"""Tablero POP Liviano DDV multitrimestre | GitHub y Streamlit Community Cloud."""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ocr_core import read_documents
from pop_core import catalog_from_excel, integer_quantity, metrics, reconcile, suggest_matches, to_csv
from period_store import (PERIOD_RE, archive_bytes, empty_period, merge_quantities,
                          new_source, restore_archive)

st.set_page_config(page_title='Control POP liviano · DDV', page_icon='📦',layout='wide')
st.markdown('''<style>
.stApp{background:#F4F7FC}
h1,h2,h3{letter-spacing:-.025em;color:#142B4C}
[data-testid="stMetric"]{background:#fff;border:1px solid #DDE5F0;border-radius:13px;padding:13px 18px}
[data-testid="stMetricLabel"]{color:#536781;font-weight:600}
[data-testid="stMetricValue"]{color:#153962}
[data-testid="stSidebar"]{background:#13263F}
[data-testid="stSidebar"] *{color:#EAF1F8}
[data-testid="stSidebar"] button{color:#18304D}
[data-testid="stSidebar"] input{color:#18304D!important}
.stTabs [data-baseweb="tab"]{padding:9px 15px}
div.stButton > button[kind="primary"]{background:#1769D2;border-radius:9px}
</style>''',unsafe_allow_html=True)


def pretty(value):
    return f'{int(value):,}'.replace(',','.')


def period_key(label):
    return label.replace(' ','_')


def labels_for(catalog,aliases):
    return {c['id']:f"{c['id']} | {aliases.get(c['id']) or c['material']} [{c['celda']}]"
            for c in catalog}


def now_label():
    return datetime.now().strftime('%d/%m/%Y %H:%M')


def make_ocr_table(p, names):
    if p.get('ocr_edited_rows') is not None:
        return p['ocr_edited_rows']
    return [
        {'Página':x.get('pagina',''), 'Cantidad':x.get('cantidad'),
         'Descripción OCR':x.get('detalle',''),
         'Material Excel':names.get(x.get('id',''),'(sin asignar)'),
         'Sugerencia':names.get(x.get('sugerido',''),'—'),
         'Lectura':x.get('estado_match',''), 'Ignorar':False}
        for x in p['ocr_rows']
    ]


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
                'Descripción':r.get('Descripción OCR',''),
                'Motivo':'Cantidad sin verificar' if n is None else 'Material sin asignar'})
    return dict(amounts),unknown,count


def initialize():
    if 'pop_periods' not in st.session_state:
        baseline=json.loads((Path(__file__).resolve().parent/'data'/'q3_2026_preliminar.json').read_text(encoding='utf-8'))
        q3=empty_period();q3.update(baseline)
        st.session_state.pop_periods={'Q3 2026':q3,'Q4 2026':empty_period()}
    # Cambios de selector deben aplicarse antes de crear los widgets de ese rerun.
    if st.session_state.get('next_period_load') in st.session_state.pop_periods:
        st.session_state.period_load=st.session_state.pop('next_period_load')
    if st.session_state.get('next_period_view') in st.session_state.pop_periods:
        st.session_state.period_view=st.session_state.pop('next_period_view')
    if 'period_load' not in st.session_state or st.session_state.period_load not in st.session_state.pop_periods:
        st.session_state.period_load='Q4 2026'
    if 'period_view' not in st.session_state or st.session_state.period_view not in st.session_state.pop_periods:
        st.session_state.period_view='Q3 2026'


initialize()
periods=st.session_state.pop_periods
st.title('📦 Control de POP liviano')
st.caption('Remitos vs. asignación de POP · Solo Distribuidora del Valle S.A. · Resultados separados por trimestre')

