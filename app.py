"""Tablero POP Liviano DDV multitrimestre | GitHub y Streamlit Community Cloud."""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import math
import hmac
import json
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ocr_core import read_documents
from pop_core import catalog_from_excel, integer_quantity, suggest_matches, active_catalog, classify_out_of_scope
from period_store import (PERIOD_RE, archive_bytes, empty_period, merge_quantities,
                          new_source, restore_archive)
from media_core import extract_pop_images, make_scan_previews, image_jpeg
from persistence import make_store, read_zip_assets, write_zip_assets, StorageError
from physical_checks import (approve_material, undo_material, invalidate_changed_checks,
                             clear_checks, reconciled_rows, metrics, to_csv)
from visual_match import visual_candidates, preferred_ocr_ids, choose_material, pending_ocr_indices
from visual_summary import filter_visual_rows, render_visual_matrix
from monthly_core import (MONTH_RE, scope_label, scope_sort, ingest_excels, check_new_remitos, digest_files)
from remito_excel import parse_batch
from convertidor_remitos import make_draft

st.set_page_config(page_title='Control POP liviano · DDV', page_icon='📦',layout='wide')
st.markdown("""<style>
/* Tema accesible: TODOS los textos negros, incluso mensajes, botones,
   menús BaseWeb, formularios, métricas, barra lateral y tablas. */
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stSidebar"] {background-color:#F4F7FC !important; color:#000 !important;}
[data-testid="stSidebar"] {background-color:#FFFFFF !important; border-right:1px solid #CBD5E1;}
.stApp *, [data-testid="stSidebar"] *,
[data-baseweb="popover"] *, [role="listbox"] * {
  color:#000000 !important;
}
.stApp input, .stApp textarea, .stApp select,
.stApp input::placeholder, .stApp textarea::placeholder,
[data-baseweb="popover"], [role="listbox"] {
  color:#000 !important; -webkit-text-fill-color:#000 !important;
}
[data-testid="stMetric"] {background:#FFFFFF; border:1px solid #CBD5E1; border-radius:12px; padding:12px;}
[data-testid="stDataFrame"], [data-testid="stDataEditor"],
[data-testid="stExpander"], [data-testid="stFileUploader"],
[data-testid="stVerticalBlockBorderWrapper"] {color:#000!important;}
.stApp button {color:#000!important; border-radius:8px;}
.stButton > button[kind="primary"],button[data-testid="stBaseButton-primary"] {
 background:#D5E9FF!important;color:#000!important;border-color:#4985BC!important;
}
.stButton > button[kind="primary"]:hover,button[data-testid="stBaseButton-primary"]:hover {
 background:#B9DBFF!important;color:#000!important;
}

/* Streamlit monta los desplegables en portales FUERA de .stApp.
   Forzar el fondo de TODOS los niveles del menú evita texto negro sobre negro,
   incluso si el navegador/tema trae estilos oscuros de BaseWeb. */
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="popover"] ul,
[data-baseweb="popover"] li,
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] [role="option"],
[data-baseweb="menu"],
[role="listbox"],
[role="option"],
[role="listbox"] > div {
  background-color:#FFFFFF !important;
  background:#FFFFFF !important;
  color:#000000 !important;
  -webkit-text-fill-color:#000000 !important;
  color-scheme:light !important;
}
/* Algunos menús BaseWeb crean divs interiores con fondo oscuro propio. */
[data-baseweb="popover"] :is(div,span,p,small,li),
[data-baseweb="menu"] :is(div,span,p,small,li),
[role="listbox"] :is(div,span,p,small,li),
[role="option"] :is(div,span,p,small) {
  color:#000000 !important;
  -webkit-text-fill-color:#000000 !important;
  background-color:transparent !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [role="option"][aria-selected="true"],
[data-baseweb="menu"] [role="option"]:hover,
[role="option"]:hover,
[role="option"][aria-selected="true"],
[role="listbox"] li:hover {background-color:#DDEBFA !important;}
[data-baseweb="popover"] input,
[data-baseweb="popover"] input::placeholder,
[data-baseweb="select"] input,
[data-baseweb="select"] * {
  color:#000000 !important;
  -webkit-text-fill-color:#000000 !important;
}
[data-baseweb="select"] > div,
[data-baseweb="select"] [aria-expanded],
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
  background:#FFFFFF !important;
  color-scheme:light !important;
}
/* El selector y la barra lateral también deben contrastar con la letra negra. */
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stExpander"] [data-baseweb="select"] > div,
[data-testid="stExpander"] summary,
[data-testid="stExpander"] details {
  background:#FFFFFF !important;
  color:#000000 !important;
}

/* Fichas con control físico confirmado: fondo, borde y botón verdes. */
[class*="st-key-pop_fisico_aprobado_"] {background:#DCFCE7!important; border:2px solid #16A34A!important; border-radius:12px; padding:8px;}
[class*="st-key-pop_boton_aprobado_"] button {
 background:#86EFAC!important; border:2px solid #15803D!important;
 color:#000!important; opacity:1!important;
}
/* Texto de SVG Plotly y leyendas de gráficos. */
.js-plotly-plot .plotly svg text {fill:#000000!important;}
</style>""",unsafe_allow_html=True)


def pretty(value):
    return f'{int(value):,}'.replace(',','.')


def period_key(label):
    return label.replace(' ','_')


def labels_for(catalog,aliases):
    return {c['id']:f"{c['id']} | {aliases.get(c['id']) or c['material']} [{c['celda']}]"
            for c in active_catalog(catalog)}


def now_label():
    return datetime.now().strftime('%d/%m/%Y %H:%M')


def make_ocr_table(p, names):
    if p.get('ocr_edited_rows') is not None:
        # Compatibilidad con respaldos JSON anteriores, cuyas tablas no tenían
        # similitud, alertas ni la nueva columna de cantidad OCR sugerida.
        defaults={'Cantidad sugerida (verificar)':None,'Origen cantidad':'', 'Similitud %':None,
                  'Excel sugerido':None,'Diferencia tentativa':None,
                  'Otras opciones':'','Alertas del match':'', 'Ignorar':False}
        return [{**defaults,**row} for row in p['ocr_edited_rows']]
    table=[]
    for x in p['ocr_rows']:
        suggestions=x.get('alternativas',[])
        options=' · '.join(f"{names.get(a['id'],a['id']).split(' | ',1)[-1][:32]} ({round(a['score'])}%)"
                           for a in suggestions[1:3])
        qty=x.get('cantidad')
        excel_qty=x.get('cantidad_excel_sugerida')
        table.append({
            'Página':x.get('pagina',''),
            'Cantidad':qty,
            'Cantidad sugerida (verificar)':x.get('cantidad_sugerida'),
            'Origen cantidad':x.get('origen_cantidad',''),
            'Descripción remito':x.get('detalle',''),
            'Material Excel':names.get(x.get('id',''),'(sin asignar)'),
            'Sugerencia':names.get(x.get('sugerido',''),'—'),
            'Similitud %':x.get('puntaje',0),
            'Excel sugerido':excel_qty,
            'Diferencia tentativa': (qty-excel_qty) if qty is not None and excel_qty is not None else None,
            'Otras opciones':options,
            'Alertas del match':' / '.join(x.get('alertas_match',[])),
            'Lectura':x.get('estado_match',''),
            'Ignorar':bool(x.get('fuera_ddv'))})
    return table


def confirm_ocr_rows(edited, catalog_ids):
    amounts=defaultdict(int);unknown=[];count=0
    for r in edited:
        if bool(r.get('Ignorar',False)):continue
        option=str(r.get('Material Excel','') or '')
        identity=option.split(' | ',1)[0] if ' | ' in option else ''
        n=integer_quantity(r.get('Cantidad'))
        if identity in catalog_ids and n is not None:
            amounts[identity]+=n;count+=1
        else:
            unknown.append({'Página':r.get('Página',''), 'Cantidad':n,
                'Descripción':r.get('Descripción remito',''),
                'Motivo':'Cantidad sin verificar' if n is None else 'Material sin asignar'})
    return dict(amounts),unknown,count


def _seed_assets():
    data_dir=Path(__file__).resolve().parent/'data'
    q3=read_zip_assets((data_dir/'q3_gallery.zip').read_bytes())
    mapping=json.loads((data_dir/'q3_pop_map.json').read_text(encoding='utf-8'))
    return q3,mapping


