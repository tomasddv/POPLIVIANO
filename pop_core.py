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
ADMIN_SHEETS = {'INICIO', 'CONTROL', 'REGLAS', 'PEGAR ASIGNACION', 'MAESTRO'}
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
            # En Q4 las hojas administrativas no contienen asignaciones POP y
            # PEGAR ASIGNACION puede superar los 79 MB descomprimidos.
            # Se excluyen por nombre, no por estado oculto: Q3 tiene hojas
            # ocultas que SI contienen asignaciones reales para DDV.
            if normalize(name) in ADMIN_SHEETS:
                continue
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
            # Q4 / V12: fila 2 contiene UNA descripción por columna y la fila 6
            # es TOTAL NACIONAL; las cantidades del proveedor están en su propia
            # fila (ej. D142 = DISTRIBUIDORA DEL VALLE S.A.).
            # No hay cabecera CANTIDAD ni descripción en filas 4-10.
            q4_layout = (any('BLOQUE' in normalize(v) for v in rows.get(1,{}).values())
                         and any('TOTAL NACIONAL' in normalize(v) for v in rows.get(6,{}).values())
                         and len(rows.get(2,{})) >= 1)
            if q4_layout:
                amount_cols = sorted((col for col,val in rows[2].items()
                      if col_index(col) >= 5 and isinstance(val,str)
                      and normalize(val)),key=col_index)
                header_row=2
            else:
                amount_cols = None
            # La mayoría de las planillas GS usan columnas de «CANTIDAD» en fila 1,
            # además de formatos en fila 4-5; no usar métricas auxiliares ni totales.
            if amount_cols is None: amount_cols=set()
            for r in (() if q4_layout else range(1, 4)):
                amount_cols.update(col for col,val in rows.get(r,{}).items() if 'CANTIDAD' in normalize(val) or normalize(val)=='CANT')
            # Algunas hojas tienen una columna de formato sin el indicador CANTIDAD en fila 1.
            # Completar con encabezados explícitos que apunten a cantidades DDV.
            for row_i in (() if q4_layout else (4,5,6,7,8,9,10)):
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
            if not q4_layout:
                header_row=_choose_header(rows,amount_cols)
            format_row=rows.get(header_row,{})
            group_row=rows.get(header_row-1,{})
            all_grouph=([(col_index(col),val) for col,val in group_row.items()
                         if isinstance(val,str) and normalize(val)] if not q4_layout else [])
            all_grouph.sort()
            count=0;total=0
            for col in amount_cols:
                raw=ddv.get(col)
                qty=integer_quantity(raw) if raw is not None else 0
                if qty is None:
                    issues.append(f'{name}!{col}{rownum}: cantidad no entera o inválida ({str(raw)[:35]}), excluida.')
                    continue
                fmt=' '.join(str(format_row.get(col,'') or '').split())
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


def active_catalog(catalog):
    """Sólo materiales POP asignados con cantidad mayor a cero en la fila DDV.

    El catálogo original se guarda sin modificar, para trazabilidad. No filtrar
    por la palabra Patagonia: hay material regional compartido asignado a DDV.
    """
    return [c for c in catalog if (integer_quantity(c.get('cantidad_excel')) or 0) > 0]


def qty_from_ocr(text):
    s=str(text or '').strip().replace(' ','')
    if not re.fullmatch(r'[0-9][0-9.,]{0,8}',s): return None
    if s.count('.')+s.count(',')>2: return None
    digits=s.replace('.','').replace(',','')
    if len(digits)>7:return None
    return int(digits)


def _ocr_leading_quantity(token):
    """Cantidad segura o candidata con letras confundidas; candidata requiere revisión."""
    safe=qty_from_ocr(token)
    if safe is not None:return safe,None
    s=token.strip().upper().replace('.','').replace(',','')
    if not re.fullmatch(r'[0-9OISBL\|]{2,7}',s) or not any(ch.isdigit() for ch in s):
        return None,None
    corrected=s.translate(str.maketrans({'O':'0','I':'1','S':'5','B':'8','L':'1','|':'1'}))
    return None,int(corrected) if corrected.isdigit() else None


