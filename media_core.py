"""Extrae y vincula imágenes reales de POP insertadas en un .xlsx.

La asignación se basa en el ancla de columna de Excel y en el nombre de hoja:
no se vinculan imágenes de una marca a otra por coincidencia visual.
"""
from __future__ import annotations
from io import BytesIO
from pathlib import PurePosixPath
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps

S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
XDR='http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
REL='http://schemas.openxmlformats.org/package/2006/relationships'


def image_jpeg(binary: bytes, max_size=(660,520), quality=78) -> bytes:
    with Image.open(BytesIO(binary)) as im:
        im=ImageOps.exif_transpose(im)
        im.thumbnail(max_size, Image.Resampling.LANCZOS)
        if im.mode!='RGB':
            rgba=im.convert('RGBA')
            background=Image.new('RGBA',rgba.size,(255,255,255,255))
            background.alpha_composite(rgba)
            im=background.convert('RGB')
        out=BytesIO();im.save(out,format='JPEG',quality=quality,optimize=True)
        return out.getvalue()


def _resolve(base: str, target: str) -> str:
    import posixpath
    return posixpath.normpath(posixpath.join(posixpath.dirname(base),target.lstrip('/'))) if not target.startswith('/') else target.lstrip('/')


def _rels(z: zipfile.ZipFile, path: str) -> dict:
    import posixpath
    relpath=posixpath.join(posixpath.dirname(path),'_rels',posixpath.basename(path)+'.rels')
    if relpath not in z.namelist():return {}
    return {node.attrib['Id']: _resolve(path,node.attrib.get('Target',''))
            for node in ET.fromstring(z.read(relpath))}


def _colnum(id_: str) -> int:
    n=0
    for char in id_.split('::')[-1]:n=n*26+ord(char)-64
    return n


def extract_pop_images(content: bytes, catalog: list[dict]) -> dict[str,bytes]:
    """Retorna miniaturas JPEG indexadas por id estable '<hoja>::<col>'."""
    valid={(c['hoja'],_colnum(c['id'])):c['id'] for c in catalog}
    result={}
    with zipfile.ZipFile(BytesIO(content)) as z:
        names=set(z.namelist())
        if 'xl/workbook.xml' not in names:return result
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        workbook_rels=_rels(z,'xl/workbook.xml')
        valid_sheets={sheet_name for sheet_name,_ in valid}
        for sheet in wb.findall(f'.//{{{S}}}sheet'):
            name=sheet.attrib.get('name','')
            if name not in valid_sheets: continue
            sheet_path=workbook_rels.get(sheet.attrib.get(f'{{{R}}}id',''))
            if not sheet_path or sheet_path not in names:continue
            root=ET.fromstring(z.read(sheet_path))
            draw=root.find(f'{{{S}}}drawing')
            if draw is None:continue
            dpath=_rels(z,sheet_path).get(draw.attrib.get(f'{{{R}}}id',''))
            if not dpath or dpath not in names:continue
            image_rels=_rels(z,dpath)
            drawing=ET.fromstring(z.read(dpath))
            for anchor in drawing:
                origin=anchor.find(f'{{{XDR}}}from')
                if origin is None:continue
                col=origin.find(f'{{{XDR}}}col')
                if col is None or col.text is None:continue
                # Anclas de Excel son 0-based; catálogo es 1-based.
                col_1=int(col.text)+1
                target=valid.get((name,col_1))
                if not target:
                    # No inventar el enlace: si el ancla cae entre columnas,
                    # solamente elegir la columna cantidad más cercana (+/- 1).
                    nearby=[(abs(index-col_1),id_) for (sheet_name,index),id_ in valid.items()
                            if sheet_name==name and abs(index-col_1)<=1]
                    if len(nearby)==1:target=nearby[0][1]
                if not target or target in result:continue
                blip=anchor.find(f'.//{{{A}}}blip')
                if blip is None:continue
                path=image_rels.get(blip.attrib.get(f'{{{R}}}embed',''))
                if path not in names:continue
                try:result[target]=image_jpeg(z.read(path))
                except (ValueError,OSError):continue
    return result


def make_scan_previews(uploaded: list[tuple[str,bytes]], max_pages:int=3) -> list[bytes]:
    """Conserva un ejemplar legible del remito para auditoría y relectura."""
    scans=[]
    for name,raw in uploaded:
        if len(scans)>=max_pages:break
        if name.lower().endswith('.pdf'):
            import fitz
            with fitz.open(stream=raw,filetype='pdf') as doc:
                for page in list(doc)[:max_pages-len(scans)]:
                    pix=page.get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False)
                    scans.append(image_jpeg(pix.tobytes('png'),(1650,2200),81))
        else:scans.append(image_jpeg(raw,(1650,2200),81))
    return scans