def initialize():
    if 'pop_store' not in st.session_state:
        try: secrets=dict(st.secrets)
        except Exception: secrets={}
        store,mode=make_store(secrets)
        st.session_state.pop_store=store
        st.session_state.storage_mode=mode
    if 'pop_periods' not in st.session_state:
        baseline=json.loads((Path(__file__).resolve().parent/'data'/'q3_2026_preliminar.json').read_text(encoding='utf-8'))
        q3=empty_period();q3.update(baseline)
        q3_assets,pop_map=_seed_assets()
        q3['pop_images']=pop_map
        q3['remito_history']=[{
            'id':'q3_base','fecha':'Q3 2026 (precargado)',
            'accion':'Remito Q3 precargado','archivos':['Remito Q3 2026 (fotografía original)'],
            'paginas':1,'filas_ocr':0,'filas_aplicadas':0,'sin_conciliar':0,
            'estado':'Preliminar · requiere verificación',
            'imagen_keys':['remitos/q3_base/pagina_01.jpg'],'firma':'q3_base'}]
        q3['pending_remito_id']=None
        current_month=datetime.now().strftime('%Y-%m')
        periods={'Q3 2026':q3,'Q4 2026':empty_period(),current_month:empty_period()}
        assets={'Q3 2026':q3_assets,'Q4 2026':{},current_month:{}}
        st.session_state.load_error=''
        try:
            raw=st.session_state.pop_store.load()
            if raw:
                restored=restore_archive(raw)
                periods.update(restored)
                for label in restored:
                    retrieved=st.session_state.pop_store.load_assets(label)
                    if retrieved is not None:assets[label]=retrieved
                # Compatibilidad con estados antiguos sin mapa de miniaturas.
                if not periods['Q3 2026'].get('pop_images'):
                    periods['Q3 2026']['pop_images']=pop_map
                assets['Q3 2026']={**q3_assets,**assets.get('Q3 2026',{})}
        except Exception as e:
            st.session_state.load_error=str(e)
        if not periods['Q3 2026'].get('pop_images') and periods['Q3 2026'].get('source_mode')=='Q3 2026 precargado':
            periods['Q3 2026']['pop_images']=pop_map
        if not periods['Q3 2026'].get('remito_history') and periods['Q3 2026'].get('source_mode')=='Q3 2026 precargado':
            periods['Q3 2026']['remito_history']=q3['remito_history']
        st.session_state.pop_periods=periods
        st.session_state.pop_assets=assets
        st.session_state.dirty_assets=set()
    if st.session_state.get('next_period_load') in st.session_state.pop_periods:
        st.session_state.period_load=st.session_state.pop('next_period_load')
    if st.session_state.get('next_period_view') in st.session_state.pop_periods:
        st.session_state.period_view=st.session_state.pop('next_period_view')
    if 'period_load' not in st.session_state or st.session_state.period_load not in st.session_state.pop_periods:
        st.session_state.period_load=datetime.now().strftime('%Y-%m')
    if 'period_view' not in st.session_state or st.session_state.period_view not in st.session_state.pop_periods:
        st.session_state.period_view=datetime.now().strftime('%Y-%m')


def persist_changes(*,assets_changed=(),rerun=True):
    st.session_state.dirty_assets.update(assets_changed)
    try:
        st.session_state.pop_store.save(st.session_state.pop_periods,
            st.session_state.pop_assets,st.session_state.dirty_assets)
    except Exception as e:
        st.error(f'⚠️ No se pudo guardar el cambio: {e}. Sigue en la sesión. Reintentá con «Guardar cambios pendientes».')
        return False
    st.session_state.dirty_assets.clear()
    st.session_state.last_saved=now_label()
    if rerun:st.rerun()
    return True


def asset_key(cid):
    return 'pop/'+sha256(cid.encode('utf-8')).hexdigest()[:20]+'.jpg'


def register_remito(p, signature, names, files, photo_keys, rows_count):
    identifier=sha256((signature+datetime.now().isoformat()).encode()).hexdigest()[:18]
    p.setdefault('remito_history',[]).append({
        'id':identifier,'fecha':now_label(),'accion':p['ocr_operation'],
        'archivos':list(names),'paginas':len(photo_keys),'filas_ocr':rows_count,
        'filas_aplicadas':0,'sin_conciliar':0,'estado':'OCR pendiente de revisión',
        'imagen_keys':photo_keys,'firma':signature})
    p['pending_remito_id']=identifier
    return identifier


try:
    _gate=dict(st.secrets).get('APP_PASSWORD','')
except Exception:_gate=''
if _gate and not st.session_state.get('access_authorized',False):
    st.title('🔒 Control POP liviano · DDV')
    password_input=st.text_input('Contraseña de acceso al tablero',type='password')
    if st.button('Ingresar'):
        if hmac.compare_digest(str(password_input),str(_gate)):
            st.session_state.access_authorized=True
            st.rerun()
        else:st.error('Contraseña incorrecta')
    st.stop()

initialize()
periods=st.session_state.pop_periods
st.title('📦 Control de POP liviano')
st.caption('Remitos vs. asignación POP · Solo Distribuidora del Valle S.A. · Meses consolidados e históricos Q3/Q4 independientes')

