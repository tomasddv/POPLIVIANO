"""Matriz tipo Excel de POP: fotos como columnas y cantidades en filas.

Las cantidades vienen de reconciled_rows(), no se modifican aquí. Todo el HTML
variable se escapa; sólo se incrustan JPEG de los activos locales ya guardados.
"""
from __future__ import annotations

import base64
from html import escape
from typing import Mapping


STATUS_COLORS = {
    'Coincide': '#D9FBE6',
    'Faltante': '#FFE1E1',
    'Sobrante': '#FFF1CC',
    'Pendiente': '#E9ECF2',
    'Sin movimiento': '#F4F5F7',
}


def fmt(value):
    if value is None:
        return '—'
    return f'{int(value):,}'.replace(',', '.')


def filter_visual_rows(rows: list[dict], aliases: Mapping[str, str],
                       sheet: str = 'Todas las hojas',
                       status: str = 'Todos', query: str = '', include_zero: bool = False) -> list[dict]:
    """Mantiene el orden del catálogo original, sin perder materiales sin lectura."""
    term=query.strip().casefold()
    output=[]
    for r in rows:
        if not include_zero and not (int(r['cantidad_excel']) > 0 or r.get('verificado') or r.get('cantidad_remito_original')):
            continue
        if sheet!='Todas las hojas' and r['hoja']!=sheet:
            continue
        if status=='Pendientes y diferencias' and not (r['estado'] in ('Pendiente','Faltante','Sobrante')):
            continue
        if status=='Coinciden' and r['estado']!='Coincide':
            continue
        if status=='Verificados físicamente' and not r.get('verificacion_fisica'):
            continue
        if status in ('Faltante','Sobrante','Pendiente') and r['estado']!=status:
            continue
        if term:
            haystack=' '.join(str(x or '') for x in (
                r['material'],r['hoja'],r['formato'],r['id'],aliases.get(r['id']),r.get('grupo'))).casefold()
            if term not in haystack:
                continue
        output.append(r)
    return output


def _clean(value):
    return escape(str(value or ''),quote=True)


def _cell_photo(row, asset_map, images):
    # Sólo se leen rutas exactas declaradas en el catálogo/almacenamiento.
    key=images.get(row['id'],'')
    blob=asset_map.get(key)
    if not isinstance(blob,bytes) or not blob:
        return '<div class="pop-no-photo">Sin imagen de POP</div>'
    image64=base64.b64encode(blob).decode('ascii')
    return (f'<img class="pop-img" src="data:image/jpeg;base64,{image64}" '
            f'alt="Imagen de {_clean(row["material"])}" loading="lazy">')


def _status(row):
    if row.get('verificacion_fisica'):
        return '✓ Verificado físicamente', '#D9FBE6'
    return row['estado'],STATUS_COLORS.get(row['estado'],'#F3F4F6')