with st.sidebar:
    st.markdown('### Control DDV')
    st.caption('Cada período guarda su propio Excel, OCR y conciliación dentro de esta sesión.')
    periods_ordered=sorted(periods,key=lambda s:(int(s.split()[1]),int(s[1])))
    load_period=st.selectbox('📥 Período de carga',periods_ordered,key='period_load')
    view_period=st.selectbox('📊 Período de visualización',periods_ordered,key='period_view')
    with st.expander('Crear otro trimestre',expanded=False):
        label=st.text_input('Nuevo período (ej. Q1 2027)',placeholder='Q1 2027',key='new_period_label').strip().upper()
        if st.button('Agregar período',use_container_width=True):
            if not PERIOD_RE.fullmatch(label):st.error('Formato requerido: Q1 2027, Q2 2027, etc.')
            elif label in periods:st.warning('El período ya existe.')
            else:
                periods[label]=empty_period()
                st.session_state.next_period_load=label
                st.session_state.next_period_view=label
                st.rerun()
    st.divider()
    uploading=periods[load_period]
    st.markdown(f'**Carga de {load_period}**')
    if uploading['catalog']:
        assigned=sum(int(c['cantidad_excel']) for c in uploading['catalog'])
        st.success(f'{len(uploading["catalog"])} materiales de DDV · {pretty(assigned)} unidades asignadas')
        st.caption(f'Excel: {uploading["source_name"]}')
    else:st.warning('Todavía no se cargó el Excel de este período.')
    uploaded_excel=st.file_uploader('1. Subir o reemplazar Excel de asignación',type=['xlsx'],key=f'xl_{period_key(load_period)}')
    if st.button('Aplicar Excel a este período',disabled=uploaded_excel is None,use_container_width=True):
        try:
            binary=uploaded_excel.getvalue()
            digest=sha256(binary).hexdigest()
            if uploading['source_digest']==digest:
                st.info('Es el mismo Excel que ya está cargado; se conservaron las cantidades del remito.')
            else:
                periods[load_period]=new_source(uploading,binary,uploaded_excel.name,catalog_from_excel)
                st.session_state.next_period_view=load_period
                st.success('Excel actualizado. Se reiniciaron SOLO las lecturas de este trimestre.')
                st.rerun()
        except Exception as ex:st.error(f'No se pudo aplicar el archivo Excel: {ex}')
    remito=st.file_uploader('2. Fotos del remito o PDF (hasta 3 páginas)',type=['png','jpg','jpeg','webp','pdf'],
                            accept_multiple_files=True,key=f'remito_{period_key(load_period)}')
    treatment=st.radio('Qué hacer con la nueva lectura',
        ['Reemplazar cantidades anteriores','Agregar páginas al remito actual'],
        key=f'operation_{period_key(load_period)}',
        help='Reemplazar: el nuevo remito sustituye las cantidades anteriores cuando confirmes el OCR. Agregar: suma cantidades, solo si son páginas diferentes del MISMO remito.')
    two_columns=st.checkbox('El remito tiene dos columnas',value=True,key=f'columns_{period_key(load_period)}')
    split=st.slider('Separación de columnas (%)',42,58,50,disabled=not two_columns,key=f'split_{period_key(load_period)}')/100
    if treatment=='Agregar páginas al remito actual':
        st.warning('No vuelvas a subir páginas ya contabilizadas: se sumarían dos veces.')
    run_ocr=st.button('🔎 Leer remito para este período',type='primary',use_container_width=True,
                      disabled=not remito or not uploading['catalog'])
    if run_ocr:
        try:
            files=[(x.name,x.getvalue()) for x in remito]
            signature=sha256(b'|'.join(x.encode()+b':'+sha256(data).hexdigest().encode() for x,data in files)).hexdigest()
            if treatment=='Agregar páginas al remito actual' and signature in uploading['processed_signatures']:
                st.error('Estas páginas ya fueron procesadas para este período. No se permite sumarlas dos veces.')
            else:
                with st.spinner(f'Leyendo páginas de {load_period}…'):
                    result=read_documents(files,two_columns=two_columns,split=split,max_pages=3)
                    suggestions=suggest_matches(result.rows,uploading['catalog'],uploading['aliases'])
                uploading.update(ocr_rows=suggestions,ocr_raw=result.raw_text,ocr_warnings=result.warnings,
                    ocr_previews=result.images,ocr_edited_rows=None,ocr_edit_ver=0,
                    ocr_version=uploading['ocr_version']+1,ocr_signature=signature,
                    ocr_operation=treatment,ocr_base_entries=deepcopy(uploading['remito_entries']),
                    remito_files=[name for name,_ in files])
                st.session_state.next_period_view=load_period
                st.success(f'{len(suggestions)} renglones reconocidos. Revisalos en la pestaña OCR antes de aplicarlos.')
                st.rerun()
        except Exception as ex:st.error(f'Error en el OCR: {ex}')
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
    st.download_button('💾 Descargar historial Q3 / Q4 (JSON)',archive_bytes(periods),
        file_name='POP_DDV_historial_todos_los_periodos.json',mime='application/json',use_container_width=True)
    history_upload=st.file_uploader('Restaurar historial guardado',type=['json'],key='restore_all')
    if st.button('Restaurar historial',disabled=history_upload is None,use_container_width=True):
        try:
            restored=restore_archive(history_upload.getvalue())
            if not restored:raise ValueError('El archivo no contiene períodos.')
            # Los períodos faltantes en el respaldo se conservan; los presentes se reemplazan.
            periods.update(restored)
            if st.session_state.period_load not in periods:st.session_state.period_load=next(iter(periods))
            if st.session_state.period_view not in periods:st.session_state.period_view=next(iter(periods))
            st.success('Historial recuperado correctamente.')
            st.rerun()
        except Exception as ex:st.error(f'No se pudo restaurar el historial: {ex}')
    st.caption('En Streamlit Cloud el historial no persiste automáticamente tras cerrar o reiniciar la app. Guardá el JSON y restauralo al volver.')