def _possible_material(detail):
    from rapidfuzz import fuzz
    norm=normalize(detail)
    if any(w in norm for w in DETAIL_WORDS):return True
    if re.search(r'\b[0-9O]{1,2}\s*X\s*[0-9O]{1,2}\b',norm):return True
    # El OCR puede cambiar 1 o 2 letras de AFICHE / CENEFA / STICKER.
    words=norm.split()
    return any(max(fuzz.ratio(t,w) for t in ('AFICHE','CENEFA','STICKER','COLLARIN','COMBO'))>=70
               for w in words[:5])


def parse_ocr_text(text: str, source: str, page_number: int=1):
    """Cantidad de cada línea; en blanco hereda la última cifra explícita.

    Sólo se hereda dentro de ESTA llamada, que equivale a una columna/página
    escaneada. Nunca se cruza el límite de columna, documento o página.
    Las cifras heredadas quedan marcadas para confirmación humana.
    """
    lines=[];last_explicit=None;last_line=None
    for line_number,raw in enumerate(text.splitlines(),1):
        line=re.sub(r'\s+',' ',raw).strip(' \t|:')
        if not line or len(line)<6:continue
        match=re.match(r'^([0-9IOSBL|][0-9IOSBL|.,]{1,8})\s+(.+)$',line,re.IGNORECASE)
        if match:
            qty,suspect=_ocr_leading_quantity(match.group(1))
            detail=match.group(2).strip()
        else:
            # Cifras con letra de ruido previa: sugerir sin aceptar automáticamente.
            dirty=re.match(r'^[A-Z]{1,3}\s*[;:,]?\s+([0-9][0-9.,]{1,7})\s+(.+)$',line,re.IGNORECASE)
            if dirty:
                qty=None;suspect=qty_from_ocr(dirty.group(1));detail=dirty.group(2).strip()
            else:
                qty=None;suspect=None;detail=line
        norm=normalize(detail)
        if len(norm)<7 or not _possible_material(detail):continue
        if 'CANT BULTOS' in norm or 'FIRMA' in norm:continue
        inherited=False
        if qty is not None:
            last_explicit=qty;last_line=line_number
            origin='Expresa en el remito'
        elif suspect is not None:
            # No heredar un número anterior sobre un renglón cuya cifra está
            # presente pero el OCR no pudo interpretarla con seguridad.
            last_explicit=None;last_line=None
            origin='Cifra OCR dudosa: verificar fotografía'
        elif last_explicit is not None:
            qty=last_explicit;inherited=True
            origin=f'Heredada de línea {last_line} en la misma columna/página: revisar'
        else:
            origin='Sin cantidad explícita ni antecedente'
        lines.append({'pagina':f'{source} · p.{page_number}', 'linea':line_number,
            'detalle':detail,'cantidad':qty,'cantidad_sugerida':suspect,
            'cantidad_heredada':inherited,'origen_cantidad':origin,
            'linea_cantidad_origen':last_line if inherited else None,
            'ocr':line,'id':'',
            'estado_ocr':('Cantidad heredada · revisar' if inherited else
                'Cantidad detectada' if qty is not None else
                ('Cantidad OCR dudosa' if suspect is not None else 'Revisar cantidad'))})
    return lines


def suggest_matches(ocr_rows, catalog, aliases=None):
    """Usa similitud tolerante al OCR sin modificar cantidades del remito."""
    from fuzzy_match import suggest_matches as match
    return match(ocr_rows,catalog,aliases)


