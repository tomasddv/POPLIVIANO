"""Regresión del fallo real de despliegue: mezcla de módulos antiguos/nuevos."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from physical_checks import (reconciled_rows, approve_material,
                             undo_material, metrics, to_csv)
from period_store import empty_period
from pop_core import reconcile as current_reconcile


class DeploymentCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.p = empty_period()
        self.p['catalog'] = [{
            'id': 'Oferta::A', 'cantidad_excel': 100, 'hoja': 'Oferta',
            'oculta': False, 'grupo': 'Oferta', 'formato': 'AFICHE 20X30',
            'material': 'AFICHE 20X30', 'celda': 'A12'
        }]
        self.p['remito_entries'] = {'Oferta::A': 80}

    def test_legacy_four_argument_reconcile_and_approval(self):
        def reconcile_legacy(catalog, quantities, completed=False, include_hidden=True):
            # Esta es la misma firma de la versión que provocaba TypeError.
            return [dict(x, cantidad_remito=quantities.get(x['id']),
                         estado='Faltante', diferencia=-20, verificado=True)
                    for x in catalog if not x['oculta'] or include_hidden]

        with patch('physical_checks.reconcile', side_effect=reconcile_legacy) as legacy:
            pending = reconciled_rows(self.p)
            self.assertEqual(pending[0]['estado'], 'Faltante')
            approve_material(self.p, 'Oferta::A')
            ready = reconciled_rows(self.p)
            self.assertEqual((ready[0]['cantidad_remito_original'],
                              ready[0]['cantidad_remito'], ready[0]['diferencia']),
                             (80, 100, 0))
            self.assertEqual(metrics(ready)['verificados_fisicos'], 1)
            self.assertIn('cantidad_remito_original', to_csv(ready).decode())
            self.assertEqual(legacy.call_count, 2)
            for call in legacy.call_args_list:
                self.assertEqual(len(call.args), 4)

        self.assertTrue(undo_material(self.p, 'Oferta::A'))
        self.assertEqual(reconciled_rows(self.p)[0]['estado'], 'Faltante')

    def test_same_results_as_new_core(self):
        approve_material(self.p, 'Oferta::A')
        actual = reconciled_rows(self.p)[0]
        reference = current_reconcile(self.p['catalog'], self.p['remito_entries'],
                                      False, True, self.p['physical_checks'])[0]
        for field in ('cantidad_remito', 'cantidad_remito_original', 'diferencia',
                      'estado', 'estado_original', 'verificacion_fisica'):
            self.assertEqual(actual[field], reference[field], field)

    def test_complete_q3_baseline_does_not_crash(self):
        baseline = json.loads((Path(__file__).resolve().parents[1] / 'data' /
                               'q3_2026_preliminar.json').read_text(encoding='utf-8'))
        q3 = empty_period()
        q3.update(baseline)
        rows = reconciled_rows(q3)
        self.assertEqual(len(rows), 100)
        self.assertEqual(metrics(rows)['asignado'], 95590)


if __name__ == '__main__':
    unittest.main()
