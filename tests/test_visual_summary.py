import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from visual_summary import filter_visual_rows, render_visual_matrix
from physical_checks import reconciled_rows, approve_material
from period_store import empty_period


class VisualSummaryTests(unittest.TestCase):
    def setUp(self):
        self.p=empty_period()
        self.p['catalog']=[
            {'id':'Oferta::A','cantidad_excel':350,'hoja':'Oferta','oculta':False,
             'formato':'AFICHE 20X30','material':'AFICHE 20X30','celda':'G11'},
            {'id':'Brahma::B','cantidad_excel':100,'hoja':'Brahma','oculta':False,
             'formato':'CENEFA 20X7','material':'CENEFA 20X7','celda':'J12'},
            {'id':'Brahma::C','cantidad_excel':0,'hoja':'Brahma','oculta':False,
             'formato':'SIN ASIGNACION','material':'SIN ASIGNACION','celda':'K12'},
        ]
        self.p['remito_entries']={'Oferta::A':340,'Brahma::B':110}
        self.rows=reconciled_rows(self.p)
        self.aliases={'Oferta::A':'Oferta afiche', 'Brahma::B':'Brahma cenefa'}

    def test_filters_sheet_search_and_status(self):
        self.assertEqual(len(filter_visual_rows(self.rows,self.aliases)),2)
        self.assertEqual(len(filter_visual_rows(self.rows,self.aliases,include_zero=True)),2)
        self.assertEqual([r['id'] for r in filter_visual_rows(self.rows,self.aliases,sheet='Oferta')],['Oferta::A'])
        self.assertEqual(len(filter_visual_rows(self.rows,self.aliases,status='Pendientes y diferencias')),2)
        self.assertEqual([r['id'] for r in filter_visual_rows(self.rows,self.aliases,query='cenefa')],['Brahma::B'])
        self.assertEqual([r['id'] for r in filter_visual_rows(self.rows,self.aliases,query='Oferta afiche')],['Oferta::A'])

    def test_photo_and_assignments_are_in_same_column(self):
        html=render_visual_matrix(self.rows[:2],self.aliases,{'Oferta::A':'a.jpg'},{'a.jpg':b'\xff\xd8test'})
        self.assertIn('data:image/jpeg;base64,',html)
        self.assertIn('Asignado DDV',html)
        self.assertIn('Remito original',html)
        self.assertIn('Remito conciliado',html)
        self.assertIn('350',html)
        self.assertIn('340',html)
        self.assertIn('-10',html)
        self.assertIn('+10',html)
        self.assertIn('Sin imagen de POP',html)
        self.assertIn('color:#000!important',html)

    def test_physical_confirmation_changes_only_conciliated_value(self):
        approve_material(self.p,'Oferta::A')
        rows=reconciled_rows(self.p)
        html=render_visual_matrix(rows[:1],self.aliases,{}, {})
        self.assertIn('✓ Verificado físicamente',html)
        self.assertIn('340',html)
        self.assertIn('350',html)
        self.assertEqual(rows[0]['cantidad_remito_original'],340)
        self.assertEqual(rows[0]['cantidad_remito'],350)
        self.assertEqual(rows[0]['diferencia'],0)
        self.assertEqual(len(filter_visual_rows(rows,self.aliases,status='Verificados físicamente')),1)

    def test_escapes_strings_in_html(self):
        self.aliases['Oferta::A']='<script>alert(1)</script>'
        html=render_visual_matrix(self.rows[:1],self.aliases,{}, {})
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)

    def test_q3_real_gallery_links_and_original_sheet_order(self):
        baseline=json.loads((ROOT/'data/q3_2026_preliminar.json').read_text(encoding='utf-8'))
        p=empty_period();p.update(baseline)
        rows=reconciled_rows(p)
        selected=filter_visual_rows(rows,p.get('aliases',{}))
        self.assertEqual(len(rows),73)
        self.assertTrue(len(selected)>0)
        self.assertEqual(selected[0]['hoja'],baseline['catalog'][0]['hoja'])
        images=json.loads((ROOT/'data/q3_pop_map.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(sum(x['id'] in images for x in selected),70)
        self.assertEqual(len(filter_visual_rows(rows,p.get('aliases',{}),include_zero=True)),73)

if __name__=='__main__':unittest.main()
