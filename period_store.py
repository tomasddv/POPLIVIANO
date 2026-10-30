"""Estado y respaldos independientes por trimestre, sin dependencia de Streamlit."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
from datetime import datetime, timezone
import json
import re
import math

PERIOD_RE = re.compile(r"(?:^Q[1-4] 20\d{2}$)|(?:^20\d{2}-(?:0[1-9]|1[0-2])$)")
FIELDS = (
    'source_digest','source_name','source_mode','catalog','issues','sheets',
    'remito_entries','aliases','unmatched','is_complete','ocr_rows',
    'ocr_raw','ocr_warnings','ocr_edited_rows','ocr_version','ocr_edit_ver',
    'edit_version','remito_files','processed_signatures','ocr_signature',
    'remito_history','pending_remito_id','pop_images',
    'physical_checks','physical_events',
    'excel_history','excel_file_digests','processed_remito_files','ocr_file_digests',
    'ocr_operation','ocr_base_entries','notes','last_updated','preliminary',
)


def empty_period():
    return {
        'source_digest':None,'source_name':'','source_mode':'sin cargar',
        'catalog':[],'issues':[],'sheets':[],
        'remito_entries':{},'aliases':{},'unmatched':[],
        'is_complete':False,'ocr_rows':[],'ocr_raw':'','ocr_warnings':[],
        'ocr_edited_rows':None,'ocr_version':0,'ocr_edit_ver':0,
        'edit_version':0,'remito_files':[],'processed_signatures':[],
        'ocr_signature':None,'ocr_operation':'Reemplazar cantidades anteriores',
        'ocr_base_entries':{},'notes':'','last_updated':'','preliminary':False,
        'ocr_previews':[],'remito_history':[], 'pending_remito_id':None, 'pop_images':{},
        'physical_checks':{},'physical_events':[],
        'excel_history':[],'excel_file_digests':[],
        'processed_remito_files':[],'ocr_file_digests':[],
    }


def new_source(state, content: bytes, name: str, parser):
    catalog, issues, sheets = parser(content)
    if not catalog:
        raise ValueError('El Excel no contiene materiales de Distribuidora del Valle S.A.')
    p=empty_period()
    p.update(source_digest=sha256(content).hexdigest(),source_name=name,
             source_mode='Excel subido por el usuario', catalog=catalog, issues=issues,
             sheets=sheets,last_updated=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    return p


def merge_quantities(base, new, operation):
    """Agregar acumula sobre el estado previo al OCR, no sobre aplicaciones anteriores."""
    if operation in ('Agregar páginas al remito actual','Agregar un remito nuevo al período'):
        result=deepcopy(base)
        for key,value in new.items():result[key]=result.get(key,0)+value
        return result
    return dict(new)


def archive_data(periods):
    safe={}
    for label,p in periods.items():
        if not PERIOD_RE.fullmatch(label):continue
        clean={k:deepcopy(p.get(k)) for k in FIELDS if k in p}
        safe[label]=clean
    return {
        'format':'pop-ddv-periodos', 'version':2,
        'exported_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'periods':safe,
        'note':'El respaldo incluye catálogos, lecturas, resultados y revisiones, pero no fotografías ni archivos .xlsx originales.'
    }


def _json_safe(value):
    # Los editores de tablas pueden devolver NaN o números numpy; el JSON debe ser estándar.
    if value is None or isinstance(value,(str,bool,int)):return value
    if isinstance(value,float):return value if math.isfinite(value) else None
    if isinstance(value,dict):return {str(k):_json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_json_safe(x) for x in value]
    if hasattr(value,'item'):
        try:return _json_safe(value.item())
        except Exception:pass
    return str(value)


def archive_bytes(periods):
    return json.dumps(_json_safe(archive_data(periods)),ensure_ascii=False,indent=2,
                      allow_nan=False).encode('utf-8')


def restore_archive(content: bytes):
    if len(content)>12_000_000:raise ValueError('El respaldo JSON supera los 12 MB.')
    data=json.loads(content)
    if data.get('format')!='pop-ddv-periodos' or data.get('version')!=2:
        raise ValueError('Formato de respaldo no reconocido. Usá el JSON generado por esta versión del tablero.')
    entries=data.get('periods')
    if not isinstance(entries,dict) or len(entries)>32:
        raise ValueError('El archivo no contiene una lista válida de períodos.')
    restored={}
    for label,raw in entries.items():
        if not isinstance(label,str) or not PERIOD_RE.fullmatch(label) or not isinstance(raw,dict):
            raise ValueError('Período inválido en el respaldo.')
        p=empty_period()
        for k in FIELDS:
            if k in raw:p[k]=raw[k]
        if not isinstance(p['catalog'],list) or not isinstance(p['remito_entries'],dict) or not isinstance(p['aliases'],dict):
            raise ValueError(f'Valores de respaldo inválidos para {label}.')
        ids={x['id'] for x in p['catalog'] if isinstance(x,dict) and isinstance(x.get('id'),str)}
        if len(ids)!=len(p['catalog']):raise ValueError(f'Catálogo inválido para {label}.')
        if any(id_ not in ids for id_ in p['remito_entries']):
            raise ValueError(f'El respaldo contiene materiales desconocidos para {label}.')
        if not isinstance(p['physical_checks'],dict) or not isinstance(p['physical_events'],list):
            raise ValueError(f'Controles físicos inválidos para {label}.')
        if any(id_ not in ids or not isinstance(info,dict) for id_,info in p['physical_checks'].items()):
            raise ValueError(f'El respaldo contiene controles físicos desconocidos para {label}.')
        restored[label]=p
    return restored