with st.sidebar:
    st.markdown('### Control DDV')
    if st.session_state.storage_mode=='github':
        if st.session_state.load_error:st.warning('GitHub configurado, pero la conexión falló. Corregí el token/repo antes de confiar en el guardado.')
        else:st.success('☁️ Guardado permanente activo · GitHub privado')
    elif st.session_state.storage_mode=='incompleto':
        st.error('Guardado remoto sin configurar: faltan datos de GitHub.')
    else:
        st.warning('⚠️ Almacenamiento local: en Streamlit Cloud se pierde al reiniciar. Configurá GitHub privado para guardar permanentemente.')
    if st.session_state.load_error:
        st.error('No se pudo recuperar el historial remoto: '+st.session_state.load_error)
    if st.button('💾 Guardar cambios pendientes',use_container_width=True):
        if persist_changes(rerun=False):st.success('Estado guardado correctamente.')
    periods_ordered=sorted(periods,key=scope_sort)
    load_period=st.selectbox('📥 Mes / período de carga',periods_ordered,
                             format_func=scope_label,key='period_load')
    view_period=st.selectbox('📊 Mes / período de resultados',periods_ordered,
                             format_func=scope_label,key='period_view')
    with st.expander('📅 Crear un mes para consolidar',expanded=False):
        chosen_month=st.date_input('Elegí una fecha del mes',value=datetime.now().date(),
                                  key='month_creation')
        month_id=chosen_month.strftime('%Y-%m')
        if st.button('Crear / seleccionar mes',use_container_width=True):
            if month_id not in periods:
                periods[month_id]=empty_period()
                st.success(f'{scope_label(month_id)} creado.')
            st.session_state.next_period_load=month_id
            st.session_state.next_period_view=month_id
            persist_changes()
    with st.expander('Crear otro trimestre',expanded=False):
        label=st.text_input('Nuevo período (ej. Q1 2027)',placeholder='Q1 2027',key='new_period_label').strip().upper()
        if st.button('Agregar período',use_container_width=True):
            if not PERIOD_RE.fullmatch(label):st.error('Formato requerido: Q1 2027, Q2 2027, etc.')
            elif label in periods:st.warning('El período ya existe.')
            else:
                periods[label]=empty_period()
                st.session_state.next_period_load=label
                st.session_state.next_period_view=label
                persist_changes()
    st.divider()
    uploading=periods[load_period]
    with st.expander('0 · Convertir fotografía/PDF a Excel (borrador)',expanded=False):
        st.caption('Paso opcional, ANTES de la carga. La lectura OCR solo prepara un Excel editable: '
                   'no ingresa cantidades en el tablero. Para imágenes de remitos distintos, '
                   'generá un Excel por cada número de remito.')
        input_scans=st.file_uploader('Foto o PDF de UN remito (puede tener varias páginas)',
            type=['jpg','jpeg','png','webp','pdf'],accept_multiple_files=True,
            key='draft_remito_scans')
        draft_number=st.text_input('Número de remito',placeholder='00015743',key='draft_remito_number')
        draft_date=st.date_input('Fecha del remito',key='draft_remito_date')
        two_cols_draft=st.checkbox('El remito tiene dos columnas',value=True,key='draft_two_columns')
        if st.button('Convertir a Excel para corregir',use_container_width=True,
                     disabled=not input_scans or not draft_number):
            try:
                with st.spinner('Extrayendo renglones para crear el BORRADOR Excel…'):
                    report=read_documents([(f.name,f.getvalue()) for f in input_scans],
                                          two_columns=two_cols_draft,max_pages=20)
                    payload=make_draft(report.rows,draft_number,draft_date.strftime('%Y-%m-%d'))
                st.session_state['draft_excel_download']=(payload,draft_number)
                st.success(f'Borrador con {len(report.rows)} filas generado. Revisalo en Excel antes de importarlo.')
                for warning in report.warnings:st.warning(warning)
            except Exception as exc:st.error(f'No se pudo convertir: {exc}')
        if st.session_state.get('draft_excel_download'):
            buffer,number=st.session_state['draft_excel_download']
            st.download_button('⬇️ Descargar Excel BORRADOR para revisión',buffer,
                file_name=f'Remito_{number}_BORRADOR_REVISAR.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True)
    st.markdown(f'**Carga de {load_period}**')
    if uploading['catalog']:
        assigned=sum(int(c['cantidad_excel']) for c in active_catalog(uploading['catalog']))
        st.success(f'{len(active_catalog(uploading["catalog"]))} POP asignados a DDV · {pretty(assigned)} unidades asignadas')
        st.caption(f'Excel: {uploading["source_name"]}')
    else:st.warning('Todavía no se cargó el Excel de este período.')
    if uploading.get('excel_history'):
        with st.expander(f'Excel registrados ({len(uploading["excel_history"])})'):
            st.dataframe(pd.DataFrame([{'Archivo':e.get('archivo',''),
                'Unidades DDV añadidas':e.get('unidades_ddv',0),
                'POP sumados':e.get('combinados',0),
                'POP nuevos':e.get('agregados',0),
                'Fecha':e.get('fecha','')}
                for e in uploading['excel_history']]),use_container_width=True,hide_index=True)
    uploaded_excels=st.file_uploader(
        '1 · Subir VARIOS Excel de asignación del mes',type=['xlsx'],
        accept_multiple_files=True,key=f'xl_{period_key(load_period)}',
        help='Se permite añadir varios archivos en un lote y repetir el proceso durante el mes.')
    excel_op=st.radio('Cómo incorporar los Excel',[
        'Sumar Excel de entregas nuevas al consolidado',
        'Reemplazar la asignación consolidada del período'],
        key=f'excel_mode_{period_key(load_period)}',
        help='No sumes archivos que sean dos versiones acumuladas de la misma asignación.',
        horizontal=False)
    if excel_op.startswith('Reemplazar'):
        st.warning('Reemplazar reinicia asignaciones, lecturas de remito y verificaciones de este período. Los demás meses no cambian.')
    else:
        st.info('Cada Excel debe corresponder a un lote adicional del mes. Si contiene un acumulado de entregas anteriores, NO lo sumes para evitar duplicaciones.')
    if st.button('📚 Consolidar Excel del período',disabled=not uploaded_excels,use_container_width=True):
        try:
            excel_files=[(f.name,f.getvalue()) for f in uploaded_excels]
            replace=excel_op.startswith('Reemplazar')
            new_state,mappings,report=ingest_excels(uploading,excel_files,catalog_from_excel,replace=replace)
            # Preparar imágenes en una copia temporal: si una falla, no se tocan
            # fotos ni datos del control anterior.
            img_assets={} if replace else dict(st.session_state.pop_assets.get(load_period,{}))
            img_map=new_state.setdefault('pop_images',{})
            photos_count=0
            for name,binary,incoming,id_map in mappings:
                photos=extract_pop_images(binary,incoming)
                for original_id,picture in photos.items():
                    cid=id_map[original_id]
                    if cid not in img_map:
                        key=asset_key(cid)
                        img_assets[key]=picture
                        img_map[cid]=key
                        photos_count+=1
            periods[load_period]=new_state
            st.session_state.pop_assets[load_period]=img_assets
            st.session_state.next_period_view=load_period
            st.success(f'{len(report)} Excel incorporados · {photos_count} fotos nuevas · '+
                       f'{pretty(sum(x["cantidad_excel"] for x in active_catalog(new_state["catalog"])))} unidades DDV consolidadas.')
            persist_changes(assets_changed=[load_period])
        except Exception as ex:
            st.error(f'No se pudieron consolidar los Excel. No se aplicó la carga: {ex}')
    st.divider()
    st.markdown('### 2 · Excel de remitos revisados')
    st.caption('Convertí cada foto/PDF a Excel, corregí las cantidades en la planilla y subí únicamente los archivos revisados. '
               'La foto ya no se interpreta al consolidar. Los Excel de asignación se cargan en el paso 1.')
    uploaded_receipts=st.file_uploader(
        'Subir VARIOS Excel de remitos (uno por remito, hasta 20 por lote)',
        type=['xlsx'],accept_multiple_files=True,key=f'remitos_xlsx_{period_key(load_period)}',
        help='Cada archivo debe tener una pestaña REMITO con REMITO, FECHA, DESCRIPCION POP y CANTIDAD.')
    receipt_operation=st.radio('Acción para estos remitos',[
        'Agregar un remito nuevo al período',
        'Reemplazar cantidades anteriores'],
        key=f'receipt_operation_{period_key(load_period)}',
        index=1 if uploading.get('source_mode')=='Q3 2026 precargado' and not uploading.get('remito_excel_history') else 0)
    if uploading.get('remito_excel_history'):
        with st.expander(f'Remitos Excel incorporados ({len(uploading["remito_excel_history"])})'):
            st.dataframe(pd.DataFrame([
                {'Archivo':e.get('archivo'), 'Remito':', '.join(e.get('remitos',[])),
                 'Filas':e.get('filas',0), 'Fecha de registro':e.get('cargado','')}
                for e in uploading['remito_excel_history']]),hide_index=True,use_container_width=True)
    if receipt_operation.startswith('Reemplazar'):
        st.warning('Reemplazar reinicia las cantidades recibidas del período cuando apliques esta revisión; '
                   'no cambia las asignaciones del Excel ni los otros meses.')
    confirm_review=st.checkbox('Confirmo que revisé los Excel contra sus remitos originales',
                               key=f'confirm_receipts_{period_key(load_period)}')
    if st.button('📄 Preparar conciliación desde los Excel revisados',type='primary',
                 disabled=not uploaded_receipts or not uploading['catalog'] or not confirm_review,
                 use_container_width=True):
        try:
            files=[(f.name,f.getvalue()) for f in uploaded_receipts]
            replace=receipt_operation.startswith('Reemplazar')
            old_history=[] if replace else uploading.get('remito_excel_history',[])
            parsed,source_rows=parse_batch(files,period=load_period,existing_history=old_history)
            signature=sha256('|'.join(f['digest'] for f in parsed).encode()).hexdigest()
            with st.spinner('Vinculando las descripciones revisadas con los POP asignados a DDV…'):
                suggestions=suggest_matches(source_rows,active_catalog(uploading['catalog']),uploading['aliases'])
                suggestions=classify_out_of_scope(suggestions,uploading['catalog'],uploading['aliases'])
            previous_id=uploading.get('pending_remito_id')
            if previous_id:
                for ev in uploading.get('remito_history',[]):
                    if ev.get('id')==previous_id and 'pendiente' in ev.get('estado','').lower():
                        ev['estado']='Reemplazado sin aplicar'
            uploading.update(
                ocr_rows=suggestions,ocr_raw='Importación desde Excel revisado (sin OCR automático en el tablero)',
                ocr_warnings=[f'{sum(x["cantidad_heredada"] for x in source_rows)} cantidades por continuidad: '
                              'confirmar que fueron revisadas en el Excel.'],
                ocr_previews=[],ocr_edited_rows=None,ocr_edit_ver=0,
                ocr_version=uploading['ocr_version']+1,ocr_signature=signature,
                ocr_operation=receipt_operation,
                ocr_base_entries={} if replace else deepcopy(uploading['remito_entries']),
                ocr_file_digests=[f['digest'] for f in parsed],
                remito_files=[f['nombre'] for f in parsed],
                ocr_excel_meta=[{'archivo':x['nombre'],'digest':x['digest'],
                                 'remitos':x['remitos'],'meses':x['meses'],'filas':len(x['filas'])}
                                for x in parsed]
            )
            st.session_state.next_period_view=load_period
            event_id=register_remito(uploading,signature,[name for name,_ in files],files,[],len(suggestions))
            for ev in uploading['remito_history']:
                if ev['id']==event_id:
                    ev.update(estado='Excel pendiente de revisión',tipo='Excel revisado',
                              remitos=sorted({n for x in parsed for n in x['remitos']}),
                              files_digests=[x['digest'] for x in parsed])
                    break
            uploading['last_updated']=now_label()
            st.success(f'{len(files)} Excel de remitos preparados · {len(source_rows)} filas. '
                       'Verificá los vínculos «Material Excel» y pulsá «Aplicar revisión».')
            persist_changes()
        except Exception as ex:
            st.error(f'No se pudieron importar los remitos Excel: {ex}')
    st.divider()
    st.markdown('**Historial de períodos**')
    history=[]
    for label in periods_ordered:
        entry=periods[label]
        registered=len(entry['remito_entries'])
        if entry['catalog']:
            status='Revisado' if entry['is_complete'] else ('Provisional' if registered else 'Sin remito')
        else:status='Sin Excel'
        history.append({'Período':label,'Estado':status,'Materiales':registered})
    st.dataframe(pd.DataFrame(history),hide_index=True,use_container_width=True)
    st.download_button('💾 Descargar historial de meses y trimestres (JSON)',archive_bytes(periods),
        file_name='POP_DDV_historial_todos_los_periodos.json',mime='application/json',use_container_width=True)
    history_upload=st.file_uploader('Restaurar historial guardado',type=['json'],key='restore_all')
    if st.button('Restaurar historial',disabled=history_upload is None,use_container_width=True):
        try:
            restored=restore_archive(history_upload.getvalue())
            if not restored:raise ValueError('El archivo no contiene períodos.')
            # Los períodos faltantes en el respaldo se conservan; los presentes se reemplazan.
            periods.update(restored)
            if 'Q3 2026' in restored and not periods['Q3 2026'].get('pop_images') and periods['Q3 2026'].get('source_mode')=='Q3 2026 precargado':
                _,seed_mapping=_seed_assets()
                periods['Q3 2026']['pop_images']=seed_mapping
            if st.session_state.period_load not in periods:st.session_state.period_load=next(iter(periods))
            if st.session_state.period_view not in periods:st.session_state.period_view=next(iter(periods))
            st.success('Historial recuperado correctamente.')
            persist_changes()
        except Exception as ex:st.error(f'No se pudo restaurar el historial: {ex}')
    with st.expander('Restaurar imágenes guardadas (ZIP)'):
        pictures_zip=st.file_uploader('Archivo ZIP de imágenes exportado',type=['zip'],key=f'restore_photos_{period_key(load_period)}')
        if st.button('Restaurar imágenes de este período',disabled=pictures_zip is None):
            try:
                restored_assets=read_zip_assets(pictures_zip.getvalue())
                st.session_state.pop_assets.setdefault(load_period,{}).update(restored_assets)
                if not periods[load_period].get('pop_images'):
                    st.warning('Para recuperar las asociaciones de las imágenes POP también hay que restaurar su historial JSON.')
                persist_changes(assets_changed=[load_period])
            except Exception as ex:st.error(f'No se pudo restaurar el ZIP: {ex}')
    st.caption('Los controles y las imágenes se guardan al realizar cambios. Para persistencia real en Streamlit Cloud: repositorio de datos privado configurado en Secrets.')

st.markdown(f'### Resultados · {view_period}')
if load_period!=view_period:
    st.info(f'Estás **cargando en {load_period}** y **consultando {view_period}**. Las operaciones de carga no modifican el período que estás viendo.')

p=periods[view_period]
catalog=active_catalog(p['catalog'])
if not catalog:
    st.warning(f'No hay Excel cargado para {view_period}. Seleccionalo como «Período de carga» y subí su archivo.')
    st.stop()

include_hidden=st.checkbox('Incluir hojas ocultas del Excel',value=True,key=f'hidden_{period_key(view_period)}')
rows=reconciled_rows(p,include_hidden)
summary=metrics(rows)
cols=st.columns(5)
for col,name,value in zip(cols,['Asignado DDV','Remito conciliado','Coinciden','Diferencias','Pendientes'],
                          [pretty(summary['asignado']),pretty(summary['recibido']),summary['coinciden'],summary['diferencias'],summary['pendientes']]):
    col.metric(name,value)
if summary['verificados_fisicos']:
    st.success(f'✅ {summary["verificados_fisicos"]} materiales verificados físicamente · '
               f'{pretty(summary["recibido"])} unidades conciliadas · '
               f'Lectura original de remitos: {pretty(summary["remito_original"])} unidades. '
               'La lectura original se mantiene intacta para auditoría.')
if p['preliminary']:
    if p['source_mode']=='Q3 2026 precargado':
        st.warning('**Q3 precargado · cifras provisionales:** la transcripción anterior de la foto no fue certificada. Podés reemplazarla subiendo un Excel de remito revisado en «Período de carga: Q3 2026».')
    else:
        st.warning('**Control preliminar:** las cantidades fueron cargadas, pero falta confirmar la revisión completa del remito.')
if p['ocr_rows'] and p['ocr_signature'] not in p['processed_signatures']:
    st.info('Hay una carga de Excel de remitos **pendiente de revisión y aplicación** para este período; las cifras de arriba todavía corresponden al control anterior.')
if p['is_complete']:
    st.success('Remito marcado como completamente revisado; los materiales sin registro pasan a contabilizarse como faltantes.')
elif p['remito_entries']:
    st.caption('Conciliación preliminar: un material no leído aparece pendiente, no como recibido en cero.')
else:
    st.info('Faltan cantidades del remito. Seleccioná este período para cargar el Excel de remito revisado.')
if p['unmatched']:
    st.error(f'Hay {len(p["unmatched"])} líneas de remito no conciliadas. Revisalas antes de cerrar el remito.')

names=labels_for(catalog,p['aliases'])
valid_ids=set(names)
options=['(sin asignar)']+list(names.values())

page_summary,page_ocr,page_items,page_gallery,page_history,page_labels,page_export=st.tabs([
    '📊 Resumen','📄 Revisión Excel de remitos','🧾 Control por material',
    '🖼️ Galería de POP','📑 Remitos registrados','🏷️ Nombres de materiales','📥 Exportar / auditar'])

with page_summary:
    # Tabla visual, al estilo de las hojas del Excel: cada columna es un POP.
    st.subheader(f'Planilla visual de POP · {scope_label(view_period)}')
    if MONTH_RE.fullmatch(view_period):
        st.caption(f'Consolidado mensual: {len(p.get("excel_history",[]))} Excel registrados · '
                   f'{len([e for e in p.get("remito_history",[]) if e.get("estado","").startswith(("OCR aplicado","Excel aplicado"))])} lotes de remitos aplicados. '
                   'Los totales se suman únicamente dentro de este mes.')
    st.caption('Solo POP asignados con unidades a DDV: foto arriba y cantidades debajo. '
               'La diferencia y el estado reflejan las tildes de verificación física de la galería. '
               'El remito original nunca se modifica.')
    sheet_options=['Todas las hojas'] + list(dict.fromkeys(r['hoja'] for r in rows))
    matrix_col_sheet,matrix_col_status=st.columns([3,2])
    sheet_filter=matrix_col_sheet.selectbox('Hoja / familia del Excel',sheet_options,
                                           key=f'visual_resumen_hoja_{period_key(view_period)}')
    status_options=['Todos','Pendientes y diferencias','Coinciden','Verificados físicamente',
                    'Faltante','Sobrante','Pendiente']
    status_filter=matrix_col_status.selectbox('Estado de conciliación',status_options,
                                             key=f'visual_resumen_estado_{period_key(view_period)}')
    matrix_col_query,matrix_col_n=st.columns([3,1])
    search_filter=matrix_col_query.text_input('Buscar POP por marca, medida o campaña',
                                              placeholder='Ej.: CENEFA 20X7, BRAHMA, STELLA…',
                                              key=f'visual_resumen_buscar_{period_key(view_period)}')
    page_size=matrix_col_n.selectbox('POP por página',[4,6,8,12],
                                      key=f'visual_resumen_paginacion_{period_key(view_period)}')
    show_zero=False  # El usuario pide catálogo DDV positivo exclusivamente.
    matrix_rows=filter_visual_rows(rows,p.get('aliases',{}),sheet_filter,status_filter,search_filter,show_zero)
    total_pages=max(1,math.ceil(len(matrix_rows)/page_size))
    matrix_page_key=f'visual_resumen_pagina_{period_key(view_period)}'
    if st.session_state.get(matrix_page_key,1)>total_pages:
        st.session_state[matrix_page_key]=total_pages
    matrix_page=st.number_input('Página de materiales',min_value=1,max_value=total_pages,
                                step=1,key=matrix_page_key)
    active_rows=matrix_rows[(matrix_page-1)*page_size:matrix_page*page_size]
    st.caption(f'{len(matrix_rows)} materiales encontrados · Página {matrix_page} de {total_pages} · '
               'Desplazá horizontalmente la planilla si la pantalla es angosta.')
    if active_rows:
        st.markdown(render_visual_matrix(active_rows,p.get('aliases',{}),p.get('pop_images',{}),
                                         st.session_state.pop_assets.get(view_period,{})),
                    unsafe_allow_html=True)
        st.caption('Asignado DDV = Excel. Remito original = lectura conservada. '
                   'Remito conciliado = lectura o cantidad confirmada físicamente. '
                   '— significa que todavía no existe una cantidad comprobada.')
    else:
        st.info('No hay materiales con esos filtros; probá otra hoja o estado.')
    st.divider()
    st.subheader(f'Conciliación por hoja · {view_period}')
    grouped=defaultdict(lambda:{'asignado':0,'recibido':0,'coinciden':0,'diferencias':0,'pendientes':0})
    for r in rows:
        g=grouped[r['hoja']]
        g['asignado']+=r['cantidad_excel']
        g['recibido']+=r['cantidad_remito'] or 0
        g['coinciden']+=int(r['estado']=='Coincide')
        g['diferencias']+=int(r['estado'] in ('Faltante','Sobrante'))
        g['pendientes']+=int(r['estado']=='Pendiente')
    ordered=sorted([(key,val) for key,val in grouped.items() if val['asignado'] or val['recibido']],
                   key=lambda e:e[1]['asignado'],reverse=True)
    if ordered:
        chart=go.Figure()
        for title,key,color in [('Excel asignado','asignado','#266FBA'),('Remito conciliado','recibido','#E6A144')]:
            chart.add_trace(go.Bar(name=title,x=[x[key] for _,x in ordered],y=[label for label,_ in ordered],
                                   marker_color=color,orientation='h'))
        chart.update_layout(barmode='group',height=max(350,40*len(ordered)+110),
                            margin=dict(l=10,r=8,t=6,b=18),legend=dict(orientation='h',y=1.07),
                            plot_bgcolor='#fff',paper_bgcolor='#fff',font=dict(color='#000000'),yaxis=dict(autorange='reversed'),
                            xaxis=dict(title='Unidades',gridcolor='#E7EDF4'))
        st.plotly_chart(chart,use_container_width=True,config={'displayModeBar':False})
    cc,dd=st.columns(2)
    cc.metric('Unidades faltantes registradas',pretty(summary['faltan_unidades']))
    dd.metric('Unidades sobrantes registradas',pretty(summary['sobran_unidades']))
    attention=[r for r in rows if r['estado'] in ('Pendiente','Faltante','Sobrante')]
    st.markdown('**Materiales que requieren atención**')
    if attention:
        st.dataframe(pd.DataFrame([{'Estado':r['estado'],'Hoja':r['hoja'],'Material':p['aliases'].get(r['id']) or r['material'],
            'Excel':r['cantidad_excel'],'Remito conciliado':r['cantidad_remito'],'Remito original':r['cantidad_remito_original'],
            'Control físico':'Sí' if r['verificacion_fisica'] else 'No', 'Diferencia':r['diferencia'],'Celda':r['celda']}
            for r in sorted(attention,key=lambda r:(r['estado']=='Pendiente',-r['cantidad_excel']))]),
            hide_index=True,use_container_width=True,height=min(550,40*len(attention)+50))
    else:st.success('No hay diferencias ni renglones pendientes en el alcance seleccionado.')
    st.markdown('**Resultado por pestaña del Excel**')
    st.dataframe(pd.DataFrame([{'Hoja':label,'Asignado':g['asignado'],'Remito':g['recibido'],
        'Coinciden':g['coinciden'],'Diferencias':g['diferencias'],'Pendientes':g['pendientes']}
        for label,g in grouped.items()]),hide_index=True,use_container_width=True)
    other=[(key,item) for key,item in periods.items() if key!=view_period and item['catalog']]
    if other:
        with st.expander('Comparar indicadores con otros meses o trimestres',expanded=False):
            compare=[]
            for label,item in [(view_period,p)]+other:
                report=metrics(reconciled_rows(item,include_hidden))
                compare.append({'Período':label,'Asignado':report['asignado'],'Remito conciliado':report['recibido'],
                    'Coinciden':report['coinciden'],'Diferencias':report['diferencias'],
                    'Pendientes':report['pendientes'],
                    'Control':'Revisado' if item['is_complete'] else 'Provisional'})
            st.dataframe(pd.DataFrame(compare),hide_index=True,use_container_width=True)

with page_ocr:
    st.subheader(f'Revisar coincidencias de Excel de remitos · {view_period}')
    st.caption('Las cantidades vienen de los Excel de remitos ya revisados. El sistema solo sugiere la correspondencia con el Excel de asignación DDV; no modifica cantidades para forzar coincidencias.')
    for warning in p['ocr_warnings']:st.warning(warning)
    if not p['ocr_rows']:
        st.info('Todavía no hay un Excel de remito para revisar. Elegí este período en «Período de carga» y subí uno o más archivos .xlsx.')
    else:
        ocr=p['ocr_rows']
        q1,q2,q3=st.columns(3)
        q1.metric('Renglones de remito',len(ocr));q2.metric('Con cantidad',sum(x.get('cantidad') is not None for x in ocr))
        q3.metric('Con material sugerido',sum(bool(x.get('sugerido')) for x in ocr))
        outside=[x for x in ocr if x.get('fuera_ddv')]
        if outside:
            st.warning(f'{len(outside)} referencias del remito tienen asignación DDV=0. Quedaron marcadas como «Ignorar» de forma reversible; no suman al recibido DDV.')
            with st.expander('Ver detalle de material fuera de asignación DDV'):
                st.dataframe(pd.DataFrame([{'Remito':x.get('detalle'),'Cantidad':x.get('cantidad'),
                    'Motivo':x.get('razon_fuera_ddv')} for x in outside]),hide_index=True,use_container_width=True)
        st.info('**Cantidad por continuidad:** el Excel indica qué cifras se heredaron. Verificá **Origen cantidad** y comprobá la correspondencia de materiales antes de confirmar.')
        st.caption(f'Acción seleccionada para esta lectura: **{p["ocr_operation"]}**. Reaplicar la misma tabla no suma dos veces los materiales.')
        st.markdown('**Revisá las propuestas de coincidencia.** La cantidad procede del Excel que ya controlaste. Si el POP elegido no es correcto, elegí otro en **Material Excel** o utilizá las fotografías del selector visual.')
        # Edición en vivo: guarda el borrador en la sesión, sin aplicar al remito
        # hasta confirmar. Esto permite seleccionar imágenes SIN perder correcciones
        # realizadas en la misma tabla.
        draft_key=f'ocr_draft_{period_key(view_period)}_{p["ocr_version"]}_{p["ocr_edit_ver"]}'
        editor_rev_key=f'ocr_editor_rev_{period_key(view_period)}_{p["ocr_version"]}_{p["ocr_edit_ver"]}'
        if draft_key not in st.session_state:
            st.session_state[draft_key]=make_ocr_table(p,names)
        if editor_rev_key not in st.session_state:
            st.session_state[editor_rev_key]=0
        editor_key=f'ocr_editor_{period_key(view_period)}_{p["ocr_version"]}_{p["ocr_edit_ver"]}_{st.session_state[editor_rev_key]}'
        edited=st.data_editor(pd.DataFrame(st.session_state[draft_key]),
            use_container_width=True,hide_index=True,key=editor_key,
            height=525,num_rows='dynamic',
            column_order=['Página','Cantidad','Origen cantidad','Cantidad sugerida (verificar)','Descripción remito',
                          'Material Excel','Sugerencia','Similitud %','Excel sugerido','Diferencia tentativa','Alertas del match','Otras opciones','Lectura','Ignorar'],
            column_config={
                'Origen cantidad':st.column_config.TextColumn('Origen cantidad',
                    help='Señala si la cifra estaba impresa o si se heredó de otro renglón. Verificá la foto.'),
                'Cantidad':st.column_config.NumberColumn('Cantidad',min_value=0,step=1,format='%d',
                   help='Cifra leída o corregida. Nunca se reemplaza automáticamente por la del Excel.'),
                'Cantidad sugerida (verificar)':st.column_config.NumberColumn(
                   'Cifra OCR dudosa',format='%d',help='El OCR confundió caracteres como S y 5. Revisá la foto y escribí la cifra confirmada en Cantidad.'),
                'Similitud %':st.column_config.NumberColumn('Similitud %',format='%d%%',
                   help='Puntaje aproximado de similitud de descripción, no de cantidad ni de recepción.'),
                'Excel sugerido':st.column_config.NumberColumn('Excel sugerido',format='%d'),
                'Diferencia tentativa':st.column_config.NumberColumn('Diferencia tentativa',format='%d'),
                'Descripción remito':st.column_config.TextColumn('Descripción remito',width='large'),
                'Material Excel':st.column_config.SelectboxColumn('Material Excel',options=options,width='large'),
                'Sugerencia':st.column_config.TextColumn('Sugerencia',width='large'),
                'Página':st.column_config.TextColumn('Página',width='medium'),
                'Ignorar':st.column_config.CheckboxColumn('Ignorar',default=False)},
            disabled=['Página','Sugerencia','Similitud %','Excel sugerido','Diferencia tentativa',
                      'Cantidad sugerida (verificar)','Origen cantidad','Alertas del match','Otras opciones','Lectura'])
        # Guardar en sesión también las cantidades recién editadas antes de abrir
        # el selector visual: el botón elige el POP sobre ESTA versión de la tabla.
        st.session_state[draft_key]=edited.to_dict('records')
        with st.expander('🖼️ Elegir material por su foto (selector visual de Material Excel)',expanded=True):
            draft=st.session_state[draft_key]
            if draft:
                pending_rows=pending_ocr_indices(draft)
                st.caption(f'**{len(pending_rows)} filas pendientes de asignación** · '
                           'Las filas desaparecen del selector apenas elegís su POP. '
                           'Si querés revisar o cambiar una ya asignada, usá la tabla de arriba.')
                if pending_rows:
                    # La firma cambia cuando desaparece una fila: evita conservar
                    # una selección obsoleta en el widget tras un rerun de Streamlit.
                    pending_signature=sha256(','.join(map(str,pending_rows)).encode('utf-8')).hexdigest()[:12]
                    current_row=st.selectbox(
                        '1 · Elegí solo una fila SIN ASIGNAR del remito',
                        pending_rows,
                        format_func=lambda i: f"Fila {i+1} · {str(draft[i].get('Descripción remito') or 'Sin descripción')[:75]} · "
                                              f"Cantidad: {draft[i].get('Cantidad') if integer_quantity(draft[i].get('Cantidad')) is not None else 'sin verificar'}",
                        key=f'visual_ocr_row_{period_key(view_period)}_{p["ocr_version"]}_{p["ocr_edit_ver"]}_{pending_signature}')
                    selected_ocr=draft[current_row]
                    st.caption('Excel del remito: '+str(selected_ocr.get('Descripción remito') or 'Sin descripción')+
                               ' · Material elegido: '+str(selected_ocr.get('Material Excel') or '(sin asignar)'))
                    filter1,filter2,filter3=st.columns([3,2,1.2])
                    search_query=filter1.text_input('2 · Buscar material por nombre o tamaño',placeholder='Ej.: afiche 20x30, Brahma, Stella',
                        key=f'visual_search_{period_key(view_period)}_{p["ocr_version"]}')
                    filter_sheet=filter2.selectbox('Hoja / marca', ['Todas']+sorted(set(c['hoja'] for c in catalog)),
                        key=f'visual_sheet_{period_key(view_period)}_{p["ocr_version"]}')
                    photos_only=filter3.checkbox('Solo con foto',value=False,
                        key=f'visual_photos_{period_key(view_period)}_{p["ocr_version"]}')
                    image_map=p.get('pop_images',{})
                    image_assets=st.session_state.pop_assets.get(view_period,{})
                    original_ocr=p['ocr_rows'][current_row] if current_row<len(p['ocr_rows']) else {}
                    preferred=preferred_ocr_ids(original_ocr)
                    candidates=visual_candidates(catalog,p['aliases'],search_query,filter_sheet,
                        preferred,photos_only,image_map,image_assets)
                    st.caption(f'3 · Tocá **Seleccionar POP** debajo de su imagen. '
                               f'Hay {len(candidates)} materiales disponibles; se muestran primero los sugeridos por similitud de nombres.')
                    if candidates:
                        per_page=12
                        page_total=max(1,math.ceil(len(candidates)/per_page))
                        pager_key=f'visual_page_{period_key(view_period)}_{p["ocr_version"]}'
                        if st.session_state.get(pager_key,1)>page_total:st.session_state[pager_key]=page_total
                        page_no=st.number_input('Página de fotos',min_value=1,max_value=page_total,
                            value=1,step=1,key=pager_key)
                        visible=candidates[(int(page_no)-1)*per_page:int(page_no)*per_page]
                        for start in range(0,len(visible),3):
                            columns=st.columns(3)
                            for column,c in zip(columns,visible[start:start+3]):
                                with column:
                                    cid=c['id']
                                    is_selected=selected_ocr.get('Material Excel')==names[cid]
                                    with st.container(border=True):
                                        picture=image_assets.get(image_map.get(cid,''))
                                        if picture:st.image(picture,use_container_width=True)
                                        else:st.caption('🖼️ Este POP no tiene foto vinculada')
                                        st.markdown('**'+str(p['aliases'].get(cid) or c['formato'])+'**')
                                        st.caption(f"{c['hoja']} · {cid} · Excel DDV: {pretty(c['cantidad_excel'])}")
                                        if cid in preferred:st.caption('⭐ Material sugerido por nombre')
                                        if is_selected:st.success('✓ Seleccionado para esta fila')
                                        if st.button('✓ Seleccionar POP',key=f'visual_pick_{period_key(view_period)}_{p["ocr_version"]}_{current_row}_{sha256(cid.encode()).hexdigest()[:12]}',
                                                     use_container_width=True,disabled=is_selected):
                                            st.session_state[draft_key]=choose_material(
                                                st.session_state[draft_key],current_row,cid,names,catalog)
                                            st.session_state[editor_rev_key]+=1
                                            st.rerun()
                    else:
                        st.info('No hay materiales que cumplan ese filtro. Probá buscar menos palabras o desactivar «Solo con foto».')
                else:
                    st.success('✅ No quedan renglones sin asignar. Todos los POP identificados se mantienen en la tabla de revisión.')
            else:
                st.warning('No hay filas del remito para seleccionar.')
        submitted=st.button('✅ Aplicar revisión a este período',type='primary',use_container_width=True,
                            help='Confirma las cantidades y las selecciones visuales para este período.')
        if submitted:
            edited_rows=edited.to_dict('records')
            quantities,unknown,count=confirm_ocr_rows(edited_rows,valid_ids)
            p['ocr_edited_rows']=edited_rows
            p['ocr_edit_ver']+=1
            updated=merge_quantities(p['ocr_base_entries'],quantities,p['ocr_operation'])
            invalidate_changed_checks(p,p['remito_entries'],updated,'Importación Excel revisado aplicada')
            p['remito_entries']=updated
            p['unmatched']=unknown
            p['is_complete']=False
            p['preliminary']=True
            p['edit_version']+=1
            if p['ocr_signature'] not in p['processed_signatures']:
                p['processed_signatures'].append(p['ocr_signature'])
            if p['ocr_operation'].startswith('Agregar'):
                existing_hashes=set(p.get('processed_remito_files',[]))
                for file_digest in p.get('ocr_file_digests',[]):
                    if file_digest not in existing_hashes:
                        p.setdefault('processed_remito_files',[]).append(file_digest)
                        existing_hashes.add(file_digest)
            else:
                p['processed_remito_files']=list(p.get('ocr_file_digests') or [])
            p['last_updated']=now_label()
            if p.get('ocr_excel_meta'):
                if p['ocr_operation'].startswith('Reemplazar'):
                    p['remito_excel_history']=[]
                stored={e.get('digest') for e in p.get('remito_excel_history',[])}
                for meta in p['ocr_excel_meta']:
                    if meta['digest'] not in stored:
                        p.setdefault('remito_excel_history',[]).append({**meta,'cargado':now_label()})
                        stored.add(meta['digest'])
            for event in reversed(p.get('remito_history',[])):
                if event['id']==p.get('pending_remito_id'):
                    event.update(estado='Excel aplicado · revisión pendiente',filas_aplicadas=count,sin_conciliar=len(unknown))
                    break
            st.toast(f'{count} líneas del Excel aplicadas a {view_period}. Pendientes: {len(unknown)}.')
            persist_changes()
        if p['unmatched']:
            st.markdown('**Renglones sin conciliar**')
            st.dataframe(pd.DataFrame(p['unmatched']),hide_index=True,use_container_width=True)
        if p.get('ocr_previews'):
            with st.expander('Ver fotografías originales de este lote',expanded=False):
                for label,img in p['ocr_previews']:
                    st.image(img,caption=label,width=650)
        with st.expander('Fuente de las cantidades y notas de importación'):
            st.text_area('Texto detectado',value=p['ocr_raw'],height=280)
            st.download_button('Descargar notas de la lectura',p['ocr_raw'].encode(),file_name=f'POP_DDV_{period_key(view_period)}_notas.txt')

with page_items:
    st.subheader(f'Control editable por material · {view_period}')
    st.caption('Remito original: cantidad del Excel revisado, sin modificaciones por tildes físicas. Conciliado: cantidad ajustada tras control presencial. Blanco significa no leído; 0 significa comprobado.')
    col1,col2,col3=st.columns([2,2,1])
    sheet=col1.selectbox('Hoja del Excel',['Todas']+sorted(set(r['hoja'] for r in rows)),key=f'filter_sheet_{period_key(view_period)}')
    status=col2.selectbox('Estado',['Todos','Diferencias y pendientes','Coincide','Faltante','Sobrante','Pendiente','Sin movimiento'],key=f'filter_status_{period_key(view_period)}')
    show_zero=False
    display=[r for r in rows if (sheet=='Todas' or r['hoja']==sheet)
             and (show_zero or r['cantidad_excel']>0 or r['verificado'])
             and (status=='Todos' or (r['estado'] in ('Faltante','Sobrante','Pendiente')
                 if status=='Diferencias y pendientes' else r['estado']==status))]
    manual=[{'ID':r['id'],'Hoja':r['hoja'],'Material':p['aliases'].get(r['id']) or r['material'],
             'Celda':r['celda'],'Excel':r['cantidad_excel'],
             'Remito original':p['remito_entries'].get(r['id']),
             'Conciliado':r['cantidad_remito'],
             'Control físico':'Sí' if r['verificacion_fisica'] else 'No',
             'Diferencia':r['diferencia'],'Estado':r['estado']} for r in display]
    if not manual:st.info('No hay materiales para estos filtros.')
    else:
        with st.form(f'form_manual_{period_key(view_period)}_{p["edit_version"]}_{sheet}_{status}_{show_zero}'):
            manual_edit=st.data_editor(pd.DataFrame(manual),hide_index=True,use_container_width=True,
                height=530,num_rows='fixed',
                column_config={'ID':None,'Material':st.column_config.TextColumn('Material',width='large'),
                    'Excel':st.column_config.NumberColumn('Excel',format='%d'),
                    'Remito original':st.column_config.NumberColumn('Remito original editable',min_value=0,step=1,format='%d')},
                disabled=['ID','Hoja','Material','Celda','Excel','Conciliado','Control físico','Diferencia','Estado'])
            manual_save=st.form_submit_button('Guardar correcciones de este trimestre',type='primary')
        if manual_save:
            update=dict(p['remito_entries'])
            for obj in manual_edit.to_dict('records'):
                amount=integer_quantity(obj['Remito original'])
                if amount is None:update.pop(obj['ID'],None)
                else:update[obj['ID']]=amount
            invalidate_changed_checks(p,p['remito_entries'],update,'Edición manual de remito')
            p['remito_entries']=update;p['edit_version']+=1
            p['is_complete']=False;p['preliminary']=True;p['last_updated']=now_label()
            persist_changes()
    st.divider()
    blocked=bool(p['unmatched']) or not p['remito_entries']
    if not p['is_complete']:
        st.caption('Para cerrar el control debe haber cantidades registradas, no quedar renglones sin vincular y haberse revisado todos los Excel del remito.')
        if st.button('✅ Marcar remito completamente revisado',disabled=blocked,key=f'finish_{period_key(view_period)}'):
            p['is_complete']=True;p['preliminary']=False;p['last_updated']=now_label()
            for event in reversed(p.get('remito_history',[])):
                if event.get('id')==p.get('pending_remito_id'):event['estado']='Remito revisado y cerrado';break
            persist_changes()
    else:
        if st.button('Reabrir revisión del remito',key=f'reopen_{period_key(view_period)}'):
            p['is_complete']=False;p['preliminary']=True;p['last_updated']=now_label();persist_changes()
    with st.expander('Reiniciar cantidades de este trimestre'):
        st.warning('Esta acción borra solo las cantidades de remito de este período. No modifica los otros trimestres ni las asignaciones del Excel.')
        if st.button(f'Borrar cantidades de {view_period}',key=f'clear_{period_key(view_period)}'):
            clear_checks(p,'Reinicio de cantidades del trimestre')
            p['remito_entries']={};p['unmatched']=[];p['is_complete']=False;p['preliminary']=False
            p['edit_version']+=1;p['last_updated']=now_label();persist_changes()

with page_gallery:
    st.subheader(f'Galería de POP · {view_period}')
    st.caption('Control presencial: en cada POP pendiente, faltante o sobrante presioná ✅ si comprobaste '
               'físicamente que la cantidad correcta es la asignada. La cifra original del remito '
               'no se borra y podés deshacer la verificación.')
    gallery_assets=st.session_state.pop_assets.get(view_period,{})
    image_map=p.get('pop_images',{})
    c1,c2,c3=st.columns([2,2,1])
    gallery_search=c1.text_input('Buscar material',key=f'gallery_search_{period_key(view_period)}',placeholder='Marca, tamaño, campaña…')
    gallery_sheet=c2.selectbox('Familia / hoja',['Todas']+sorted(set(r['hoja'] for r in rows)),key=f'gallery_sheet_{period_key(view_period)}')
    gallery_status=c3.selectbox('Estado',['Todos','Diferencias y pendientes','Verificados físicamente',
                                             'Coincide','Faltante','Sobrante','Pendiente','Sin movimiento'],
                                key=f'gallery_status_{period_key(view_period)}')
    q=gallery_search.strip().casefold()
    def gallery_match(r):
        if gallery_status=='Todos':return True
        if gallery_status=='Verificados físicamente':return r['verificacion_fisica']
        if gallery_status=='Diferencias y pendientes':
            return r['estado'] in ('Pendiente','Faltante','Sobrante') or r['verificacion_fisica']
        if gallery_status in ('Pendiente','Faltante','Sobrante'):
            return r['estado']==gallery_status or (r['verificacion_fisica'] and r['estado_original']==gallery_status)
        return r['estado']==gallery_status
    gallery_rows=[r for r in rows if (r['cantidad_excel']>0 or r['verificado'])
                  and (gallery_sheet=='Todas' or r['hoja']==gallery_sheet)
                  and gallery_match(r)
                  and (not q or q in (str(p['aliases'].get(r['id']) or '')+' '+r['material']+' '+r['hoja']).casefold())]
    with st.expander('Asignar o reemplazar la imagen de un POP',expanded=False):
        material_options={f"{r['hoja']} · {r['formato']} · {r['id']}":r['id'] for r in rows}
        selected=st.selectbox('Material',list(material_options),key=f'gallery_edit_{period_key(view_period)}')
        uploaded_photo=st.file_uploader('Foto del POP (JPG, PNG, WEBP)',type=['jpg','jpeg','png','webp'],key=f'gallery_photo_{period_key(view_period)}')
        if st.button('Guardar imagen de este POP',disabled=uploaded_photo is None):
            try:
                cid=material_options[selected];key=asset_key(cid)
                st.session_state.pop_assets.setdefault(view_period,{})[key]=image_jpeg(uploaded_photo.getvalue())
                p.setdefault('pop_images',{})[cid]=key
                p['last_updated']=now_label()
                persist_changes(assets_changed=[view_period])
            except Exception as exc:st.error(f'Imagen inválida: {exc}')
    gallery_total=len(gallery_rows)
    pages=max(1,math.ceil(gallery_total/12))
    page_key=f'gallery_page_{period_key(view_period)}'
    # Un filtro puede reducir las páginas después de aprobar. Evitar la excepción
    # de un number_input cuyo valor previo queda fuera del rango.
    if st.session_state.get(page_key,1)>pages:st.session_state[page_key]=pages
    page_number=st.number_input('Página de la galería',min_value=1,max_value=pages,value=1,step=1,key=page_key)
    st.caption(f'{gallery_total} materiales · Página {page_number} de {pages} · '
               f'{sum(r["id"] in image_map and image_map[r["id"]] in gallery_assets for r in gallery_rows)} con imagen · '
               f'{sum(r["verificacion_fisica"] for r in gallery_rows)} verificados físicamente')
    part=gallery_rows[(int(page_number)-1)*12:int(page_number)*12]
    for start in range(0,len(part),3):
        columns=st.columns(3)
        for box,r in zip(columns,part[start:start+3]):
            with box:
                hash_key=sha256((view_period+'|'+r['id']).encode('utf-8')).hexdigest()[:18]
                tile_key=('pop_fisico_aprobado_' if r['verificacion_fisica'] else 'pop_pendiente_')+hash_key
                with st.container(border=True,key=tile_key):
                    pic=gallery_assets.get(image_map.get(r['id'],''))
                    if pic:st.image(pic,use_container_width=True)
                    else:st.info('Sin imagen vinculada · cargala arriba')
                    st.markdown(f"**{p['aliases'].get(r['id']) or r['formato']}**")
                    st.caption(f"{r['hoja']} · {r['celda']} · {r['estado']}")
                    a,b=st.columns(2)
                    a.metric('Asignado',pretty(r['cantidad_excel']))
                    b.metric('Remito conciliado','—' if r['cantidad_remito'] is None else pretty(r['cantidad_remito']))
                    if r['verificacion_fisica']:
                        st.button('✅ Verificado físicamente',key='pop_boton_aprobado_'+hash_key,
                                  disabled=True,use_container_width=True)
                        original=r['cantidad_remito_original']
                        st.caption('Remito original: '+('Sin lectura' if original is None else pretty(original))+
                                   f' · Comprobado: {r["fecha_verificacion"] or "sin fecha"}')
                        if st.button('↶ Deshacer control físico',key='undo_fisico_'+hash_key,
                                     use_container_width=True):
                            undo_material(p,r['id'])
                            p['last_updated']=now_label();p['edit_version']+=1
                            persist_changes()
                    else:
                        if r['diferencia'] is None:st.caption('Diferencia pendiente de comprobar')
                        elif r['diferencia']==0:st.success('Coincide · diferencia 0')
                        elif r['diferencia']<0:st.error(f"Faltan {pretty(abs(r['diferencia']))} unidades")
                        else:st.warning(f"Sobran {pretty(r['diferencia'])} unidades")
                        if r['estado'] in ('Pendiente','Faltante','Sobrante'):
                            if st.button('✅ Verificado físicamente',key='aprobar_fisico_'+hash_key,
                                         use_container_width=True,help='Confirmar inspección presencial. '
                                         'Iguala la cantidad CONCILIADA a la asignada, sin borrar el remito original.'):
                                approve_material(p,r['id'])
                                p['last_updated']=now_label();p['edit_version']+=1
                                persist_changes()
    if not part:st.info('No hay materiales para estos filtros.')
    if p.get('physical_events'):
        with st.expander(f'Historial de verificaciones físicas ({len(p["physical_events"])})'):
            st.dataframe(pd.DataFrame([{ 'Fecha (UTC)':e.get('fecha',''),
                'Material':e.get('material_id',''),'Acción':e.get('accion',''),
                'Remito original':e.get('cantidad_remito_original'),
                'Cantidad conciliada':e.get('cantidad_conciliada'),
                'Motivo':e.get('motivo','')}
                for e in reversed(p['physical_events'])]),use_container_width=True,hide_index=True)

with page_history:
    st.subheader(f'Archivos y remitos registrados · {view_period}')
    if p.get('excel_history'):
        st.markdown('**Excel incorporados a la asignación del mes**')
        st.dataframe(pd.DataFrame([{'Fecha':e.get('fecha'), 'Excel':e.get('archivo'),
            'Unidades DDV':e.get('unidades_ddv'), 'POP combinados':e.get('combinados'),
            'POP nuevos':e.get('agregados')} for e in p['excel_history']]),
            hide_index=True,use_container_width=True)
    events=p.get('remito_history',[])
    st.caption('Cada incorporación de un remito queda registrada con fecha, archivos, operación y estado. Las comprobaciones presenciales de POP se registran por separado en la Galería y en el respaldo JSON.')
    if events:
        st.dataframe(pd.DataFrame([{
            'Fecha':e.get('fecha',''), 'Operación':e.get('accion',''),
            'Archivos':', '.join(e.get('archivos',[])),
            'Páginas':e.get('paginas',0),'Renglones':e.get('filas_ocr',0),
            'Aplicados':e.get('filas_aplicadas',0),'Estado':e.get('estado','')}
            for e in reversed(events)]),use_container_width=True,hide_index=True)
        scans=st.session_state.pop_assets.get(view_period,{})
        for e in reversed(events):
            with st.expander(f"{e.get('fecha','')} · {', '.join(e.get('archivos',[]))} · {e.get('estado','')}"):
                st.write(f"Operación: **{e.get('accion','')}** · Páginas conservadas: {len(e.get('imagen_keys',[]))}")
                for key in e.get('imagen_keys',[]):
                    if key in scans:st.image(scans[key],use_container_width=True)
                    else:st.warning('Imagen original no disponible en el registro; permanece el nombre de archivo.')
    else:st.info('Todavía no se agregaron remitos para este período.')

with page_labels:
    st.subheader(f'Identificación de materiales · {view_period}')
    st.caption('Si una columna del Excel dice solo «20x30», podés agregar el nombre específico de la campaña. Esto no modifica el archivo Excel.')
    labels=[{'ID':c['id'],'Hoja':c['hoja'],'Original':c['material'],
             'Descripción personalizada':p['aliases'].get(c['id'],'')}
             for c in catalog if c['cantidad_excel']>0]
    with st.form(f'alias_form_{period_key(view_period)}_{p["edit_version"]}'):
        aliases_data=st.data_editor(pd.DataFrame(labels),hide_index=True,use_container_width=True,
            height=475,num_rows='fixed',column_config={
                'Original':st.column_config.TextColumn('Original',width='large'),
                'Descripción personalizada':st.column_config.TextColumn('Descripción personalizada',width='large')},
                disabled=['ID','Hoja','Original'])
        update_names=st.form_submit_button('Guardar nombres para este período')
    if update_names:
        p['aliases']={r['ID']:str(r['Descripción personalizada']).strip()
                      for r in aliases_data.to_dict('records')
                      if str(r['Descripción personalizada']).strip() not in ('','nan','None')}
        p['last_updated']=now_label();p['edit_version']+=1;persist_changes()

with page_export:
    st.subheader(f'Descargas y auditoría · {view_period}')
    st.download_button('⬇️ Descargar conciliación CSV de este período',to_csv(rows),
        file_name=f'POP_DDV_{period_key(view_period)}_conciliacion.csv',mime='text/csv',type='primary')
    st.download_button('💾 Descargar historial completo en JSON',archive_bytes(periods),
        file_name='POP_DDV_historial_todos_los_periodos.json',mime='application/json')
    st.markdown(f'''**Origen Excel:** {p['source_name']}  
**Estado:** {'Revisión completa' if p['is_complete'] else 'Provisional o incompleto'}  
**Última modificación:** {p['last_updated'] or 'No registrada'}''')
    st.markdown('**Hojas del Excel inspeccionadas**')
    st.dataframe(pd.DataFrame([{'Hoja':r['hoja'],'Oculta': 'Sí' if r['oculta'] else 'No',
        'Fila DDV':r['fila_ddv'],'Columnas POP':r['materiales'],'Unidades DDV':r['total']}
        for r in p['sheets']]),hide_index=True,use_container_width=True)
    if p['issues']:
        st.markdown('**Alertas de lectura Excel**')
        for issue in p['issues']:st.caption('• '+str(issue))
    st.info('Con GitHub privado configurado, el registro, las tildes de verificación física y las fotografías se conservan. El JSON respalda resultados e historial, pero no incluye las imágenes.')
    st.download_button('⬇️ Descargar imágenes de POP y remitos (ZIP)',
        write_zip_assets(st.session_state.pop_assets.get(view_period,{})),
        file_name=f'POP_DDV_{period_key(view_period)}_imagenes.zip',mime='application/zip')

st.divider()
st.caption('POP liviano · DDV · Los Excel revisados son la base de recepción; las verificaciones físicas se guardan por período.')
