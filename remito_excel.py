"""Carga de remitos Excel REVISADOS, independiente del OCR y del Excel de asignación.

Conserva número de remito, fecha, columna, fila, cantidad y procedencia;
no inventa/ajusta cantidades desde el Excel de asignación.
"""
from __future__ import annotations
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
from collections import Counter
import re
import unicodedata
import pandas as pd

MAX_FILES = 20
MAX_ROWS = 2500


def _key(value):
    value = unicodedata.normalize('NFKD', str(value or '').strip().upper())
    return re.sub(r'[^A-Z0-9]', '', ''.join(ch for ch in value if not unicodedata.combining(ch)))


def _field(names, *alternatives):
    for label in alternatives:
        if _key(label) in names: return names[_key(label)]
    return None


def _date(value):
    if isinstance(value,(datetime,date)):
        return value.strftime('%Y-%m-%d')
    if pd.isna(value):return ''
    x=str(value).strip()
    if re.fullmatch(r'20\d{2}-\d{2}-\d{2}',x):return x
    for pattern in ('%d/%m/%Y','%d-%m-%Y','%Y/%m/%d','%Y-%m-%d 00:00:00'):
        try:return datetime.strptime(x,pattern).strftime('%Y-%m-%d')
        except ValueError:pass
    raise ValueError('Fecha no válida: '+x[:30]+'. Usá AAAA-MM-DD o DD/MM/AAAA.')


def _qty(value,filename,rownum):
    if pd.isna(value) or str(value).strip()=='':
        raise ValueError(f'{filename}, fila Excel {rownum}: falta cantidad. Revisala antes de subir.')
    if isinstance(value,bool):raise ValueError(f'{filename}, fila {rownum}: cantidad inválida.')
    try:
        if isinstance(value,str):
            x=value.strip().replace(' ','')
            if not re.fullmatch(r'\d{1,3}(?:[.,]\d{3})*|\d+',x):raise ValueError()
            x=x.replace('.','').replace(',','')
            num=int(x)
        else:
            if float(value)!=int(float(value)):raise ValueError()
            num=int(value)
    except (ValueError,TypeError,OverflowError):
        raise ValueError(f'{filename}, fila Excel {rownum}: cantidad inválida: {value}')
    if not 0<=num<=10_000_000:
        raise ValueError(f'{filename}, fila {rownum}: cantidad fuera de rango.')
    return num


