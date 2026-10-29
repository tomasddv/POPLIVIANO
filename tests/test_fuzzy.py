"""Regresiones: OCR puede alterar letras/dígitos de nombres, no cantidades."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pop_core import parse_ocr_text, suggest_matches, reconcile
from fuzzy_match import rank_matches


class FuzzyPOPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed=json.loads((ROOT/'data'/'q3_2026_preliminar.json').read_text(encoding='utf-8'))

    def match(self,desc,qty=350):
        return suggest_matches([{'detalle':desc,'cantidad':qty}],
                               self.seed['catalog'],self.seed['aliases'])[0]

    def test_ocr_typo_letters(self):
        self.assertEqual(self.match('AFÍCME 20X30 OFERTA')['id'],'Oferta::G')

    def test_ocr_typo_digits_in_format(self):
        self.assertEqual(self.match('AFICHE 2OX3O OFERTA')['id'],'Oferta::G')

    def test_same_name_other_brands_not_confused(self):
        self.assertEqual(self.match('AFICHE A3 QUILMES MUNDIAL')['id'],'Quilmes::G')
        self.assertEqual(self.match('AFICHE A3 STELLA PURE GOLD')['id'],'Stella::S')

    def test_regional_latones_not_pepsi(self):
        ranked=rank_matches('AFICHE OFERTA LATON 50x70 NEALITORA!',
                            self.seed['catalog'],self.seed['aliases'])
        self.assertEqual(ranked[0]['id'],'Genérico Latones+Litro::K')
        self.assertFalse(ranked[0]['flags'])

    def test_different_regional_product(self):
        ranked=rank_matches('AFICHE OFERTA LITRO 35X50 CUYO',
                            self.seed['catalog'],self.seed['aliases'])
        self.assertEqual(ranked[0]['id'],'Genérico Latones+Litro::AX')

    def test_ambiguous_campaign_needs_review(self):
        result=self.match('AFICHE A3 BRAHMA SED',1310)
        self.assertEqual(result['id'],'')
        self.assertTrue(result['sugerido'])
        self.assertIn('revisar',result['estado_match'].lower())

    def test_same_size_different_type_no_auto(self):
        result=self.match('AFICHE 7X35 CORONA INVIERNO')
        self.assertEqual(result['id'],'')
        self.assertTrue(result['sugerido'])

    def test_amount_is_never_corrected(self):
        result=self.match('AFICHE 20X30 OFERTA',358)
        self.assertEqual(result['cantidad'],358)
        self.assertEqual(result['cantidad_excel_sugerida'],350)
        self.assertEqual(reconcile(self.seed['catalog'],{'Oferta::G':358})[0]['diferencia'],8)

    def test_uncertain_ocr_digit_is_suggested_but_not_applied(self):
        rows=parse_ocr_text('S20 AFICME A3 BUD', 'p.jpg')
        self.assertEqual(rows[0]['cantidad_sugerida'],520)
        self.assertIsNone(rows[0]['cantidad'])
        result=suggest_matches(rows,self.seed['catalog'],self.seed['aliases'])[0]
        self.assertTrue(result['sugerido'])

    def test_clean_ocr_quantity(self):
        rows=parse_ocr_text('2.840 CENEFA 20X7 OFERTA', 'p.jpg')
        self.assertEqual(rows[0]['cantidad'],2840)
        self.assertEqual(self.match(rows[0]['detalle'])['id'],'Oferta::J')

    def test_extra_material_not_matched_by_quantity(self):
        result=self.match('ESTANTERIA INEXISTENTE PROMOCIONAL',350)
        self.assertFalse(result['id'])


if __name__=='__main__':unittest.main()
