"""Controles físicos por material, separados de las cifras OCR originales.

La cantidad registrada en el remito nunca se modifica al aprobar una ficha:
el valor conciliado se obtiene aplicando una confirmación auditada. Revocar
una aprobación restaura la lectura original sin perder historia.
"""
from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
from pop_core import integer_quantity, reconcile


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def approve_material(period: dict, material_id: str) -> dict:
    catalog = {row['id']: row for row in period.get('catalog', [])}
    if material_id not in catalog:
        raise ValueError('El material no existe en este trimestre.')
    c = catalog[material_id]
    expected = integer_quantity(c.get('cantidad_excel'))
    if expected is None:
        raise ValueError('La cantidad asignada del Excel no es válida.')
    checks = period.setdefault('physical_checks', {})
    if material_id in checks:
        return checks[material_id]
    original = period.get('remito_entries', {}).get(material_id)
    original = integer_quantity(original) if original is not None else None
    approval = {
        'fecha': _now(),
        'cantidad_original_remito': original,
        'cantidad_aprobada': expected,
        'remito_firma': period.get('ocr_signature'),
        'origen': 'Control presencial en galería POP',
    }
    checks[material_id] = approval
    period.setdefault('physical_events', []).append({
        'fecha': approval['fecha'], 'accion': 'Aprobado físicamente',
        'material_id': material_id, 'hoja': c.get('hoja', ''),
        'cantidad_remito_original': original, 'cantidad_conciliada': expected,
    })
    return approval


def undo_material(period: dict, material_id: str) -> bool:
    check = period.setdefault('physical_checks', {}).pop(material_id, None)
    if check is None:
        return False
    c = next((c for c in period.get('catalog', []) if c['id'] == material_id), {})
    period.setdefault('physical_events', []).append({
        'fecha': _now(), 'accion': 'Aprobación física anulada',
        'material_id': material_id, 'hoja': c.get('hoja', ''),
        'cantidad_remito_original': period.get('remito_entries', {}).get(material_id),
        'cantidad_conciliada': None,
    })
    return True


def invalidate_changed_checks(period: dict, old: dict, new: dict, reason: str) -> list[str]:
    """Revoca solo aprobaciones con cantidad de remito modificada; mantiene la auditoría."""
    impacted = [material_id for material_id in list(period.get('physical_checks', {}))
                if old.get(material_id) != new.get(material_id)]
    if not impacted:
        return []
    for material_id in impacted:
        undo_material(period, material_id)
        period['physical_events'][-1]['accion'] = 'Verificación invalidada por nueva información'
        period['physical_events'][-1]['motivo'] = reason
    return impacted


def clear_checks(period: dict, reason: str) -> None:
    for material_id in list(period.get('physical_checks', {})):
        undo_material(period, material_id)
        period['physical_events'][-1]['accion'] = 'Verificación invalidada por reinicio'
        period['physical_events'][-1]['motivo'] = reason


def reconciled_rows(period: dict, include_hidden=True):
    return reconcile(period['catalog'], period['remito_entries'],
                     period['is_complete'], include_hidden,
                     period.get('physical_checks', {}))
