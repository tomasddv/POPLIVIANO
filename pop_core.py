"""Conciliación POP DDV. No requiere un formato de trimestre fijo ni códigos de producto históricos."""
from __future__ import annotations
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from io import BytesIO, StringIO
import csv
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

MAIN = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
DETAIL_WORDS = ('AFICHE', 'CENEFA', 'STICKER', 'COLLAR', 'COMBO', 'INTERNO', 'EXTERNO',
                'CARTEL', 'FLEJE', 'WOBBLER', 'CENEF', 'BANNER', 'TIRAS', 'VINILO', 'BOTELLA')


def normalize(s):
    val = unicodedata.normalize('NFKD', str(s or '').upper().replace('×','X'))
    val = ''.join(ch for ch in val if not unicodedata.combining(ch))
    val = val.replace('A.F.', 'AF')
    return re.sub(r'[^A-Z0-9]+', ' ', val).strip()


def col_index(label):
    idx = 0
    for letter in label: idx = idx * 26 + ord(letter) - 64
    return idx


def integer_quantity(value):
    if value is None or str(value).strip() == '': return None
    try:
        v = float(str(value).replace(',','.'))
        return int(v) if v >= 0 and v.is_integer() else None
    except (ValueError, TypeError, OverflowError): return None


def _get_text(cell, shared):
    v = cell.find(MAIN+'v')
    if v is not None and v.text is not None:
        if cell.get('t')=='s':
            index=int(v.text)
            return shared[index] if index < len(shared) else None
        return v.text
    inline=cell.find(MAIN+'is')
    if inline is not None: return ''.join(n.text or '' for n in inline.iter(MAIN+'t'))
    if cell.find(MAIN+'f') is not None: return '__FORMULA_SIN_VALOR_CALCULADO__'
    return None


def _read_zip_rows(zf, path, shared):
    rows = {}
    root = ET.fromstring(zf.read(path))
    for row in root.findall('.//'+MAIN+'sheetData/'+MAIN+'row'):
        cells = {}
        for c in row.findall(MAIN+'c'):
            col=re.match(r'[A-Z]+',c.get('r',''))
            if not col: continue
            value=_get_text(c,shared)
            if value is not None: cells[col.group()] = value
        rows[int(row.get('r'))]=cells
    return rows


def _ddv_name(s):
    key=normalize(s)
    return key in ('DISTRIBUIDORA DEL VALLE SA','DISTRIBUIDORA DEL VALLE S A',
                   'DISTRIBUIDORA DEL VALLE','DIST DEL VALLE SA', 'DIST DEL VALLE S A')


def _choose_header(rows, expected_cols):
    """Priorizar renglones superiores de formato, evitando filas de estimación/cálculo."""
    preferred=[]
    for rownum in range(2, 17):
        row=rows.get(rownum,{})
        if not row: continue
        cnt=0
        for col in expected_cols:
            v=row.get(col)
            if isinstance(v,str) and normalize(v) and not normalize(v).isdigit(): cnt+=1
        if cnt:
            # Q3: fila 5 = formato y 4 = agrupación. En otros trimestres la fila puede cambiar.
            preferred.append((cnt, 1 if rownum==5 else 0, -abs(rownum-5),rownum))
    if not preferred: return 5
    return sorted(preferred,reverse=True)[0][-1]


