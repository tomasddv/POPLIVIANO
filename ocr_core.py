"""OCR local para fotos/PDF de remitos; no transmite archivos a servicios externos."""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
import re

from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import pytesseract
from pop_core import parse_ocr_text


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
    # Remitos GS: 2 columnas de materiales; OCR completo mezcla cantidades de una con texto de otra.
    if two_columns:
        overlap=max(4,int(W*.018))
        boundary=int(W*split)
        parts=[('Columna izquierda',img.crop((0,0,min(W,boundary+overlap),H))),
               ('Columna derecha',img.crop((max(0,boundary-overlap),0,W,H)))]
    else:parts=[('Página completa',img)]
    texts=[]
    for label, crop in parts:
        processed=_preprocess(crop)
        txt=pytesseract.image_to_string(processed,lang='spa+eng',config='--oem 3 --psm 6')
        texts.append((label,txt))
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
                # PDF digital: usar texto nativo si contiene cantidades y materiales. De otro modo OCR.
                detected=parse_ocr_text(extracted,name,page_id+1) if extracted else []
                if len(detected)>=4:
                    out.extend(detected)
                    raw.append(f'### {name}, página {page_id+1} · PDF texto\n{extracted}')
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
