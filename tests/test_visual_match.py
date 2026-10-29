import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from visual_match import visual_candidates, preferred_ocr_ids, choose_material

CATALOG=[
    {'id':'Oferta::G','hoja':'Oferta','formato':'AFICHE 20X30 OFERTA','material':'Oferta · AFICHE 20X30 OFERTA','grupo':'Oferta','cantidad_excel':350},
    {'id':'Brahma::K','hoja':'Brahma','formato':'CENEFA 20X7 BRAHMA','material':'Brahma · CENEFA 20X7 BRAHMA','grupo':'Brahma','cantidad_excel':200},
    {'id':'Oferta::H','hoja':'Oferta','formato':'CENEFA 20X7 OFERTA','material':'Oferta · CENEFA 20X7 OFERTA','grupo':'Oferta','cantidad_excel':2840},
]
NAMES={x['id']:x['id']+' | '+x['material'] for x in CATALOG}
class VisualMatchTests(unittest.TestCase):
    def test_prefers_suggested_excel_match(self):
        selected=visual_candidates(CATALOG,{},preferred=['Brahma::K'])
        self.assertEqual(selected[0]['id'],'Brahma::K')
    def test_filters_by_text_and_excel_sheet(self):
        found=visual_candidates(CATALOG,{},query='cenefa 20x7',sheet='Oferta')
        self.assertEqual([x['id'] for x in found],['Oferta::H'])
    def test_alias_search(self):
        found=visual_candidates(CATALOG,{'Oferta::G':'Campaña ANIVERSARIO'},query='aniversario')
        self.assertEqual([x['id'] for x in found],['Oferta::G'])
    def test_images_filter_only_existing(self):
        found=visual_candidates(CATALOG,{},only_with_image=True,
            image_map={'Oferta::G':'pop/a.jpg','Oferta::H':'pop/missing.jpg'},
            assets={'pop/a.jpg':b'valid'})
        self.assertEqual([x['id'] for x in found],['Oferta::G'])
    def test_deduplicates_suggestions(self):
        o={'id':'Oferta::G','sugerido':'Oferta::H','alternativas':[
            {'id':'Oferta::G','score':91},{'id':'Brahma::K','score':65}]}
        self.assertEqual(preferred_ocr_ids(o),['Oferta::H','Oferta::G','Brahma::K'])
    def test_selection_preserves_original_ocr_text_and_quantity(self):
        lines=[{'Descripción OCR':'k 350 AFlCHE 2OX3O OFERTA','Cantidad':350,
                'Material Excel':'(sin asignar)','Sugerencia':'Oferta::H',
                'Similitud %':90,'Excel sugerido':2840,'Diferencia tentativa':-2490}]
        revised=choose_material(lines,0,'Oferta::G',NAMES,CATALOG)
        self.assertEqual(revised[0]['Material Excel'],NAMES['Oferta::G'])
        self.assertEqual(revised[0]['Excel sugerido'],350)
        self.assertEqual(revised[0]['Diferencia tentativa'],0)
        self.assertEqual(revised[0]['Cantidad'],350)
        self.assertEqual(revised[0]['Descripción OCR'],'k 350 AFlCHE 2OX3O OFERTA')
        self.assertEqual(revised[0]['Sugerencia'],'Oferta::H')
        self.assertIsNone(revised[0]['Similitud %'])
        self.assertEqual(lines[0]['Material Excel'],'(sin asignar)')
    def test_no_invented_quantity(self):
        revised=choose_material([{'Cantidad':None}],0,'Oferta::G',NAMES,CATALOG)
        self.assertIsNone(revised[0]['Diferencia tentativa'])
        self.assertIsNone(revised[0]['Cantidad'])
    def test_error_for_bad_row_or_material(self):
        with self.assertRaises(IndexError):choose_material([],0,'Oferta::G',NAMES,CATALOG)
        with self.assertRaises(ValueError):choose_material([{}],0,'Other::X',NAMES,CATALOG)
if __name__=='__main__':unittest.main()