st.markdown(f'### Resultados · {view_period}')
if load_period!=view_period:
    st.info(f'Estás **cargando en {load_period}** y **consultando {view_period}**. Las operaciones de carga no modifican el período que estás viendo.')

p=periods[view_period]
catalog=p['catalog']
if not catalog:
    st.warning(f'No hay Excel cargado para {view_period}. Seleccionalo como «Período de carga» y subí su archivo.')
    st.stop()

include_hidden=st.checkbox('Incluir hojas ocultas del Excel',value=True,key=f'hidden_{period_key(view_period)}')
rows=reconcile(catalog,p['remito_entries'],p['is_complete'],include_hidden)
summary=metrics(rows)
cols=st.columns(5)
for col,name,value in zip(cols,['Asignado DDV','Remito registrado','Coinciden','Diferencias','Pendientes'],
                          [pretty(summary['asignado']),pretty(summary['recibido']),summary['coinciden'],summary['diferencias'],summary['pendientes']]):
    col.metric(name,value)
if p['preliminary']:
    if p['source_mode']=='Q3 2026 precargado':
        st.warning('**Q3 precargado · cifras provisionales:** la transcripción anterior de la foto no fue certificada. Podés reemplazarla subiendo nuevas fotos en «Período de carga: Q3 2026».')
    else:
        st.warning('**Control preliminar:** las cantidades fueron cargadas, pero falta confirmar la revisión completa del remito.')
if p['ocr_rows'] and p['ocr_signature'] not in p['processed_signatures']:
    st.info('Hay una lectura OCR nueva **pendiente de revisión y aplicación** para este período; las cifras de arriba todavía corresponden al control anterior.')
if p['is_complete']:
    st.success('Remito marcado como completamente revisado; los materiales sin registro pasan a contabilizarse como faltantes.')
elif p['remito_entries']:
    st.caption('Conciliación preliminar: un material no leído aparece pendiente, no como recibido en cero.')
else:
    st.info('Faltan cantidades del remito. Seleccioná este período para cargar sus fotos o PDF.')