def render_visual_matrix(rows: list[dict], aliases: Mapping[str,str],
                         image_map: Mapping[str,str], assets: Mapping[str,bytes],
                         image_height: int = 170) -> str:
    """Entrega tabla HTML horizontalmente desplazable, con letras negras."""
    if not rows:
        return '<p>No hay materiales para mostrar.</p>'
    num_cols=len(rows)
    head=['<th scope="col" class="pop-label-cell">Material</th>']
    pics=['<th scope="row" class="pop-label-cell">Fotografía</th>']
    assigned=['<th scope="row" class="pop-label-cell">Asignado DDV</th>']
    original=['<th scope="row" class="pop-label-cell">Remito original</th>']
    confirmed=['<th scope="row" class="pop-label-cell">Remito conciliado</th>']
    difference=['<th scope="row" class="pop-label-cell">Diferencia</th>']
    statuses=['<th scope="row" class="pop-label-cell">Estado</th>']
    for r in rows:
        name=aliases.get(r['id']) or r['formato'] or r['material']
        label=_clean(name)
        sheet=_clean(r['hoja']+' · '+str(r.get('celda','')))
        head.append(f'<th class="pop-item-title" scope="col">{label}<small>{sheet}</small></th>')
        pics.append(f'<td class="pop-photo-cell">{_cell_photo(r,assets,image_map)}</td>')
        assigned.append(f'<td class="pop-number">{fmt(r["cantidad_excel"])}</td>')
        original.append(f'<td class="pop-number">{fmt(r.get("cantidad_remito_original"))}</td>')
        confirmed.append(f'<td class="pop-number">{fmt(r.get("cantidad_remito"))}</td>')
        d=r.get('diferencia')
        d_text='—' if d is None else ('+'+fmt(d) if d>0 else fmt(d))
        d_color='#1D6A3D' if d==0 else '#A52834' if (d is not None and d<0) else '#9B6200' if d else '#111827'
        difference.append(f'<td class="pop-number" style="background:{d_color}10">{_clean(d_text)}</td>')
        caption,color=_status(r)
        statuses.append(f'<td class="pop-status" style="background:{color}">{_clean(caption)}</td>')
    def tr(tds):return '<tr>'+''.join(tds)+'</tr>'
    table=''.join([
        '<thead>',tr(head),'</thead>',
        '<tbody>',tr(pics),tr(assigned),tr(original),tr(confirmed),tr(difference),tr(statuses),'</tbody>'
    ])
    return f'''<div class="pop-matrix-frame" role="region" aria-label="Tabla visual de materiales POP" tabindex="0">
<style>
.pop-matrix-frame {{background:#fff;overflow-x:auto;border:1px solid #CBD5E1;border-radius:12px;padding:0;margin:12px 0 24px;}}
.pop-matrix-frame,.pop-matrix-frame * {{color:#000!important; -webkit-text-fill-color:#000!important; box-sizing:border-box;}}
.pop-matrix {{border-collapse:separate;border-spacing:0;table-layout:fixed;min-width:{max(740,180+num_cols*225)}px;width:100%;font:14px system-ui,-apple-system,'Segoe UI',sans-serif;}}
.pop-matrix th,.pop-matrix td {{border-right:1px solid #D5DEEB;border-bottom:1px solid #D5DEEB;vertical-align:middle;text-align:center;padding:10px 8px;overflow-wrap:anywhere;background:#fff;}}
.pop-matrix th:last-child,.pop-matrix td:last-child {{border-right:0;}}
.pop-matrix tbody tr:last-child td,.pop-matrix tbody tr:last-child th {{border-bottom:0;}}
.pop-matrix .pop-label-cell {{width:180px;min-width:180px;position:sticky;left:0;z-index:2;background:#E9EFF7!important;text-align:left;font-weight:750;padding-left:12px;white-space:normal;}}
.pop-matrix thead .pop-label-cell {{z-index:3;}}
.pop-matrix .pop-item-title {{background:#E8F1FF!important;font-weight:750;line-height:1.3;font-size:13px;}}
.pop-matrix .pop-item-title small {{display:block;font-size:11px;font-weight:450;margin-top:5px;}}
.pop-matrix .pop-img {{width:100%;max-width:210px;height:{image_height}px;object-fit:contain;background:#fff;border:1px solid #EDF0F5;border-radius:7px;}}
.pop-matrix .pop-no-photo {{height:{image_height}px;display:flex;align-items:center;justify-content:center;border:1px dashed #CBD5E1;border-radius:7px;background:#F7F9FC!important;font-size:12px;}}
.pop-matrix .pop-number {{font-size:19px;font-weight:800;font-variant-numeric:tabular-nums;}}
.pop-matrix .pop-status {{font-size:12px;font-weight:750;}}
.pop-matrix .pop-photo-cell {{height:{image_height+23}px;}}
</style><table class="pop-matrix" aria-label="POP con foto y cantidades por material">{table}</table></div>'''