def catalog_from_excel(content: bytes):
    """Lee TODAS las hojas de Excel, tomando solo la fila DDV; devuelve (materiales, alertas, hojas)."""
    catalog=[];issues=[];meta=[]
    try: zf=zipfile.ZipFile(BytesIO(content))
    except (zipfile.BadZipFile,TypeError) as ex: raise ValueError('El archivo no es un Excel .xlsx válido.') from ex
    with zf:
        if 'xl/workbook.xml' not in zf.namelist(): raise ValueError('El archivo no contiene una estructura Excel .xlsx válida.')
        shared=[]
        if 'xl/sharedStrings.xml' in zf.namelist():
            ss=ET.fromstring(zf.read('xl/sharedStrings.xml'))
            shared=[''.join(node.text or '' for node in si.iter(MAIN+'t')) for si in ss.findall(MAIN+'si')]
        wb=ET.fromstring(zf.read('xl/workbook.xml'))
        rel=ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
        mapping={node.get('Id'):node.get('Target') for node in rel}
        for sheet in wb.findall('.//'+MAIN+'sheets/'+MAIN+'sheet'):
            name=sheet.get('name') or 'Sin nombre'
            hidden=sheet.get('state','visible')!='visible'
            dest=mapping.get(sheet.get(REL+'id'),'')
            if not dest:
                issues.append(f'{name}: no se encontró el archivo de hoja.');continue
            path=dest.lstrip('/')
            if not path.startswith('xl/'): path='xl/'+path
            path=path.replace('xl/xl/','xl/')
            if path not in zf.namelist():
                issues.append(f'{name}: archivo interno no encontrado.');continue
            rows=_read_zip_rows(zf,path,shared)
            matches=[(r,values) for r,values in rows.items() if any(_ddv_name(v) for v in values.values())]
            if len(matches)!=1:
                issues.append(f'{name}: fila DDV {"ausente" if not matches else "duplicada"}. Hoja excluida (NO se usan otros distribuidores).')
                meta.append({'hoja':name,'oculta':hidden,'fila_ddv':None,'materiales':0,'total':0,'cabecera':None})
                continue
            rownum, ddv = matches[0]
            # La mayoría de las planillas GS usan columnas de «CANTIDAD» en fila 1,
            # además de formatos en fila 4-5; no usar métricas auxiliares ni totales.
            amount_cols=set()
            for r in range(1, 4):
                amount_cols.update(col for col,val in rows.get(r,{}).items() if 'CANTIDAD' in normalize(val) or normalize(val)=='CANT')
            # Algunas hojas tienen una columna de formato sin el indicador CANTIDAD en fila 1.
            # Completar con encabezados explícitos que apunten a cantidades DDV.
            for row_i in (4,5,6,7,8,9,10):
                for col,val in rows.get(row_i,{}).items():
                    description=normalize(val)
                    if not isinstance(val,str):continue
                    if integer_quantity(ddv.get(col)) is None:continue
                    if (any(word in description for word in DETAIL_WORDS) or re.search(r"\b\d{1,2}\s*X\s*\d{1,2}\b",description)):
                        amount_cols.add(col)
            if not amount_cols:
                for row_i in (4,5,6,7,8,9,10):
                    for col,val in rows.get(row_i,{}).items():
                        s=normalize(val)
                        if isinstance(val,str) and (any(word in s for word in DETAIL_WORDS) or re.search(r'\b\d{1,2}\s*X\s*\d{1,2}\b',s)):
                            amount_cols.add(col)
            # Si el Excel no rotula bien cabeceras, se contemplan celdas numéricas
            # con encabezado de producto, sin asumir que toda cifra en DDV es POP.
            if not amount_cols:
                issues.append(f'{name}: no se identificaron encabezados de cantidad / POP. Hoja sin asignaciones.')
                meta.append({'hoja':name,'oculta':hidden,'fila_ddv':rownum,'materiales':0,'total':0,'cabecera':None})
                continue
            amount_cols=sorted(amount_cols,key=col_index)
            header_row=_choose_header(rows,amount_cols)
            format_row=rows.get(header_row,{})
            group_row=rows.get(header_row-1,{})
            all_grouph=[(col_index(col),val) for col,val in group_row.items() if isinstance(val,str) and normalize(val)]
            all_grouph.sort()
            count=0;total=0
            for col in amount_cols:
                raw=ddv.get(col)
                qty=integer_quantity(raw) if raw is not None else 0
                if qty is None:
                    issues.append(f'{name}!{col}{rownum}: cantidad no entera o inválida ({str(raw)[:35]}), excluida.')
                    continue
                fmt=str(format_row.get(col,'') or '').strip()
                prior=[(idx,txt) for idx,txt in all_grouph if idx<=col_index(col)]
                group=str(prior[-1][1]).strip() if prior else name
                # A veces la fila de grupo es solo una cabecera genérica
                if not fmt: fmt=str(rows.get(4,{}).get(col,'') or 'Material sin descripción')
                if not fmt:fmt='Material sin descripción'
                chunks=[name]
                if normalize(group) not in (normalize(name),normalize(fmt)) and group:chunks.append(group)
                if normalize(fmt)!=normalize(name):chunks.append(fmt)
                label=' · '.join(chunks)
                catalog.append({'id':f'{name}::{col}','hoja':name,'grupo':group,'formato':fmt,
                    'material':label,'cantidad_excel':qty,'celda':f'{col}{rownum}',
                    'oculta':hidden,'fila':rownum,'cabecera':header_row})
                count+=1;total+=qty
            meta.append({'hoja':name,'oculta':hidden,'fila_ddv':rownum,'materiales':count,'total':total,'cabecera':header_row})
    return catalog,issues,meta


def qty_from_ocr(text):
    s=str(text or '').strip().replace(' ','')
    if not re.fullmatch(r'[0-9][0-9.,]{0,8}',s): return None
    if s.count('.')+s.count(',')>2: return None
    digits=s.replace('.','').replace(',','')
    if len(digits)>7:return None
    return int(digits)