if p['unmatched']:
    st.error(f'Hay {len(p["unmatched"])} líneas OCR no conciliadas. Revisalas antes de cerrar el remito.')

names=labels_for(catalog,p['aliases'])
valid_ids=set(names)
options=['(sin asignar)']+list(names.values())

page_summary,page_ocr,page_items,page_labels,page_export=st.tabs([
    '📊 Resumen','📷 Lectura OCR','🧾 Control por material','🏷️ Nombres de materiales','📥 Exportar / auditar'])

with page_summary:
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
        for title,key,color in [('Excel asignado','asignado','#266FBA'),('Remito registrado','recibido','#E6A144')]:
            chart.add_trace(go.Bar(name=title,x=[x[key] for _,x in ordered],y=[label for label,_ in ordered],
                                   marker_color=color,orientation='h'))
        chart.update_layout(barmode='group',height=max(350,40*len(ordered)+110),
                            margin=dict(l=10,r=8,t=6,b=18),legend=dict(orientation='h',y=1.07),
                            plot_bgcolor='#fff',paper_bgcolor='#fff',yaxis=dict(autorange='reversed'),
                            xaxis=dict(title='Unidades',gridcolor='#E7EDF4'))
        st.plotly_chart(chart,use_container_width=True,config={'displayModeBar':False})
    cc,dd=st.columns(2)
    cc.metric('Unidades faltantes registradas',pretty(summary['faltan_unidades']))
    dd.metric('Unidades sobrantes registradas',pretty(summary['sobran_unidades']))
    attention=[r for r in rows if r['estado'] in ('Pendiente','Faltante','Sobrante')]
    st.markdown('**Materiales que requieren atención**')
    if attention:
        st.dataframe(pd.DataFrame([{'Estado':r['estado'],'Hoja':r['hoja'],'Material':p['aliases'].get(r['id']) or r['material'],
            'Excel':r['cantidad_excel'],'Remito':r['cantidad_remito'],'Diferencia':r['diferencia'],'Celda':r['celda']}
            for r in sorted(attention,key=lambda r:(r['estado']=='Pendiente',-r['cantidad_excel']))]),
            hide_index=True,use_container_width=True,height=min(550,40*len(attention)+50))
    else:st.success('No hay diferencias ni renglones pendientes en el alcance seleccionado.')
    st.markdown('**Resultado por pestaña del Excel**')
    st.dataframe(pd.DataFrame([{'Hoja':label,'Asignado':g['asignado'],'Remito':g['recibido'],
        'Coinciden':g['coinciden'],'Diferencias':g['diferencias'],'Pendientes':g['pendientes']}
        for label,g in grouped.items()]),hide_index=True,use_container_width=True)
    other=[(key,item) for key,item in periods.items() if key!=view_period and item['catalog']]
    if other:
        with st.expander('Comparar indicadores con otros trimestres',expanded=False):
            compare=[]
            for label,item in [(view_period,p)]+other:
                report=metrics(reconcile(item['catalog'],item['remito_entries'],item['is_complete'],include_hidden))
                compare.append({'Período':label,'Asignado':report['asignado'],'Remito registrado':report['recibido'],
                    'Coinciden':report['coinciden'],'Diferencias':report['diferencias'],
                    'Pendientes':report['pendientes'],
                    'Control':'Revisado' if item['is_complete'] else 'Provisional'})
            st.dataframe(pd.DataFrame(compare),hide_index=True,use_container_width=True)

