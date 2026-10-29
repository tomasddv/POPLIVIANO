"""Reconstrucción espacial de renglones OCR de remitos GS.

El PDF/foto coloca la cantidad a la izquierda de la descripción. Tesseract
puede devolverlas como bloques distintos: unir por cercanía vertical evita
que una cantidad pase al POP equivocado. No deduce cantidades del Excel.
"""
from __future__ import annotations
import re
from statistics import median


def _dict_words(data):
    result=[]
    length=len(data.get('text',[]))
    for i in range(length):
        token=str(data['text'][i] or '').strip()
        if not token:continue
        try:
            x=int(data['left'][i]);y=int(data['top'][i]);w=int(data['width'][i]);h=int(data['height'][i])
            conf=float(data['conf'][i])
        except (TypeError, ValueError, KeyError):continue
        if w<=0 or h<=0 or conf<0:continue
        result.append({'text':token,'x':x,'y':y,'w':w,'h':h,'cy':y+h/2,'conf':conf})
    return result


def _row_is_numeric(row):
    # Las cifras pueden llevar puntuación o una única letra ruido del OCR.
    text=' '.join(t['text'] for t in sorted(row['words'],key=lambda w:w['x']))
    return bool(re.fullmatch(r'[qQkKpPeE]?\s*[0-9OISBL|.,]{2,9}',text))


def spatial_lines(data):
    """Reconstruye filas por Y a partir de image_to_data de Tesseract.

    Devuelve el texto y la coordenada de la fila para auditar lecturas.
    No cruza una columna/página: el llamador recorta ambas por separado.
    """
    words=_dict_words(data)
    if not words:return []
    height=median(w['h'] for w in words)
    # Menor que el interlineado habitual, mayor que la diferencia de centros
    # causada por mayúsculas, tildes y cifras.
    tolerance=max(5.0,min(18.0,height*.57))
    rows=[]
    for word in sorted(words,key=lambda t:(t['cy'],t['x'])):
        candidates=[(abs(r['cy']-word['cy']),r) for r in rows if abs(r['cy']-word['cy'])<=tolerance]
        if candidates:
            _,row=min(candidates,key=lambda q:q[0])
            row['words'].append(word)
            row['cy']=median(w['cy'] for w in row['words'])
        else:
            rows.append({'cy':word['cy'],'words':[word]})
    rows.sort(key=lambda r:r['cy'])
    # En remitos con leve inclinación los dígitos aislados pueden quedar 1/2
    # interlineado arriba/abajo de su descripción; nunca unir con filas lejanas.
    for row in list(rows):
        if not _row_is_numeric(row):continue
        if len(row['words'])>3:continue
        numeric_right=max(w['x']+w['w'] for w in row['words'])
        candidates=[]
        for other in rows:
            if other is row or _row_is_numeric(other):continue
            text_left=min(w['x'] for w in other['words'])
            delta=abs(other['cy']-row['cy'])
            if numeric_right<text_left and delta<height*.93:
                candidates.append((delta,other))
        if candidates:
            _,target=min(candidates,key=lambda q:q[0])
            target['words'].extend(row['words'])
            rows.remove(row)
    result=[]
    for row in sorted(rows,key=lambda r:r['cy']):
        tokens=sorted(row['words'],key=lambda t:t['x'])
        value=' '.join(w['text'] for w in tokens).strip()
        if value:
            result.append({'text':value,'y':round(row['cy'],1),
                           'confidence':round(median(w['conf'] for w in tokens),1)})
    return result