def parse_ocr_text(text: str, source: str, page_number: int=1):
    """No descarta materiales si el OCR pierde la cantidad: quedan pendientes de revisión."""
    lines=[]
    for line_number, raw in enumerate(text.splitlines(),1):
        line=re.sub(r'\s+',' ',raw).strip(' \t|:')
        if not line or len(line)<6: continue
        hit=re.match(r'^\s*([0-9][0-9.,]{0,8})\s+(.+)$',line)
        if hit:
            qty=qty_from_ocr(hit.group(1));detail=hit.group(2).strip()
        else:qty=None;detail=line
        norm=normalize(detail)
        if len(norm)<8:continue
        if not (any(word in norm for word in DETAIL_WORDS) or re.search(r'\b\d{1,2}\s*X\s*\d{1,2}\b',norm)):
            continue
        if 'CANT BULTOS' in norm or 'FIRMA' in norm:continue
        lines.append({'pagina':f'{source} · p.{page_number}', 'linea':line_number,
                      'detalle':detail,'cantidad':qty,'ocr':line,'id':'',
                      'estado_ocr':'Cantidad detectada' if qty is not None else 'Revisar cantidad'})
    return lines


def _score(detail, source):
    # «AFICHE A3» y «AS» (confusión habitual de OCR) reciben normalización.
    q=normalize(detail).replace('AFICHE AS ','AFICHE A3 ')
    s=normalize(source).replace('AFICHE AS ','AFICHE A3 ')
    if not q or not s:return 0.0
    # No usar la cantidad asignada para sugerir match: produciría confirmaciones circulares.
    qa=set(q.split()); sa=set(s.split())
    common=len(qa&sa); union=len(qa|sa)
    j=common/union if union else 0
    cover=common/max(1,min(len(qa),len(sa)))
    similarity=SequenceMatcher(None,q,s).ratio()
    return 100*(.32*j+.30*cover+.38*similarity)


def suggest_matches(ocr_rows,catalog,aliases=None):
    aliases=aliases or {}
    # Si varias columnas tienen identidad indistinguible, nunca hacer enlace automático.
    labels={m['id']:' '.join([m['material'],aliases.get(m['id'],'')]) for m in catalog}
    candidates=[]
    for r in ocr_rows:
        ranked=sorted((( _score(r.get('detalle',''),label),ident) for ident,label in labels.items()),reverse=True)
        next_row=dict(r)
        score,id_=(ranked[0] if ranked else (0,''))
        second=ranked[1][0] if len(ranked)>1 else 0
        next_row['sugerido']=id_ if score>=42 else ''
        next_row['puntaje']=round(score)
        next_row['segunda_opcion']=round(second)
        next_row['id']=id_ if score>=68 and score-second>=12 else ''
        next_row['estado_match']='Automática: revisar' if next_row['id'] else ('Sugerencia ambigua' if score>=42 else 'Sin sugerencia')
        candidates.append(next_row)
    # Más de una fila puede mapear el mismo material si realmente aparece en más de una página.
    # Siempre se muestra para revisión, nunca se omiten páginas duplicadas.
    return candidates


def reconcile(catalog, quantities, completed=False,include_hidden=True):
    rows=[]
    for c in catalog:
        if c['oculta'] and not include_hidden:continue
        qty=quantities.get(c['id'])
        expected=c['cantidad_excel']
        received=integer_quantity(qty) if qty is not None else (0 if completed else None)
        delta=received-expected if received is not None else None
        if received is None:status='Pendiente' if expected>0 else 'Sin movimiento'
        elif delta==0:status='Coincide'
        elif delta<0:status='Faltante'
        else:status='Sobrante'
        rows.append({**c,'cantidad_remito':received,'diferencia':delta,'estado':status,
                     'verificado':c['id'] in quantities})
    return rows


def metrics(rows):
    return {'asignado':sum(r['cantidad_excel'] for r in rows),
            'recibido':sum(r['cantidad_remito'] or 0 for r in rows),
            'coinciden':sum(r['estado']=='Coincide' for r in rows),
            'diferencias':sum(r['estado'] in ('Faltante','Sobrante') for r in rows),
            'pendientes':sum(r['estado']=='Pendiente' for r in rows),
            'faltan_unidades':sum(-r['diferencia'] for r in rows if r['diferencia'] is not None and r['diferencia']<0),
            'sobran_unidades':sum(r['diferencia'] for r in rows if r['diferencia'] is not None and r['diferencia']>0)}


def to_csv(rows):
    f=StringIO();cols=['hoja','grupo','formato','material','celda','cantidad_excel','cantidad_remito','diferencia','estado','verificado','oculta']
    writer=csv.DictWriter(f,fieldnames=cols,delimiter=';',extrasaction='ignore')
    writer.writeheader();writer.writerows(rows)
    return ('\ufeff'+f.getvalue()).encode('utf-8')