with page_ocr:
    st.subheader(f'Leer y revisar fotos · {view_period}')
    st.caption('Cargá las imágenes del período desde el panel izquierdo. Las coincidencias automáticas son propuestas, no validaciones definitivas.')
    for warning in p['ocr_warnings']:st.warning(warning)
    if not p['ocr_rows']:
        st.info('Este trimestre no tiene una extracción OCR editable. Podés subir una imagen nueva y ejecutar «Leer remito para este período».')
    else:
        ocr=p['ocr_rows']
        q1,q2,q3=st.columns(3)
        q1.metric('Renglones OCR',len(ocr));q2.metric('Con cantidad',sum(x.get('cantidad') is not None for x in ocr))
        q3.metric('Con propuesta',sum(bool(x.get('sugerido')) for x in ocr))
        st.caption(f'Acción seleccionada para esta lectura: **{p["ocr_operation"]}**. Reaplicar la misma tabla no suma dos veces los materiales.')
        st.markdown('Corregí las cifras y elegí el material correcto. Si el OCR confundió dos conceptos, dejalos pendientes hasta identificarlos.')
        table=make_ocr_table(p,names)
        with st.form(f'ocr_form_{period_key(view_period)}_{p["ocr_version"]}_{p["ocr_edit_ver"]}'):
            edited=st.data_editor(pd.DataFrame(table),use_container_width=True,hide_index=True,
                height=525,num_rows='dynamic',
                column_order=['Página','Cantidad','Descripción OCR','Material Excel','Sugerencia','Lectura','Ignorar'],
                column_config={
                    'Cantidad':st.column_config.NumberColumn('Cantidad',min_value=0,step=1,format='%d'),
                    'Descripción OCR':st.column_config.TextColumn('Descripción OCR',width='large'),
                    'Material Excel':st.column_config.SelectboxColumn('Material Excel',options=options,width='large'),
                    'Sugerencia':st.column_config.TextColumn('Sugerencia',width='large'),
                    'Página':st.column_config.TextColumn('Página',width='medium'),
                    'Ignorar':st.column_config.CheckboxColumn('Ignorar',default=False)},
                disabled=['Página','Sugerencia','Lectura'])
            submitted=st.form_submit_button('✅ Aplicar revisión a este período',type='primary',use_container_width=True)
        if submitted:
            edited_rows=edited.to_dict('records')
            quantities,unknown,count=confirm_ocr_rows(edited_rows,valid_ids)
            p['ocr_edited_rows']=edited_rows
            p['ocr_edit_ver']+=1
            p['remito_entries']=merge_quantities(p['ocr_base_entries'],quantities,p['ocr_operation'])
            p['unmatched']=unknown
            p['is_complete']=False
            p['preliminary']=True
            p['edit_version']+=1
            if p['ocr_signature'] not in p['processed_signatures']:
                p['processed_signatures'].append(p['ocr_signature'])
            p['last_updated']=now_label()
            st.toast(f'{count} líneas aplicadas a {view_period}. Pendientes: {len(unknown)}.')
            st.rerun()
        if p['unmatched']:
            st.markdown('**Renglones sin conciliar**')
            st.dataframe(pd.DataFrame(p['unmatched']),hide_index=True,use_container_width=True)
        if p.get('ocr_previews'):
            with st.expander('Ver fotografías originales de este lote',expanded=False):
                for label,img in p['ocr_previews']:
                    st.image(img,caption=label,width=650)
        with st.expander('Transcripción completa del OCR'):
            st.text_area('Texto detectado',value=p['ocr_raw'],height=280)
            st.download_button('Descargar texto OCR',p['ocr_raw'].encode(),file_name=f'POP_DDV_{period_key(view_period)}_ocr.txt')

