"""Control de POP liviano — Distribuidora del Valle | GitHub + Streamlit Community Cloud.
Iniciar: streamlit run app.py
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
import json
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pop_core import catalog_from_excel, integer_quantity, metrics, reconcile, suggest_matches, to_csv
from ocr_core import read_documents

st.set_page_config(page_title='POP Liviano | DDV',page_icon='📦',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
.stApp {background:#F4F7FC}
h1,h2,h3 {letter-spacing:-.025em;color:#142B4C}
[data-testid="stMetric"] {background:white;border:1px solid #E1E8F2;border-radius:13px;padding:15px 19px}
[data-testid="stMetricLabel"]{font-weight:600;color:#536781}
[data-testid="stMetricValue"]{color:#183A68}
[data-testid="stSidebar"]{background:#13263F}
[data-testid="stSidebar"] *{color:#EAF1F8}
[data-testid="stSidebar"] button{color:#18304D}
[data-testid="stSidebar"] input{color:#18304D!important}
.stTabs [data-baseweb="tab"]{padding:9px 16px}
div.stButton > button[kind="primary"]{background:#1769D2;border-radius:9px}
</style>''',unsafe_allow_html=True)


def count_fmt(n): return f'{int(n):,}'.replace(',','.')


def reset_source(content):
    digest=sha256(content).hexdigest()
    if st.session_state.get('source_digest')!=digest:
        catalog,issues,sheets=catalog_from_excel(content)
        st.session_state.update(source_digest=digest,catalog=catalog,issues=issues,sheets=sheets,
            remito_entries={},ocr_rows=[],ocr_raw='',ocr_previews=[],ocr_warnings=[],
            ocr_version=0,ocr_edit_ver=0,ocr_edited_rows=None,edit_version=0,aliases={},unmatched=[],is_complete=False,
            remito_signature=None,checked_source=False)
    return digest


def rows_dataframe(items):
    return pd.DataFrame(items)


def reviewed_ocr_to_items(items):
    additions=defaultdict(int);unmatched=[];accepted=0
    for r in items:
        if bool(r.get('Ignorar',False)):continue
        selected=str(r.get('Material Excel','') or '')
        qty=integer_quantity(r.get('Cantidad'))
        ident=selected.split(' | ',1)[0] if ' | ' in selected else ''
        if ident in valid_ids and qty is not None:
            additions[ident]+=qty;accepted+=1
        else:
            unmatched.append({'pagina':r.get('Página',''),'cantidad':qty,'detalle':r.get('Descripción OCR',''),
                'sugerencia':r.get('Sugerencia',''), 'motivo':'Cantidad sin verificar' if qty is None else 'Sin material asociado'})
    return dict(additions),unmatched,accepted


def options_for_catalog(catalog,aliases):
    names={}
    for c in catalog:
        extra=aliases.get(c['id'],'').strip()
        label=(extra if extra else c['material'])
        names[c['id']]=f"{c['id']} | {label} [{c['celda']}]"
    return names


st.title('📦 Control de POP liviano')
st.caption('Conciliación trimestral de remitos · Exclusivamente Distribuidora del Valle S.A.')

with st.sidebar:
    st.markdown('### POP · DDV')
    st.caption('Control de recepción por material y por pestaña')
    period=st.text_input('Trimestre / período',value='Q4 2026',help='Ej.: GS Q4 2026')
    uploaded_excel=st.file_uploader('1. Excel de asignaciones (.xlsx)',type=['xlsx'],help='Se utiliza la fila de Distribuidora del Valle S.A. en cada hoja, también las ocultas.')
    uploaded_remito=st.file_uploader('2. Remito: fotos o PDF (1 a 3 páginas)',type=['png','jpg','jpeg','webp','pdf'],accept_multiple_files=True)
    two_col=st.checkbox('Remito con 2 columnas de materiales',value=True)
    split=st.slider('Separación de las dos columnas (%)',42,58,50,1,disabled=not two_col,
                    help='Si una cantidad queda cortada en la foto, mové el separador y volvé a leer.')/100
    include_hidden=st.checkbox('Incluir hojas ocultas del Excel',value=True)
    st.divider()
    st.caption('El OCR funciona en el servidor, sin servicios externos de reconocimiento. Ningún resultado se considera definitivo sin revisión.')

if uploaded_excel is None:
    st.info('**Empezá subiendo el Excel de asignación Q4 y las imágenes del remito en la barra lateral.** Luego presioná «Leer e interpretar remito».')
    a,b,c=st.columns(3)
    a.markdown('**1 · Cargar**\n\nExcel Q4 + hasta 3 fotos / páginas del remito.')
    b.markdown('**2 · Revisar**\n\nOCR de cantidades, sugerencias de materiales y correcciones.')
    c.markdown('**3 · Comparar**\n\nCoincidencias, faltantes, sobrantes y exportación del control.')
    st.stop()

try: raw_excel=uploaded_excel.getvalue();digest=reset_source(raw_excel)
except Exception as e:
    st.error(f'No pude leer el Excel: {e}');st.stop()
catalog=st.session_state['catalog'];meta=st.session_state['sheets'];issues=st.session_state['issues']
valid_ids={c['id'] for c in catalog};aliases=st.session_state['aliases']
if not catalog:
    st.error('El Excel no contiene cantidades identificadas en la fila «Distribuidora del Valle S.A.». Consultá la hoja de auditoría y verificá que sea el archivo de asignación.');
    with st.expander('Alertas de lectura de Excel',expanded=True):
        for item in issues:st.write('•',item)
    st.stop()

names=options_for_catalog(catalog,aliases)
selection_options=['(sin asignar)']+list(names.values())

with st.sidebar:
    st.success(f'{len(catalog)} columnas de POP detectadas en {len([m for m in meta if m["fila_ddv"] is not None])} hojas con DDV.')
    if uploaded_remito:
        total_photos=sum(1 for f in uploaded_remito if f.name.lower().endswith(('.png','.jpg','.jpeg','.webp')))
        if total_photos>3:st.warning('Se analizarán como máximo tres páginas.')
    if st.button('🔍 Leer e interpretar remito',type='primary',use_container_width=True,disabled=not uploaded_remito):
        signature=sha256(''.join(f.name+sha256(f.getvalue()).hexdigest() for f in uploaded_remito).encode()).hexdigest()
        try:
            with st.spinner('Extrayendo texto y cantidades de todas las páginas…'):
                files=[(f.name,f.getvalue()) for f in uploaded_remito]
                result=read_documents(files,two_columns=two_col,split=split,max_pages=3)
                suggestions=suggest_matches(result.rows,catalog,aliases)
            st.session_state['ocr_rows']=suggestions
            st.session_state['ocr_edited_rows']=None
            st.session_state['ocr_edit_ver']=0
            st.session_state['ocr_previews']=result.images
            st.session_state['ocr_raw']=result.raw_text
            st.session_state['ocr_warnings']=result.warnings
            st.session_state['ocr_version']+=1
            st.session_state['remito_signature']=signature
            st.session_state['unmatched']=[]
            st.session_state['is_complete']=False
            st.session_state['remito_entries']={}
            st.success(f'{len(suggestions)} renglones de materiales identificados. Revisalos antes de aplicarlos.')
        except Exception as ex: st.error(f'Error en reconocimiento: {ex}')

rows=reconcile(catalog,st.session_state['remito_entries'],st.session_state['is_complete'],include_hidden)
summary=metrics(rows)
unmatched=st.session_state['unmatched']
a,b,c,d,e=st.columns(5)
a.metric('Asignado DDV',count_fmt(summary['asignado']))
b.metric('Declarado en remito',count_fmt(summary['recibido']))
c.metric('Coinciden',summary['coinciden'])
d.metric('Diferencias',summary['diferencias'])
e.metric('Pendientes',summary['pendientes'])

if st.session_state['is_complete']:
    st.success('Remito marcado como completamente revisado. Los materiales asignados que no figuren se contabilizan como faltantes.')
elif st.session_state['remito_entries']:
    st.warning('**Conciliación preliminar:** todavía no se confirmó la revisión completa del remito. Las asignaciones sin lectura se muestran como pendientes, no como faltantes.')
else:
    st.info('Aún no hay cantidades confirmadas del remito. Hacé la lectura OCR y revisá las asignaciones detectadas.')
if unmatched:st.error(f'Hay {len(unmatched)} renglones del remito sin conciliar. Revisalos en «Lectura OCR».')

page1,page2,page3,page4,page5=st.tabs(['📷 Lectura OCR','📊 Resumen','🧾 Control por material','🏷️ Identificar materiales','📥 Exportar y auditar'])

with page1:
    st.subheader('Lectura e interpretación de remitos')
    st.caption('El OCR reconoce texto y cantidades, pero puede errar cuando la imagen está borrosa, inclinada o contiene números pequeños. Las coincidencias automáticas son sugerencias que siempre se revisan.')
    if st.session_state['ocr_warnings']:
        for warn in st.session_state['ocr_warnings']:st.warning(warn)
    ocr=st.session_state['ocr_rows']
    if not ocr:
        st.info('Subí uno o más archivos en el panel izquierdo y hacé clic en «Leer e interpretar remito».')
    else:
        num_qty=sum(r.get('cantidad') is not None for r in ocr)
        num_suggest=sum(bool(r.get('sugerido')) for r in ocr)
        aa,bb,cc=st.columns(3)
        aa.metric('Renglones OCR',len(ocr))
        bb.metric('Con cantidad',num_qty)
        cc.metric('Con sugerencia',num_suggest)
        st.markdown('**Paso de revisión:** corregí las cantidades, elegí el material Excel para cada línea y marcá «Ignorar» solo en líneas que no correspondan a POP.')
        preview=[]
        for item in ocr:
            candidate=item.get('id','')
            preview.append({'Página':item['pagina'], 'Cantidad':item['cantidad'],
                            'Descripción OCR':item['detalle'],
                            'Material Excel':names.get(candidate,'(sin asignar)'),
                            'Sugerencia':names.get(item.get('sugerido',''),'—'),
                            'Lectura':item.get('estado_match',''), 'Ignorar':False})
        if st.session_state.get('ocr_edited_rows') is not None:
            preview=st.session_state['ocr_edited_rows']
        with st.form(key=f'review_ocr_{st.session_state["ocr_version"]}_{st.session_state["ocr_edit_ver"]}'):
            modified=st.data_editor(pd.DataFrame(preview),hide_index=True,use_container_width=True,num_rows='dynamic',height=530,
                column_order=['Página','Cantidad','Descripción OCR','Material Excel','Sugerencia','Lectura','Ignorar'],
                column_config={
                    'Página':st.column_config.TextColumn('Página',width='medium'),
                    'Cantidad':st.column_config.NumberColumn('Cantidad',min_value=0,step=1,format='%d',help='En blanco significa cantidad no reconocida'),
                    'Descripción OCR':st.column_config.TextColumn('Descripción OCR',width='large'),
                    'Material Excel':st.column_config.SelectboxColumn('Material Excel',options=selection_options,required=False,width='large'),
                    'Sugerencia':st.column_config.TextColumn('Sugerencia',width='large'),
                    'Lectura':st.column_config.TextColumn('Lectura',width='small'),
                    'Ignorar':st.column_config.CheckboxColumn('Ignorar',default=False),
                },disabled=['Página','Sugerencia','Lectura'])
            submitted=st.form_submit_button('✅ Aplicar lectura revisada a la conciliación',type='primary',use_container_width=True)
        if submitted:
            items=modified.to_dict('records')
            st.session_state['ocr_edited_rows']=items
            st.session_state['ocr_edit_ver']+=1
            qty,unresolved,accepted=reviewed_ocr_to_items(items)
            st.session_state['remito_entries']=qty
            st.session_state['unmatched']=unresolved
            st.session_state['is_complete']=False
            st.session_state['edit_version']+=1
            st.toast(f'{accepted} líneas aplicadas. {len(unresolved)} por resolver.')
            st.rerun()
        if unmatched:
            st.markdown('**Líneas sin conciliar (no cuentan como recibidas)**')
            st.dataframe(pd.DataFrame(unmatched),hide_index=True,use_container_width=True)
        if st.session_state['ocr_previews']:
            with st.expander('Ver fotografías originales de las páginas',expanded=False):
                for caption,photo in st.session_state['ocr_previews']:
                    st.image(photo,caption=caption,use_container_width=False,width=600)
        with st.expander('Consultar la transcripción OCR íntegra',expanded=False):
            st.text_area('Texto detectado',st.session_state['ocr_raw'],height=320)
            st.download_button('Descargar transcripción OCR',st.session_state['ocr_raw'].encode('utf-8'),file_name='POP_DDV_transcripcion_OCR.txt')

with page2:
    st.subheader('Conciliación por pestaña del Excel')
    st.caption(f'Período {period} · Filtro exclusivo DDV · {"Incluye" if include_hidden else "Excluye"} hojas ocultas')
    group=defaultdict(lambda:{'asignado':0,'recibido':0,'diferencias':0,'pendientes':0})
    for r in rows:
        g=group[r['hoja']];g['asignado']+=r['cantidad_excel'];g['recibido']+=r['cantidad_remito'] or 0
        g['diferencias']+=int(r['estado'] in ('Faltante','Sobrante'))
        g['pendientes']+=int(r['estado']=='Pendiente')
    chosen=sorted([(k,v) for k,v in group.items() if v['asignado'] or v['recibido']],key=lambda i:i[1]['asignado'],reverse=True)
    if chosen:
        fig=go.Figure()
        for name,key,color in [('Asignado','asignado','#2575C7'),('Remito validado','recibido','#E8A248')]:
            fig.add_trace(go.Bar(name=name,x=[v[key] for _,v in chosen],y=[k for k,_ in chosen],orientation='h',marker_color=color))
        fig.update_layout(barmode='group',height=max(330,38*len(chosen)+100),margin=dict(l=12,r=10,t=5,b=15),
            legend=dict(orientation='h',y=1.07),xaxis=dict(title='Unidades',gridcolor='#E7EDF4'),
            yaxis=dict(autorange='reversed'),plot_bgcolor='#FFFFFF',paper_bgcolor='#FFFFFF')
        st.plotly_chart(fig,use_container_width=True,config={'displayModeBar':False})
    if summary['diferencias']:
        x,y=st.columns(2);x.metric('Unidades faltantes',count_fmt(summary['faltan_unidades']))
        y.metric('Unidades sobrantes',count_fmt(summary['sobran_unidades']))
    st.markdown('**Materiales que requieren atención**')
    attentions=[r for r in rows if r['estado'] in ('Pendiente','Faltante','Sobrante')]
    if attentions:
        st.dataframe(pd.DataFrame([{'Estado':r['estado'],'Hoja':r['hoja'],'Material':r['material'],
            'Excel':r['cantidad_excel'],'Remito':r['cantidad_remito'],'Diferencia':r['diferencia'], 'Celda':r['celda']}
            for r in sorted(attentions,key=lambda r:(0 if r['estado']!='Pendiente' else 1,-r['cantidad_excel']))]),
            hide_index=True,use_container_width=True,height=min(500,40*len(attentions)+50))
    else:st.success('Sin diferencias ni materiales pendientes en el alcance seleccionado.')
    st.markdown('**Resumen por hoja**')
    st.dataframe(pd.DataFrame([{'Hoja':k,'Asignado':v['asignado'],'Remito':v['recibido'],
        'Diferencias':v['diferencias'],'Pendientes':v['pendientes']} for k,v in group.items()]),
        hide_index=True,use_container_width=True)

with page3:
    st.subheader('Control editable por material')
    st.caption('Podés ingresar o corregir cantidades manualmente. **Blanco = sin verificar**. **0 = confirmado como no recibido**.')
    c1,c2,c3=st.columns([2,2,1])
    with c1:sheet_filter=st.selectbox('Pestaña', ['Todas']+sorted(set(r['hoja'] for r in rows)))
    with c2:status_filter=st.selectbox('Estado',['Todos','Diferencias y pendientes','Coincide','Faltante','Sobrante','Pendiente','Sin movimiento'])
    with c3:include_empty=st.checkbox('Ver ceros de Excel',False)
    displayed=[r for r in rows if (sheet_filter=='Todas' or r['hoja']==sheet_filter)
            and (include_empty or r['cantidad_excel']>0 or r['verificado'])
            and (status_filter=='Todos' or (r['estado'] in ('Faltante','Sobrante','Pendiente') if status_filter=='Diferencias y pendientes' else r['estado']==status_filter))]
    data=[{'ID':r['id'],'Hoja':r['hoja'],'Material':aliases.get(r['id']) or r['material'],
         'Celda':r['celda'],'Asignado':r['cantidad_excel'],
         'Recibido':st.session_state['remito_entries'].get(r['id']),
         'Diferencia':r['diferencia'],'Estado':r['estado']} for r in displayed]
    apply_manual=False
    if not data:
        st.info('No hay materiales para los filtros seleccionados.')
    else:
        with st.form(key=f'edit_manual_{st.session_state["edit_version"]}_{sheet_filter}_{status_filter}_{include_empty}'):
            edited=st.data_editor(pd.DataFrame(data),use_container_width=True,hide_index=True,num_rows='fixed',height=560,
                column_config={'ID':None,'Material':st.column_config.TextColumn('Material',width='large'),
                    'Recibido':st.column_config.NumberColumn('Recibido',format='%d',min_value=0,step=1),
                    'Asignado':st.column_config.NumberColumn('Asignado',format='%d')},
                disabled=['ID','Hoja','Material','Celda','Asignado','Diferencia','Estado'])
            apply_manual=st.form_submit_button('Guardar correcciones manuales',type='primary')
    if apply_manual:
        update=dict(st.session_state['remito_entries'])
        for r in edited.to_dict('records'):
            qty=integer_quantity(r['Recibido'])
            if qty is None:update.pop(r['ID'],None)
            else:update[r['ID']]=qty
        st.session_state['remito_entries']=update
        st.session_state['edit_version']+=1
        st.session_state['is_complete']=False
        st.rerun()
    st.divider()
    cannot_finish=bool(unmatched) or not st.session_state['remito_entries']
    if cannot_finish:
        st.caption('Para cerrar la revisión debe existir al menos una cantidad confirmada y no puede quedar ninguna línea OCR sin asociar o ignorar.')
    # Una marca explícita evita convertir silenciosamente líneas borrosas en faltantes.
    new_complete=st.checkbox('✅ Confirmo que revisé TODAS las páginas del remito y las cantidades del control',
                  value=st.session_state['is_complete'],disabled=cannot_finish)
    if new_complete!=st.session_state['is_complete']:
        st.session_state['is_complete']=new_complete;st.rerun()
    if st.button('Borrar todas las cantidades cargadas'):
        st.session_state['remito_entries']={};st.session_state['unmatched']=[]
        st.session_state['is_complete']=False;st.session_state['edit_version']+=1;st.rerun()

with page4:
    st.subheader('Identificar materiales ambiguos del Excel')
    st.caption('Algunas columnas se llaman únicamente «20x30» o «7x3,5», pero representan campañas distintas. Escribí un nombre más específico para mejorar las próximas sugerencias OCR. No modifica el Excel.')
    alias_upload=st.file_uploader('Importar nombres guardados de este mismo archivo (JSON)',type=['json'],key='alias_import')
    if st.button('Importar nombres',disabled=alias_upload is None):
        try:
            data=json.loads(alias_upload.getvalue())
            if data.get('source_digest')!=digest:st.error('Este diccionario pertenece a un Excel diferente. No se importó.')
            else:
                st.session_state['aliases']={k:str(v) for k,v in data.get('aliases',{}).items() if k in valid_ids}
                st.rerun()
        except Exception as ex:st.error(f'JSON inválido: {ex}')
    with st.form('aliases_form'):
        alias_rows=[{'ID':c['id'],'Hoja':c['hoja'],'Etiqueta original':c['material'],
                     'Nombre específico (opcional)':aliases.get(c['id'],'')} for c in catalog if c['cantidad_excel']>0]
        aliased=st.data_editor(pd.DataFrame(alias_rows),hide_index=True,use_container_width=True,
            height=430,num_rows='fixed',disabled=['ID','Hoja','Etiqueta original'],
            column_config={'Etiqueta original':st.column_config.TextColumn('Etiqueta original',width='large'),
                           'Nombre específico (opcional)':st.column_config.TextColumn('Nombre específico (opcional)',width='large')})
        save_alias=st.form_submit_button('Guardar nombres personalizados')
    if save_alias:
        st.session_state['aliases']={r['ID']:str(r['Nombre específico (opcional)']).strip()
                     for r in aliased.to_dict('records') if str(r['Nombre específico (opcional)']).strip() not in ('','nan','None')}
        st.success('Nombres actualizados. Volvé a interpretar el remito para recalcular sugerencias.')
    st.download_button('Descargar diccionario de nombres (JSON)',
        json.dumps({'source_digest':digest,'aliases':st.session_state['aliases']},ensure_ascii=False,indent=2).encode('utf-8'),
        file_name=f'POP_DDV_diccionario_{re.sub(r"[^A-Za-z0-9-]","_",period)}.json',mime='application/json')

with page5:
    st.subheader('Exportación y trazabilidad')
    st.download_button('⬇️ Descargar conciliación CSV (Excel)',to_csv(rows),
        file_name=f'POP_DDV_{re.sub(r"[^A-Za-z0-9-]","_",period)}_conciliacion.csv',
        mime='text/csv',type='primary')
    backup={'version':1,'periodo':period,'fecha_exportacion':datetime.now().isoformat(timespec='seconds'),
        'source_digest':digest,'archivo_excel':uploaded_excel.name,
        'remito_completo':st.session_state['is_complete'],'cantidades':st.session_state['remito_entries'],
        'aliases':st.session_state['aliases'],'unmatched':st.session_state['unmatched']}
    st.download_button('💾 Guardar avance como JSON (para continuar otro día)',
        json.dumps(backup,ensure_ascii=False,indent=2).encode('utf-8'),
        file_name=f'POP_DDV_{re.sub(r"[^A-Za-z0-9-]","_",period)}_respaldo.json',mime='application/json')
    backup_upload=st.file_uploader('Restaurar avance previamente guardado (JSON)',type=['json'],key='backup_upload')
    if st.button('Restaurar avance',disabled=backup_upload is None):
        try:
            data=json.loads(backup_upload.getvalue())
            if data.get('source_digest')!=digest:st.error('El respaldo pertenece a otro Excel. Subí el Excel correspondiente antes de restaurarlo.')
            else:
                st.session_state['remito_entries']={k:v for k,v in data.get('cantidades',{}).items() if k in valid_ids}
                st.session_state['aliases']={k:v for k,v in data.get('aliases',{}).items() if k in valid_ids}
                st.session_state['unmatched']=data.get('unmatched',[])
                st.session_state['is_complete']=bool(data.get('remito_completo',False))
                st.session_state['edit_version']+=1;st.rerun()
        except Exception as ex:st.error(f'No fue posible abrir ese respaldo: {ex}')
    st.markdown('**Hojas inspeccionadas (incluidas las ocultas)**')
    st.dataframe(pd.DataFrame([{'Hoja':m['hoja'],'Oculta':('Sí' if m['oculta'] else 'No'),
            'Fila DDV':m['fila_ddv'],'Columnas POP':m['materiales'],'Unidades DDV':m['total'],
            'Fila cabeceras':m['cabecera']} for m in meta]),hide_index=True,use_container_width=True)
    if issues:
        st.markdown('**Observaciones de lectura del Excel**')
        for issue in issues:st.caption('• '+issue)
    st.caption('Seguridad: en Streamlit Community Cloud, la sesión y sus datos no son un archivo histórico persistente. Descargá el respaldo JSON. No subas datos sensibles a una app pública sin controles de acceso.')

st.divider()
st.caption('POP liviano · DDV · Carga nueva cada trimestre · El remito declara cantidades; la conformidad física requiere verificación del depósito.')
