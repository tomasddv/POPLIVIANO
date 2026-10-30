import unittest
from convertidor_remitos import make_draft
from remito_excel import parse_file,parse_batch
from period_store import empty_period,archive_bytes,restore_archive


def sample(number='15743', day='2026-06-17', label='AFICHE 20x30 QUILMES'):
    return make_draft([{'pagina':'p1','linea':1,'detalle':label,'cantidad':40,'origen_cantidad':'EXPRESA'}], number, day)


class ReviewedReceiptExcelTests(unittest.TestCase):
    def test_ingests_verified_rows(self):
        result=parse_file('uno.xlsx',sample())
        self.assertEqual(result['remitos'],['00015743'])
        self.assertEqual(result['meses'],['2026-06'])
        self.assertEqual(result['filas'][0]['cantidad'],40)
    def test_no_cross_month_adds(self):
        f=('uno.xlsx',sample())
        with self.assertRaisesRegex(ValueError,'2026-06'):
            parse_batch([f],'2026-07')
        _,rows=parse_batch([f],'2026-06')
        self.assertEqual(len(rows),1)
    def test_duplicate_document_across_different_excel(self):
        with self.assertRaisesRegex(ValueError,'aparece en varios Excel'):
            parse_batch([('uno.xlsx',sample()),('dos.xlsx',sample(label='AFICHE A3 QUILMES'))],'Q3 2026')
        with self.assertRaisesRegex(ValueError,'ya incorporado'):
            parse_batch([('uno.xlsx',sample())],'Q3 2026',[{'remitos':['00015743'],'digest':'other'}])
    def test_two_documents_historic_but_not_month(self):
        docs=[('junio.xlsx',sample()),('julio.xlsx',sample('16228','2026-07-17'))]
        _,rows=parse_batch(docs,'Q3 2026')
        self.assertEqual(len(rows),2)
        with self.assertRaisesRegex(ValueError,'2026-06'):
            parse_batch(docs,'2026-07')
    def test_blank_quantity_excluded_by_converter(self):
        draft=make_draft([{'pagina':'p1','detalle':'AFICHE 20x30 QUILMES','cantidad':40},
                          {'pagina':'p1','detalle':'AFICHE 20x30 PEPSI','cantidad':None}], '15743','2026-06-17')
        self.assertEqual(len(parse_file('borrador.xlsx',draft)['filas']),1)
    def test_archive_preserves_new_import_history(self):
        p=empty_period()
        p['remito_excel_history']=[{'archivo':'abc.xlsx','remitos':['00015743'],'digest':'x'}]
        p['ocr_excel_meta']=[{'remitos':['00016228']}]
        out=restore_archive(archive_bytes({'2026-06':p}))['2026-06']
        self.assertEqual(out['remito_excel_history'][0]['remitos'],['00015743'])
        self.assertEqual(out['ocr_excel_meta'][0]['remitos'],['00016228'])
