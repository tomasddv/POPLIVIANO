"""Consolidación por mes de asignaciones DDV procedentes de múltiples Excel.

Se suman entregas adicionales, NO snapshots acumulativos de la misma asignación.
No se fusionan columnas con identidades ambiguas ni se aceptan archivos duplicados.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from collections import defaultdict
import re

MONTH_RE = re.compile(r'^20\d{2}-(?:0[1-9]|1[0-2])$')
MONTH_NAMES = ('','Enero','Febrero','Marzo','Abril','Mayo','Junio',
               'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre')


def scope_label(scope):
    if MONTH_RE.fullmatch(scope):
        year, month = scope.split('-')
        return f'{MONTH_NAMES[int(month)]} {year} · mensual'
    return scope + ' · histórico trimestral'


def scope_sort(label):
    if MONTH_RE.fullmatch(label):
        return (int(label[:4]),int(label[-2:]),1)
    year=int(label[-4:]); q=int(label[1]); return year, (q-1)*3+1,0


def _key(row):
    from pop_core import normalize
    return (normalize(row.get('hoja')), normalize(row.get('grupo')),
            normalize(row.get('formato')))


def _summarize_sheets(catalog, old_meta, new_meta):
    # Cada hoja se presenta consolidada y con los totales calculados de nuevo.
    by_name={}
    for item in list(old_meta) + list(new_meta):
        name=item['hoja']
        if name not in by_name:
            by_name[name]=dict(item)
        else:
            by_name[name]['oculta']=bool(by_name[name]['oculta'] and item.get('oculta'))
            if by_name[name].get('fila_ddv')!=item.get('fila_ddv'):
                by_name[name]['fila_ddv']='varias'
    for name, item in by_name.items():
        subset=[c for c in catalog if c['hoja']==name]
        item['total']=sum(int(c['cantidad_excel']) for c in subset)
        item['materiales']=len(subset)
    return sorted(by_name.values(),key=lambda d:d['hoja'])


def merge_catalog(existing, incoming, digest):
    """Fusionar misma hoja+columna y descripción; migración de columnas solo si no ambigua.

    Duplicados de descripciones dentro de una hoja son objetos distintos salvo que
    tengan la misma columna original. Si una celda se reutiliza para otro POP,
    se crea un ID distinto con prefijo de archivo para no alterar recepciones.
    """
    from pop_core import normalize
    merged=[deepcopy(c) for c in existing]
    by_id={c['id']:i for i,c in enumerate(merged)}
    by_key=defaultdict(list)
    for i,c in enumerate(merged): by_key[_key(c)].append(i)
    map_incoming={}
    merged_count=0; new_count=0; warnings=[]
    for incoming_row in incoming:
        row=deepcopy(incoming_row)
        origin_id=row['id']
        idx=by_id.get(origin_id)
        if idx is not None and _key(row)!=_key(merged[idx]):
            warnings.append(f'{row["hoja"]} / {row["celda"]}: distinta descripción en dos Excel; se conservan como POP separados.')
            idx=None
        if idx is None:
            candidates=by_key.get(_key(row),[])
            # Permitir mover columnas entre Excel solo si la descripción existe UNA sola vez.
            if len(candidates)==1:
                idx=candidates[0]
            elif len(candidates)>1:
                warnings.append(f'{row["hoja"]} / {row["formato"]}: varias referencias posibles en Excel anteriores; no se fusiona automáticamente.')
        if idx is not None:
            current=merged[idx]
            current['cantidad_excel']=int(current['cantidad_excel'])+int(row['cantidad_excel'])
            current['origen_archivos']=int(current.get('origen_archivos',1))+1
            current['oculta']=bool(current.get('oculta') and row.get('oculta'))
            map_incoming[origin_id]=current['id']
            merged_count+=1
            continue
        if row['id'] in by_id:
            row['id']=f'{digest[:10]}::{origin_id}'
        row['origen_archivos']=1
        by_id[row['id']]=len(merged)
        # No agregar esta nueva fila al índice de coincidencias del lote:
        # dos columnas con descripción idéntica en UN MISMO Excel
        # pueden ser POP diferentes y deben conservar sus IDs.
        merged.append(row)
        map_incoming[origin_id]=row['id']
        new_count+=1
    return merged,map_incoming,merged_count,new_count,warnings


def ingest_excels(period, files, parser, *, replace=False):
    """Transacción: o se incorporan TODOS los archivos o no se modifica el período.

    files: [(filename, binary), ...]. Retorna estado, mapeos para imágenes y resumen.
    """
    from period_store import empty_period
    from pop_core import active_catalog
    if not files:raise ValueError('Seleccioná al menos un Excel.')
    if len(files)>15:raise ValueError('Máximo 15 archivos Excel por carga. Podés realizar varias cargas.')
    previous=deepcopy(period)
    p=empty_period() if replace else deepcopy(period)
    sources=list(p.get('excel_history',[]))
    # Convertir un Excel histórico precargado en la primera fuente del historial,
    # sin re-sumar su catálogo ni perder su huella de duplicados.
    if p.get('catalog') and not sources and p.get('source_digest'):
        sources=[{'archivo':p.get('source_name') or 'Excel histórico',
                  'digest':p['source_digest'],'fecha':'Carga histórica previa',
                  'unidades_ddv':sum(int(x['cantidad_excel']) for x in p['catalog'] if x['cantidad_excel']>0),
                  'pop_ddv':sum(x['cantidad_excel']>0 for x in p['catalog']),
                  'agregados':len(p['catalog']),'combinados':0}]
    seen=set(p.get('excel_file_digests',[]))
    seen.update(s['digest'] for s in sources if s.get('digest'))
    if p.get('source_digest') and not sources:
        seen.add(p['source_digest'])
    image_mappings=[];reports=[];seen_this_batch=set()
    for filename, content in files:
        if not isinstance(content,bytes) or not content:
            raise ValueError(f'{filename}: archivo vacío.')
        digest=sha256(content).hexdigest()
        if digest in seen or digest in seen_this_batch:
            raise ValueError(f'{filename}: archivo ya incorporado en este período. No se sumó dos veces.')
        seen_this_batch.add(digest)
        incoming, issues, sheets = parser(content)
        if not incoming or not active_catalog(incoming):
            raise ValueError(f'{filename}: no se encontraron cantidades positivas asignadas a Distribuidora del Valle.')
        catalog,mapping,merged_count,new_count,warnings=merge_catalog(p['catalog'],incoming,digest)
        previous_catalog=p['catalog']
        p['catalog']=catalog
        p['sheets']=_summarize_sheets(catalog,p.get('sheets',[]),sheets)
        p['issues'].extend(f'{filename}: {issue}' for issue in issues)
        p['issues'].extend(warnings)
        qty=sum(int(x['cantidad_excel']) for x in active_catalog(incoming))
        sources.append({'archivo':filename,'digest':digest,'fecha':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                        'unidades_ddv':qty,'pop_ddv':len(active_catalog(incoming)),
                        'agregados':new_count,'combinados':merged_count})
        image_mappings.append((filename,content,incoming,mapping))
        reports.append({'Archivo':filename,'Unidades DDV sumadas':qty,
                        'POP nuevos':new_count,'POP combinados':merged_count})
    p['excel_history']=sources
    p['excel_file_digests']=[s['digest'] for s in sources]
    p['source_digest']=sha256('|'.join(p['excel_file_digests']).encode()).hexdigest()
    p['source_name']=' + '.join(s['archivo'] for s in sources)
    p['source_mode']='Asignación consolidada a partir de múltiples Excel'
    p['last_updated']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    p['is_complete']=False
    # Al cambiar la cantidad asignada hay que retirar el tilde físico:
    # el control fue hecho contra la asignación anterior.
    old_qty={x['id']:int(x['cantidad_excel']) for x in previous.get('catalog',[])}
    impacted=[id_ for id_ in list(p.get('physical_checks',{}))
              if int(next((c['cantidad_excel'] for c in p['catalog'] if c['id']==id_),0))!=old_qty.get(id_)]
    if impacted:
        from physical_checks import undo_material
        for id_ in impacted:
            undo_material(p,id_)
            p['physical_events'][-1]['accion']='Verificación invalidada por Excel adicional'
            p['physical_events'][-1]['motivo']='Cambió la asignación consolidada'
    return p,image_mappings,reports


def digest_files(files):
    """Un hash por fotografía/PDF, independiente del nombre del archivo."""
    return [sha256(data).hexdigest() for _,data in files]


def check_new_remitos(period, files):
    """Bloquear contenido repetido incluso si se renombró el PDF/foto."""
    if not files:raise ValueError('No se seleccionaron imágenes ni PDF.')
    if len(files)>20:raise ValueError('Máximo 20 archivos por lote.')
    digests=digest_files(files)
    seen=set(period.get('processed_remito_files',[]))
    # Incorporar historiales anteriores en los que también se registraba el hash.
    for event in period.get('remito_history',[]):
        if event.get('estado','').startswith('OCR aplicado'):
            seen.update(event.get('files_digests',[]))
    repeated=[]
    for (name,_),digest in zip(files,digests):
        if digest in seen or digests.count(digest)>1: repeated.append(name)
    if repeated:
        raise ValueError('Estos archivos ya se habían incorporado o se repitieron en el lote: '+', '.join(sorted(set(repeated)))+'.')
    return digests
