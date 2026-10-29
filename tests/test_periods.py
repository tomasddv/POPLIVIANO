import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from period_store import (empty_period, archive_bytes, restore_archive,
                          merge_quantities, PERIOD_RE, new_source)
from pop_core import reconcile, metrics, catalog_from_excel

class PeriodWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed=json.loads((ROOT/'data'/'q3_2026_preliminar.json').read_text(encoding='utf-8'))

    def test_q3_preloaded_real_ddv(self):
        cat=self.seed['catalog'];self.assertEqual(len(cat),100)
        row=metrics(reconcile(cat,self.seed['remito_entries'],False,True))
        self.assertEqual((row['asignado'],row['recibido']), (95590,93750))
        self.assertEqual((row['coinciden'],row['diferencias'],row['pendientes']),(70,1,3))
        self.assertFalse(self.seed['is_complete'])
        self.assertTrue(self.seed['preliminary'])

    def test_q3_q4_are_separate(self):
        q3=empty_period();q3.update(self.seed)
        q4=empty_period()
        controls={'Q3 2026':q3, 'Q4 2026':q4}
        controls['Q4 2026']['remito_entries']['Q4::A']=400
        controls['Q3 2026']['remito_entries']['Oferta::G']=350
        self.assertEqual(controls['Q3 2026']['remito_entries']['Oferta::G'],350)
        self.assertNotIn('Q4::A',controls['Q3 2026']['remito_entries'])

    def test_append_ocr_is_idempotent_when_reapplied(self):
        base={'Material::A':100}
        rows={'Material::A':20,'Material::B':30}
        first=merge_quantities(base,rows,'Agregar páginas al remito actual')
        second=merge_quantities(base,rows,'Agregar páginas al remito actual')
        self.assertEqual(first,second)
        self.assertEqual(first,{'Material::A':120,'Material::B':30})
        self.assertEqual(merge_quantities(base,rows,'Reemplazar cantidades anteriores'),rows)

    def test_round_trip_archive_includes_source_for_future_view(self):
        q3=empty_period();q3.update(self.seed)
        q4=empty_period();q4.update(source_name='Q4.xlsx',source_digest='fake',
            catalog=[{'id':'Q4::J','hoja':'Q4','cantidad_excel':42,'oculta':False}],
            remito_entries={'Q4::J':45})
        restored=restore_archive(archive_bytes({'Q3 2026':q3,'Q4 2026':q4}))
        self.assertEqual(restored['Q4 2026']['catalog'][0]['cantidad_excel'],42)
        self.assertEqual(restored['Q4 2026']['remito_entries']['Q4::J'],45)
        self.assertEqual(restored['Q3 2026']['remito_entries']['Oferta::G'],350)

    def test_reject_invalid_archive(self):
        with self.assertRaises(ValueError):restore_archive(b'{"format":"unknown","version":2,"periods":{}}')
        with self.assertRaises(ValueError):restore_archive(b'{"format":"pop-ddv-periodos","version":2,"periods":{"Q3 2026":{"catalog":[],"remito_entries":{"not valid":5}}}}')

    def test_new_excel_resets_only_target_period(self):
        def parser(_):
            return [{'id':'Q4::G','cantidad_excel':20}],[],[{'hoja':'Q4'}]
        q4=new_source(empty_period(),b'dummy','Q4.xlsx',parser)
        self.assertEqual(q4['catalog'][0]['cantidad_excel'],20)
        self.assertFalse(q4['is_complete'])
        self.assertEqual(q4['remito_entries'],{})

if __name__=='__main__': unittest.main()
