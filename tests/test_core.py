import unittest
from pop_core import parse_ocr_text, suggest_matches, reconcile, metrics, qty_from_ocr

class AppTests(unittest.TestCase):
    def setUp(self):
        self.catalog=[{'id':'Bud::G','hoja':'Bud','material':'Bud · BUD · AFICHE A3','cantidad_excel':200,'oculta':False},
                      {'id':'Bud::J','hoja':'Bud','material':'Bud · BUD · CENEFA 20x7','cantidad_excel':150,'oculta':False}]
    def test_qty(self):
        self.assertEqual(qty_from_ocr('2.840'),2840)
        self.assertEqual(qty_from_ocr('280'),280)
        self.assertIsNone(qty_from_ocr('B80'))
    def test_pending_not_zero(self):
        rows=reconcile(self.catalog,{'Bud::G':200},completed=False)
        self.assertEqual([x['estado'] for x in rows],['Coincide','Pendiente'])
        self.assertEqual(metrics(rows)['recibido'],200)
    def test_completed_missing_faltante(self):
        rows=reconcile(self.catalog,{'Bud::G':200},completed=True)
        self.assertEqual([x['estado'] for x in rows],['Coincide','Faltante'])
    def test_surplus(self):
        rows=reconcile(self.catalog,{'Bud::G':215,'Bud::J':150},completed=True)
        self.assertEqual(rows[0]['estado'],'Sobrante')
        self.assertEqual(rows[0]['diferencia'],15)
    def test_ocr_missing_qty_inherits(self):
        rows=parse_ocr_text('280 AFICHE 20x30 COMBO\nAFICHE A3 STELLA\nFECHA:', 'remito.jpg')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1]['cantidad'],280)
        self.assertTrue(rows[1]['cantidad_heredada'])
    def test_never_match_only_by_quantity(self):
        rows=suggest_matches([{'detalle':'Sticker Corona','cantidad':200}],self.catalog)
        self.assertEqual(rows[0]['id'],'')
if __name__=='__main__':unittest.main()

class ExcelLayoutTests(unittest.TestCase):
    def test_extracts_only_ddv_with_variable_row_and_hidden_sheet(self):
        import io,zipfile
        from pop_core import catalog_from_excel
        xml_ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        def c(ref,value):
            return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>' if isinstance(value,str) else f'<c r="{ref}"><v>{value}</v></c>'
        def row(n,cols):return '<row r="%s">%s</row>'%(n,''.join(c(f'{col}{n}',val) for col,val in cols.items()))
        sheet=f'<worksheet xmlns="{xml_ns}"><sheetData>'+''.join([
            row(1,{'G':'CANTIDAD','J':'CANTIDAD'}),
            row(4,{'G':'NUEVA OFERTA','J':'NUEVA OFERTA'}),
            row(5,{'G':'AFICHE 20x30','J':'CENEFA 20x7'}),
            row(15,{'D':'DISTRIBUIDORA EXTERNA SA','G':9999,'J':8888}),
            row(53,{'D':'DISTRIBUIDORA DEL VALLE S.A.','G':120,'J':30}),
        ])+'</sheetData></worksheet>'
        w=f'<workbook xmlns="{xml_ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Q4" sheetId="1" state="hidden" r:id="rId1"/></sheets></workbook>'
        r='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w') as f:
            f.writestr('xl/workbook.xml',w)
            f.writestr('xl/_rels/workbook.xml.rels',r)
            f.writestr('xl/worksheets/sheet1.xml',sheet)
        catalog,issues,meta=catalog_from_excel(memory.getvalue())
        self.assertEqual(len(catalog),2)
        self.assertEqual(sum(x['cantidad_excel'] for x in catalog),150)
        self.assertTrue(all(x['oculta'] for x in catalog))
        self.assertEqual(meta[0]['fila_ddv'],53)
