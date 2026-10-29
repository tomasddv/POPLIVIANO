"""OCR local para fotos/PDF de remitos; no transmite archivos a servicios externos."""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
import re

from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import pytesseract
from pop_core import parse_ocr_text
from ocr_layout import spatial_lines


@dataclass
class OCRResult:
    rows: list[dict]
    raw_text: str
    warnings: list[str]
    images: list[tuple[str,Image.Image]]


def _normalize_image(image: Image.Image):
    image=ImageOps.exif_transpose(image).convert('RGB')
    if max(image.size)>4400:
        image.thumbnail((4400,4400),Image.Resampling.LANCZOS)
    return image


def _preprocess(image):
    # Escalado y realce moderado: reduce pérdida de números de cuatro o cinco cifras.
    image=ImageOps.autocontrast(ImageOps.grayscale(image),cutoff=1)
    scale=min(3.1,max(1.6,1650/max(1,image.width)))
    image=image.resize((int(image.width*scale),int(image.height*scale)),Image.Resampling.LANCZOS)
    image=ImageEnhance.Contrast(image).enhance(1.25)
    image=image.filter(ImageFilter.UnsharpMask(radius=1.35,percent=125,threshold=3))
    return image


def _read_photo(img, two_columns=True, split=0.50):
    W,H=img.size
    # Los remitos GS tienen dos bloques de POP, cada uno con columna de
    # cantidad y descripción. El OCR por página completa mezcla ambos.
    if two_columns:
        overlap=max(4,int(W*.018))
        boundary=int(W*split)
        parts=[('Columna izquierda',img.crop((0,0,min(W,boundary+overlap),H))),
               ('Columna derecha',img.crop((max(0,boundary-overlap),0,W,H)))]
    else:parts=[('Página completa',img)]
    texts=[]
    for label, crop in parts:
        processed=_preprocess(crop)
        # image_to_data conserva coordenadas. Es fundamental cuando Tesseract
        # ubica la cantidad y el material en bloques de texto diferentes.
        data=pytesseract.image_to_data(processed,lang='spa+eng',
                     config='--oem 3 --psm 6',output_type=pytesseract.Output.DICT)
        located=spatial_lines(data)
        spatial_text='\n'.join(line['text'] for line in located)
        parsed=parse_ocr_text(spatial_text,label)
        # En fotografías difíciles, la lectura plana puede captar palabras
        # omitidas por reconstrucción espacial. Usarla solo si es mejor.
        if len(parsed)<4:
            fallback=pytesseract.image_to_string(processed,lang='spa+eng',config='--oem 3 --psm 6')
            if len(parse_ocr_text(fallback,label))>len(parsed):
                spatial_text=fallback
        texts.append((label,spatial_text))
    return texts


def _native_pdf_texts(page, two_columns=True, split=.5):
    """Extrae texto PDF digital separado por coordenada, sin mezclar bloques."""
    words=page.get_text('words')
    if not words:return []
    width=float(page.rect.width)
    boundary=width*split
    labels=['Columna izquierda','Columna derecha'] if two_columns else ['Página completa']
    grouped={name:[] for name in labels}
    for entry in words:
        if len(entry)<5:continue
        x0,y0,x1,y1,value=entry[:5]
        xcentre=(x0+x1)/2
        label=('Columna izquierda' if xcentre < boundary else 'Columna derecha') if two_columns else labels[0]
        grouped[label].append((x0,y0,x1,y1,str(value)))
    texts=[]
    for label in labels:
        source=grouped[label]
        if not source:continue
        data={k:[] for k in ('text','left','top','width','height','conf')}
        for x0,y0,x1,y1,value in source:
            for key,value0 in (('text',value),('left',round(x0*3)),('top',round(y0*3)),
                                ('width',max(1,round((x1-x0)*3))),
                                ('height',max(1,round((y1-y0)*3))),('conf',100)):
                data[key].append(value0)
        text='\n'.join(t['text'] for t in spatial_lines(data))
        texts.append((label,text))
    return texts


def read_documents(files: list[tuple[str,bytes]],two_columns=True,split=.50,max_pages=3):
    out=[]; raw=[]; warnings=[]; previews=[];total_pages=0
    for name,data in files:
        is_pdf=name.lower().endswith('.pdf')
        if is_pdf:
            import fitz
            try:doc=fitz.open(stream=data,filetype='pdf')
            except Exception as ex:
                warnings.append(f'{name}: no se pudo abrir el PDF ({ex}).');continue
            pages=min(len(doc),max_pages-total_pages)
            for page_id in range(pages):
                page=doc[page_id];total_pages+=1
                extracted=page.get_text(sort=True).strip()
                # PDF digital: separar espacialmente las dos columnas también
                # aquí, para no heredar cantidades de la columna contraria.
                digital_parts=_native_pdf_texts(page,two_columns,split) if extracted else []
                native_rows=[]
                for label,txt in digital_parts:
                    native_rows.extend(parse_ocr_text(txt,f'{name}, página {page_id+1} ({label})',page_id+1))
                if len(native_rows)>=4:
                    out.extend(native_rows)
                    for label,txt in digital_parts:
                        raw.append(f'### {name}, página {page_id+1} · PDF texto / {label}\n{txt}')
                else:
                    pix=page.get_pixmap(matrix=fitz.Matrix(2.0,2.0),alpha=False)
                    img=_normalize_image(Image.open(BytesIO(pix.tobytes('png'))))
                    previews.append((f'{name} · página {page_id+1}',img))
                    try: texts=_read_photo(img,two_columns,split)
                    except pytesseract.TesseractNotFoundError:
                        raise RuntimeError('No se encontró Tesseract en el servidor. Revisá packages.txt y el deploy.')
                    for label,txt in texts:
                        out.extend(parse_ocr_text(txt,f'{name}, página {page_id+1} ({label})',page_id+1))
                        raw.append(f'### {name}, página {page_id+1} / {label}\n{txt}')
            if len(doc)>pages:warnings.append(f'{name}: se admiten como máximo {max_pages} páginas en total.')
            doc.close()
        else:
            if total_pages>=max_pages:break
            try:img=_normalize_image(Image.open(BytesIO(data)))
            except Exception as ex:
                warnings.append(f'{name}: imagen inválida ({ex}).');continue
            total_pages+=1;previews.append((name,img))
            try: texts=_read_photo(img,two_columns,split)
            except pytesseract.TesseractNotFoundError:
                raise RuntimeError('No se encontró Tesseract en el servidor. Revisá packages.txt y el deploy.')
            for label,txt in texts:
                out.extend(parse_ocr_text(txt,f'{name} ({label})',1))
                raw.append(f'### {name} / {label}\n{txt}')
    if not out: warnings.append('No se detectaron renglones de POP. Probá con una foto más nítida o modificá el formato de columnas.')
    return OCRResult(out,'\n\n'.join(raw),warnings,previews)