def parse_file(filename,raw):
    """Interpreta hojas REMITO y/o hojas con las columnas estándar.

    Una fila = un material del remito. No interpreta la hoja de instrucciones.
    """
    if not filename.lower().endswith('.xlsx'):
        raise ValueError(f'{filename}: solo se admiten archivos .xlsx.')
    if len(raw)>60_000_000:
        raise ValueError(f'{filename}: supera 60 MB.')
    try:
        book=pd.ExcelFile(BytesIO(raw))
    except Exception as exc:
        raise ValueError(f'{filename}: no se puede abrir el Excel: {exc}') from exc
    result=[];pages=[]
    for sheet in book.sheet_names:
        # la primera fila de las hojas tiene encabezados; ignorar instructivos
        df=book.parse(sheet_name=sheet,dtype=object)
        cols={_key(c):c for c in df.columns}
        dcol=_field(cols,'DESCRIPCION POP','DESCRIPCION','DETALLE','MATERIAL REMITO','MATERIAL')
        qcol=_field(cols,'CANTIDAD','CANTIDAD REMITO','UNIDADES')
        if not dcol or not qcol:continue
        numcol=_field(cols,'REMITO','NUMERO REMITO','N REMITO','NRO REMITO')
        fcol=_field(cols,'FECHA','FECHA REMITO')
        co_col=_field(cols,'COLUMNA','COLUMNA REMITO')
        rowcol=_field(cols,'FILA','LINEA','RENGLON')
        origcol=_field(cols,'ORIGEN CANTIDAD','ORIGEN')
        includecol=_field(cols,'INCLUIR','INCLUIR EN CONTROL')
        if not numcol:
            raise ValueError(f'{filename}, hoja {sheet}: falta columna REMITO. Es necesaria para evitar duplicados.')
        if not fcol:
            raise ValueError(f'{filename}, hoja {sheet}: falta columna FECHA.')
        count=0
        for ix,row in df.iterrows():
            detail = row[dcol]
            if pd.isna(detail) or not str(detail).strip():continue
            detail=str(detail).strip()
            if includecol:
                flag=str(row[includecol]).strip().upper() if not pd.isna(row[includecol]) else 'SI'
                if flag in ('NO','N','FALSE','0','EXCLUIR'):
                    continue
                if flag not in ('SI','S','TRUE','1','INCLUIR'):
                    raise ValueError(f'{filename}, fila Excel {ix+2}: INCLUIR debe ser SI o NO.')
            if len(detail)<5:raise ValueError(f'{filename}, hoja {sheet}, fila {ix+2}: descripción demasiado corta.')
            number=row[numcol]
            if pd.isna(number):raise ValueError(f'{filename}, hoja {sheet}, fila {ix+2}: remito sin número.')
            number=re.sub(r'\D','',str(number).strip())
            if not number or len(number)>15:raise ValueError(f'{filename}, hoja {sheet}, fila {ix+2}: número de remito inválido.')
            number=number.zfill(8)
            dat=_date(row[fcol]);n=_qty(row[qcol],filename,ix+2)
            col=str(row[co_col]).strip() if co_col and not pd.isna(row[co_col]) else sheet
            linea=str(row[rowcol]).strip() if rowcol and not pd.isna(row[rowcol]) else str(ix+1)
            source=str(row[origcol]).strip() if origcol and not pd.isna(row[origcol]) else 'REVISADO EN EXCEL'
            result.append({'remito':number,'fecha':dat,'columna':col,'fila_excel':ix+2,
                           'linea_remito':linea,'detalle':detail,'cantidad':n,'origen_cantidad':source,
                           'pagina':f'{filename} · {sheet} · fila {ix+2}',
                           'cantidad_heredada': 'HEREDAD' in source.upper(), 'id':'',
                           'estado_ocr':'Cantidad proveniente de Excel revisado'})
            count+=1
        pages.append((sheet,count))
    if not result:
        if pages:raise ValueError(f'{filename}: hay hojas válidas, pero todas las filas tienen INCLUIR=NO o carecen de descripción.')
        raise ValueError(f'{filename}: no se encontró una hoja con columnas REMITO, FECHA, DESCRIPCION POP y CANTIDAD.')
    if len(result)>MAX_ROWS:raise ValueError(f'{filename}: más de {MAX_ROWS} filas.')
    docs={r['remito'] for r in result}; dates={r['fecha'] for r in result if r['fecha']}
    if len(docs)>1:
        # para archivos consolidados se permite múltiples números de remito, fechas distintas,
        # pero no mezcla de meses dentro de un único período mensual.
        pass
    return {'nombre':filename,'digest':sha256(raw).hexdigest(),'filas':result,
            'remitos':sorted(docs),'meses':sorted({d[:7] for d in dates}), 'hojas':pages}


def parse_batch(files,period=None,existing_history=None):
    if not files:raise ValueError('Subí al menos un Excel de remito.')
    if len(files)>MAX_FILES:raise ValueError(f'Máximo {MAX_FILES} archivos por lote.')
    parsed=[parse_file(name,raw) for name,raw in files]
    hashes=[x['digest'] for x in parsed]
    if len(set(hashes))!=len(hashes):raise ValueError('Un mismo archivo está repetido en el lote.')
    all_ids=[n for f in parsed for n in f['remitos']]
    repeated=sorted(n for n,c in Counter(all_ids).items() if c>1)
    if repeated:
        raise ValueError('El mismo número de remito aparece en varios Excel: '+', '.join(repeated)+'. Combiná todas sus páginas en un solo archivo.')
    old_docs={r for h in (existing_history or []) for r in h.get('remitos',[])}
    old_digests={h.get('digest') for h in (existing_history or [])}
    if set(all_ids)&old_docs:
        raise ValueError('Remito ya incorporado en este período: '+', '.join(sorted(set(all_ids)&old_docs))+'. Para corregirlo, reemplazá la recepción del período.')
    if set(hashes)&old_digests:
        raise ValueError('Este Excel ya se importó; no se duplicaron las cantidades.')
    if period and re.fullmatch(r'20\d{2}-\d{2}',period):
        mismatches=sorted({x for f in parsed for x in f['meses'] if x!=period})
        if mismatches:raise ValueError(f'Estás cargando {period}, pero hay remitos de {", ".join(mismatches)}. Elegí su mes correspondiente para evitar mezclar las recepciones.')
    rows=[r for f in parsed for r in f['filas']]
    return parsed,rows