def classify_out_of_scope(suggestions, full_catalog, aliases=None):
    """Marca coincidencias claras contra POP con asignación DDV=0, auditables.

    No descarta lecturas ambiguas ni modifica cantidades. Los registros fuera
    de alcance quedan por defecto sin sumar a la recepción, visibles en OCR.
    """
    from fuzzy_match import rank_matches
    active=active_catalog(full_catalog)
    active_ids={c['id'] for c in active}
    output=[]
    for row0 in suggestions:
        row=dict(row0)
        row['fuera_ddv']=False;row['razon_fuera_ddv']=''
        if not row.get('id'):
            full=rank_matches(row.get('detalle',''),full_catalog,aliases)
            positive=rank_matches(row.get('detalle',''),active,aliases)
            if full:
                best=full[0];active_score=positive[0]['score'] if positive else 0
                if (best['id'] not in active_ids and best['score']>=86
                    and best['score']-active_score>=12 and not best['flags']):
                    source=next((c for c in full_catalog if c['id']==best['id']),None)
                    if source and (integer_quantity(source.get('cantidad_excel')) or 0)==0:
                        row['fuera_ddv']=True
                        row['razon_fuera_ddv']=(f"DDV=0 para {source.get('hoja','')} · "
                            f"{source.get('formato','')} · {source['id']}; "
                            f"similitud {round(best['score'])}%")
                        row['estado_match']='Fuera de asignación DDV · revisar'
        output.append(row)
    return output


def reconcile(catalog, quantities, completed=False,include_hidden=True, physical_checks=None):
    rows=[]
    checks=physical_checks or {}
    for c in catalog:
        if c['oculta'] and not include_hidden:continue
        qty=quantities.get(c['id'])
        expected=c['cantidad_excel']
        original=integer_quantity(qty) if qty is not None else (0 if completed else None)
        verified=c['id'] in checks
        if original is None:previous_status='Pendiente' if expected>0 else 'Sin movimiento'
        elif original==expected:previous_status='Coincide'
        elif original<expected:previous_status='Faltante'
        else:previous_status='Sobrante'
        # El valor del remito bruto queda intacto. La conciliación visible
        # refleja el recuento físico aprobado y es reversible.
        received=expected if verified else original
        delta=received-expected if received is not None else None
        if received is None:status='Pendiente' if expected>0 else 'Sin movimiento'
        elif delta==0:status='Coincide'
        elif delta<0:status='Faltante'
        else:status='Sobrante'
        rows.append({**c,'cantidad_remito':received,'cantidad_remito_original':original,
                     'diferencia':delta,'estado':status,'estado_original':previous_status,
                     'verificacion_fisica':verified,
                     'fecha_verificacion':checks.get(c['id'],{}).get('fecha'),
                     'verificado':c['id'] in quantities or verified})
    return rows


def metrics(rows):
    return {'asignado':sum(r['cantidad_excel'] for r in rows),
            'recibido':sum(r['cantidad_remito'] or 0 for r in rows),
            'coinciden':sum(r['estado']=='Coincide' for r in rows),
            'diferencias':sum(r['estado'] in ('Faltante','Sobrante') for r in rows),
            'pendientes':sum(r['estado']=='Pendiente' for r in rows),
            'verificados_fisicos':sum(bool(r.get('verificacion_fisica')) for r in rows),
            'remito_original':sum(r.get('cantidad_remito_original') or 0 for r in rows),
            'faltan_unidades':sum(-r['diferencia'] for r in rows if r['diferencia'] is not None and r['diferencia']<0),
            'sobran_unidades':sum(r['diferencia'] for r in rows if r['diferencia'] is not None and r['diferencia']>0)}


def to_csv(rows):
    f=StringIO();cols=['hoja','grupo','formato','material','celda','cantidad_excel','cantidad_remito_original','cantidad_remito','diferencia','estado','estado_original','verificacion_fisica','fecha_verificacion','verificado','oculta']
    writer=csv.DictWriter(f,fieldnames=cols,delimiter=';',extrasaction='ignore')
    writer.writeheader();writer.writerows(rows)
    return ('\ufeff'+f.getvalue()).encode('utf-8')
