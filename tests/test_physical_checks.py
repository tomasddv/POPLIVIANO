import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from physical_checks import approve_material, undo_material, invalidate_changed_checks, clear_checks, reconciled_rows
from period_store import empty_period, archive_bytes, restore_archive
from pop_core import metrics, to_csv

class PhysicalVerificationTests(unittest.TestCase):
    def setUp(self):
        self.p=empty_period()
        self.p['catalog']=[{'id':'Oferta::A','cantidad_excel':100,'hoja':'Oferta',
                            'oculta':False,'formato':'AFICHE 20X30','material':'AFICHE 20X30','celda':'G11'},
                           {'id':'Cenefa::B','cantidad_excel':20,'hoja':'Cenefa',
                            'oculta':False,'formato':'CENEFA 20X7','material':'CENEFA 20X7','celda':'J12'},
                           {'id':'Brahma::C','cantidad_excel':30,'hoja':'Brahma',
                            'oculta':False,'formato':'BRAHMA A3','material':'BRAHMA A3','celda':'K11'}]
        self.p['remito_entries']={'Oferta::A':80,'Cenefa::B':24}

    def test_physically_approved_faltante_conciliates_exactly_without_mutating_original(self):
        event=approve_material(self.p,'Oferta::A')
        self.assertEqual(event['cantidad_original_remito'],80)
        self.assertEqual(self.p['remito_entries']['Oferta::A'],80)
        got=reconciled_rows(self.p)
        x=got[0]
        self.assertEqual((x['cantidad_remito_original'],x['cantidad_remito'],x['diferencia']),(80,100,0))
        self.assertEqual((x['estado'],x['estado_original']),('Coincide','Faltante'))
        self.assertTrue(x['verificacion_fisica'])
        self.assertEqual(metrics(got)['verificados_fisicos'],1)
        self.assertEqual(metrics(got)['remito_original'],104)
        self.assertEqual(metrics(got)['recibido'],124)

    def test_sobrante_approved_then_undone(self):
        approve_material(self.p,'Cenefa::B')
        self.assertEqual(reconciled_rows(self.p)[1]['cantidad_remito'],20)
        self.assertEqual(reconciled_rows(self.p)[1]['estado_original'],'Sobrante')
        self.assertTrue(undo_material(self.p,'Cenefa::B'))
        self.assertFalse(undo_material(self.p,'Cenefa::B'))
        self.assertEqual(reconciled_rows(self.p)[1]['cantidad_remito'],24)
        self.assertEqual(reconciled_rows(self.p)[1]['estado'],'Sobrante')
        self.assertEqual(len(self.p['physical_events']),2)

    def test_pending_approved_undo_restores_unknown(self):
        self.assertIsNone(reconciled_rows(self.p)[2]['cantidad_remito'])
        approve_material(self.p,'Brahma::C')
        self.assertEqual(reconciled_rows(self.p)[2]['cantidad_remito'],30)
        self.assertIsNone(reconciled_rows(self.p)[2]['cantidad_remito_original'])
        self.assertEqual(reconciled_rows(self.p)[2]['estado_original'],'Pendiente')
        undo_material(self.p,'Brahma::C')
        self.assertEqual(reconciled_rows(self.p)[2]['estado'],'Pendiente')

    def test_approval_persists_in_json_and_is_period_specific(self):
        approve_material(self.p,'Oferta::A')
        q4=empty_period()
        restored=restore_archive(archive_bytes({'Q3 2026':self.p,'Q4 2026':q4}))
        self.assertIn('Oferta::A',restored['Q3 2026']['physical_checks'])
        self.assertEqual(len(restored['Q3 2026']['physical_events']),1)
        self.assertEqual(restored['Q4 2026']['physical_checks'],{})
        self.assertEqual(reconciled_rows(restored['Q3 2026'])[0]['diferencia'],0)

    def test_new_or_corrected_remito_reopens_affected_only(self):
        approve_material(self.p,'Oferta::A')
        approve_material(self.p,'Cenefa::B')
        updated={'Oferta::A':90,'Cenefa::B':24}
        changed=invalidate_changed_checks(self.p,self.p['remito_entries'],updated,'Revisión OCR')
        self.assertEqual(changed,['Oferta::A'])
        self.p['remito_entries']=updated
        self.assertNotIn('Oferta::A',self.p['physical_checks'])
        self.assertIn('Cenefa::B',self.p['physical_checks'])
        self.assertEqual(reconciled_rows(self.p)[0]['diferencia'],-10)
        self.assertEqual(self.p['physical_events'][-1]['motivo'],'Revisión OCR')

    def test_reset_clears_approvals_with_history(self):
        approve_material(self.p,'Oferta::A')
        clear_checks(self.p,'Reinicio')
        self.assertEqual(self.p['physical_checks'],{})
        self.assertEqual(len(self.p['physical_events']),2)

    def test_export_includes_raw_and_reconciled_and_verified(self):
        approve_material(self.p,'Oferta::A')
        report=to_csv(reconciled_rows(self.p)).decode('utf-8-sig')
        self.assertIn('cantidad_remito_original',report)
        self.assertIn('verificacion_fisica',report)
        self.assertIn('fecha_verificacion',report)
        self.assertIn('80;100;0;Coincide;Faltante;True',report)

    def test_unknown_id_rejected(self):
        with self.assertRaises(ValueError):approve_material(self.p,'Cualquiera::X')

if __name__=='__main__':unittest.main()
