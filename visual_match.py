"""Buscador visual y asignación manual de material Excel a una fila OCR.

La selección por foto solo cambia la identidad del POP. No inventa, altera
ni rellena la cantidad leída del remito.
"""
from __future__ import annotations
from copy import deepcopy
from pop_core import normalize, integer_quantity


def visual_candidates(catalog, aliases, query='', sheet='Todas', preferred=(),
                      only_with_image=False, image_map=None, assets=None):
    """Materiales ordenados por sugerencias OCR, con filtros de búsqueda y foto."""
    image_map = image_map or {}
    assets = assets or {}
    preference = {id_: i for i, id_ in enumerate(preferred)}
    terms = normalize(query).split()
    result = []
    for material in catalog:
        cid = material['id']
        if sheet != 'Todas' and material['hoja'] != sheet:
            continue
        has_image = image_map.get(cid) in assets
        if only_with_image and not has_image:
            continue
        haystack = normalize(' '.join(str(x or '') for x in (
            aliases.get(cid,''), material.get('material',''),
            material.get('formato',''), material.get('hoja',''),
            material.get('grupo',''),cid)))
        if terms and not all(t in haystack for t in terms):
            continue
        result.append(material)
    result.sort(key=lambda m: (
        0 if m['id'] in preference else 1,
        preference.get(m['id'],9999),
        0 if int(m.get('cantidad_excel') or 0) > 0 else 1,
        m['hoja'].casefold(),m['formato'].casefold(),m['id']))
    return result


def preferred_ocr_ids(ocr_row):
    """Sugerencia principal y alternativas reconocidas, sin duplicados."""
    if not isinstance(ocr_row,dict):
        return []
    values = [ocr_row.get('sugerido'),ocr_row.get('id')]
    values.extend(x.get('id') for x in ocr_row.get('alternativas',[]) if isinstance(x,dict))
    return list(dict.fromkeys(v for v in values if v))


def choose_material(rows, row_index, material_id, names, catalog):
    """Vincula POP por foto, dejando intactas cantidad y descripción del OCR."""
    if not isinstance(row_index,int) or row_index < 0 or row_index >= len(rows):
        raise IndexError('La fila OCR no existe.')
    lookup={c['id']:c for c in catalog}
    if material_id not in lookup or material_id not in names:
        raise ValueError('El material no está en el Excel del período.')
    updated=deepcopy(rows)
    entry=updated[row_index]
    excel_qty=int(lookup[material_id].get('cantidad_excel') or 0)
    ocr_qty=integer_quantity(entry.get('Cantidad'))
    entry['Material Excel']=names[material_id]
    entry['Excel sugerido']=excel_qty
    entry['Diferencia tentativa']=(ocr_qty-excel_qty) if ocr_qty is not None else None
    # La similitud calculada por OCR ya no aplica a la elección humana.
    entry['Similitud %']=None
    entry['Lectura']='Seleccionado manualmente por imagen'
    entry['Alertas del match']='Seleccionado por foto · revisar cantidad del remito'
    # Conservar la sugerencia OCR original, la cantidad leída y el texto tal cual.
    return updated
