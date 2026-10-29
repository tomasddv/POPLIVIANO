"""Controles físicos por material, separados de las cifras OCR originales.

La cantidad registrada en el remito nunca se modifica al aprobar una ficha:
el valor conciliado se obtiene aplicando una confirmación auditada. Revocar
una aprobación restaura la lectura original sin perder historia.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import csv
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


def reconciled_rows(period: dict, include_hidden: bool = True) -> list[dict]:
    """Concilia todas las versiones de pop_core (4 o 5 argumentos).

    Algunas instalaciones de GitHub conservan pop_core.py de una versión
    anterior, cuya función reconcile solo admite cuatro argumentos. Las
    verificaciones físicas se aplican aquí, después de la conciliación base,
    para que no importe qué versión de reconcile esté instalada.
    """
    quantities = period.get('remito_entries') or {}
    completed = bool(period.get('is_complete', False))
    checks = period.get('physical_checks') or {}
    # Exactamente cuatro argumentos: compatible con la función antigua y nueva.
    rows = reconcile(period['catalog'], quantities, completed, include_hidden)

    for row in rows:
        material_id = row['id']
        expected = integer_quantity(row.get('cantidad_excel'))
        if expected is None:
            raise ValueError(f'Cantidad Excel inválida para {material_id}.')
        raw = quantities.get(material_id)
        original = integer_quantity(raw) if raw is not None else (0 if completed else None)
        if original is None:
            original_status = 'Pendiente' if expected > 0 else 'Sin movimiento'
        elif original == expected:
            original_status = 'Coincide'
        elif original < expected:
            original_status = 'Faltante'
        else:
            original_status = 'Sobrante'

        verification = checks.get(material_id)
        verified = verification is not None
        reconciled = expected if verified else original
        delta = reconciled - expected if reconciled is not None else None
        if delta is None:
            status = 'Pendiente' if expected > 0 else 'Sin movimiento'
        elif delta == 0:
            status = 'Coincide'
        elif delta < 0:
            status = 'Faltante'
        else:
            status = 'Sobrante'

        row.update(cantidad_remito=reconciled,
                   cantidad_remito_original=original,
                   diferencia=delta,
                   estado=status,
                   estado_original=original_status,
                   verificacion_fisica=verified,
                   fecha_verificacion=verification.get('fecha') if verified else None,
                   verificado=material_id in quantities or verified)
    return rows


def metrics(rows: list[dict]) -> dict:
    """Métricas completas incluso con un pop_core.py antiguo."""
    return {
        'asignado': sum(r['cantidad_excel'] for r in rows),
        'recibido': sum(r['cantidad_remito'] or 0 for r in rows),
        'coinciden': sum(r['estado'] == 'Coincide' for r in rows),
        'diferencias': sum(r['estado'] in ('Faltante', 'Sobrante') for r in rows),
        'pendientes': sum(r['estado'] == 'Pendiente' for r in rows),
        'verificados_fisicos': sum(bool(r.get('verificacion_fisica')) for r in rows),
        'remito_original': sum(r.get('cantidad_remito_original') or 0 for r in rows),
        'faltan_unidades': sum(-r['diferencia'] for r in rows if r['diferencia'] is not None and r['diferencia'] < 0),
        'sobran_unidades': sum(r['diferencia'] for r in rows if r['diferencia'] is not None and r['diferencia'] > 0),
    }


def to_csv(rows: list[dict]) -> bytes:
    """Exporta cifras originales y conciliadas sin depender de pop_core."""
    f = StringIO()
    cols = ['hoja', 'grupo', 'formato', 'material', 'celda', 'cantidad_excel',
            'cantidad_remito_original', 'cantidad_remito', 'diferencia', 'estado',
            'estado_original', 'verificacion_fisica', 'fecha_verificacion',
            'verificado', 'oculta']
    writer = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return ('\ufeff' + f.getvalue()).encode('utf-8')