with page_items:
    st.subheader(f'Control editable por material · {view_period}')
    st.caption('Blanco significa material no verificado; 0 significa cero unidades recibidas, comprobado.')
    col1,col2,col3=st.columns([2,2,1])
    sheet=col1.selectbox('Hoja del Excel',['Todas']+sorted(set(r['hoja'] for r in rows)),key=f'filter_sheet_{period_key(view_period)}')
    status=col2.selectbox('Estado',['Todos','Diferencias y pendientes','Coincide','Faltante','Sobrante','Pendiente','Sin movimiento'],key=f'filter_status_{period_key(view_period)}')
    show_zero=col3.checkbox('Ver ceros Excel',value=False,key=f'filter_zero_{period_key(view_period)}')
    display=[r for r in rows if (sheet=='Todas' or r['hoja']==sheet)
             and (show_zero or r['cantidad_excel']>0 or r['verificado'])
             and (status=='Todos' or (r['estado'] in ('Faltante','Sobrante','Pendiente')
                 if status=='Diferencias y pendientes' else r['estado']==status))]
    manual=[{'ID':r['id'],'Hoja':r['hoja'],'Material':p['aliases'].get(r['id']) or r['material'],
             'Celda':r['celda'],'Excel':r['cantidad_excel'],
             'Remito':p['remito_entries'].get(r['id']),
             'Diferencia':r['diferencia'],'Estado':r['estado']} for r in display]
    if not manual:st.info('No hay materiales para estos filtros.')
    else:
        with st.form(f'form_manual_{period_key(view_period)}_{p["edit_version"]}_{sheet}_{status}_{show_zero}'):
            manual_edit=st.data_editor(pd.DataFrame(manual),hide_index=True,use_container_width=True,
                height=530,num_rows='fixed',
                column_config={'ID':None,'Material':st.column_config.TextColumn('Material',width='large'),
                    'Excel':st.column_config.NumberColumn('Excel',format='%d'),
                    'Remito':st.column_config.NumberColumn('Remito',min_value=0,step=1,format='%d')},
                disabled=['ID','Hoja','Material','Celda','Excel','Diferencia','Estado'])
            manual_save=st.form_submit_button('Guardar correcciones de este trimestre',type='primary')
        if manual_save:
            update=dict(p['remito_entries'])
            for obj in manual_edit.to_dict('records'):
                amount=integer_quantity(obj['Remito'])
                if amount is None:update.pop(obj['ID'],None)
                else:update[obj['ID']]=amount
            p['remito_entries']=update;p['edit_version']+=1
            p['is_complete']=False;p['preliminary']=True;p['last_updated']=now_label()
            st.rerun()
    st.divider()
    blocked=bool(p['unmatched']) or not p['remito_entries']
    if not p['is_complete']:
        st.caption('Para cerrar el remito debe haber cantidades registradas, no quedar renglones OCR sin resolver y haberse revisado físicamente TODAS sus páginas.')
        if st.button('✅ Marcar remito completamente revisado',disabled=blocked,key=f'finish_{period_key(view_period)}'):
            p['is_complete']=True;p['preliminary']=False;p['last_updated']=now_label();st.rerun()
    else:
        if st.button('Reabrir revisión del remito',key=f'reopen_{period_key(view_period)}'):
            p['is_complete']=False;p['preliminary']=True;p['last_updated']=now_label();st.rerun()
    with st.expander('Reiniciar cantidades de este trimestre'):
        st.warning('Esta acción borra solo las cantidades de remito de este período. No modifica los otros trimestres ni las asignaciones del Excel.')
        if st.button(f'Borrar cantidades de {view_period}',key=f'clear_{period_key(view_period)}'):
            p['remito_entries']={};p['unmatched']=[];p['is_complete']=False;p['preliminary']=False
            p['edit_version']+=1;p['last_updated']=now_label();st.rerun()

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
        update_names=st.form_submit_button('Guardar nombres para este trimestre')
    if update_names:
        p['aliases']={r['ID']:str(r['Descripción personalizada']).strip()
                      for r in aliases_data.to_dict('records')
                      if str(r['Descripción personalizada']).strip() not in ('','nan','None')}
        p['last_updated']=now_label();p['edit_version']+=1;st.rerun()

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
    st.info('Los datos del remito se procesan en el servidor. Los respaldos JSON conservan resultados y correcciones, pero NO contienen las fotografías ni los Excel completos. Si el hosting reinicia, restaurá el JSON.')

st.divider()
st.caption('POP liviano · DDV · Cada trimestre es independiente. Nunca se considera una cifra OCR como recepción física certificada sin revisión.')
