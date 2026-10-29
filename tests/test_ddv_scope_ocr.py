import unittest,json
from pathlib import Path
from pop_core import active_catalog,parse_ocr_text,suggest_matches,classify_out_of_scope
from fuzzy_match import rank_matches
from physical_checks import reconciled_rows
from period_store import empty_period
BASE=json.loads((Path(__file__).resolve().parents[1]/'data/q3_2026_preliminar.json').read_text(encoding='utf-8'))

class DDVScopeOCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all=BASE['catalog'];cls.active=active_catalog(cls.all);cls.alias=BASE['aliases']
    def test_scope_positive_ddv_only(self):
        self.assertEqual(len(self.all),100)
        self.assertEqual(len(self.active),73)
        self.assertEqual(sum(x['cantidad_excel'] for x in self.active),95590)
        self.assertNotIn('Quilmes::M',[x['id'] for x in self.active])
        p=empty_period();p.update(BASE)
        self.assertEqual(len(reconciled_rows(p)),73)
    def test_ao_andes_match_with_review_on_duplicate(self):
        ranks=rank_matches('AFICHE 35X50 ANDES',self.active,self.alias)
        self.assertEqual({ranks[0]['id'],ranks[1]['id']},{'AO::J','AO::P'})
        result=suggest_matches([{'detalle':'AFICHE 35X50 AO','cantidad':70}],self.active,self.alias)[0]
        self.assertEqual(result['id'],'')
        self.assertIn(result['sugerido'],('AO::J','AO::P'))
    def test_regional_remito_varias_matches_ddv(self):
        for fmt,material in [('35X50','Genérico Latones+Litro::AF'),('50X70','Genérico Latones+Litro::AI')]:
            result=suggest_matches([{'detalle':f'AFICHE OFERTA LATON {fmt} REG VARIAS','cantidad':1490}],self.active,self.alias)[0]
            self.assertEqual(result['id'],material)
    def test_forward_fills_only_within_same_page_and_column(self):
        txt='1490 AFICHE OFERTA LATON 35X50 REG VARIAS\nAFICHE OFERTA LATON 50X70 REG VARIAS\n30 AFICHE OFERTA LITRO 35X50 REG VARIAS\nAFICHE OFERTA LITRO 50X70 REG VARIAS\n40 AFICHE 35X50 QUILMES MUNDIAL\nAFICHE 20X30 QUILMES MUNDIAL'
        a=parse_ocr_text(txt,'izquierda')
        self.assertEqual([x['cantidad'] for x in a],[1490,1490,30,30,40,40])
        self.assertEqual([x['cantidad_heredada'] for x in a],[False,True,False,True,False,True])
        self.assertIsNone(parse_ocr_text('AFICHE 20X30 QUILMES MUNDIAL','derecha')[0]['cantidad'])
    def test_20x30_quilmes_received_out_of_ddv(self):
        rows=parse_ocr_text('40 AFICHE 35X50 QUILMES MUNDIAL\nAFICHE 20X30 QUILMES MUNDIAL','izquierda')
        scoped=classify_out_of_scope(suggest_matches(rows,self.active,self.alias),self.all,self.alias)
        self.assertFalse(scoped[0]['fuera_ddv']);self.assertEqual(scoped[0]['id'],'Quilmes::J')
        self.assertTrue(scoped[1]['fuera_ddv']);self.assertEqual(scoped[1]['cantidad'],40)
        self.assertIn('DDV=0',scoped[1]['razon_fuera_ddv'])
    def test_uncertain_match_not_auto_excluded(self):
        x=suggest_matches([{'detalle':'CARTEL NUNCA VISTO 35X50','cantidad':10}],self.active,self.alias)
        self.assertFalse(classify_out_of_scope(x,self.all,self.alias)[0]['fuera_ddv'])
