"""Cobertura del formato Q4/V12 (encabezados fila 2, DDV en D142)."""
import io
import unittest
import zipfile
from pop_core import catalog_from_excel, active_catalog
from monthly_core import ingest_excels
from period_store import empty_period


def make_q4():
    main='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    office='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    def inline(ref,value):
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
    def numeric(ref,num):
        return f'<c r="{ref}"><v>{num}</v></c>'
    sheet = f'''<?xml version="1.0" encoding="UTF-8"?>
       <worksheet xmlns="{main}"><sheetData>
         <row r="1">{inline('A1','BLOQUE 1 - ASIGNACIÓN A PROVEEDOR')}</row>
         <row r="2">{inline('E2','Andes Origen A3 RESTO PAIS')}{inline('F2','Andes Origen 35x50 RESTO PAIS')}{inline('G2','Cenefita 7x3,5 K+T')}</row>
         <row r="6">{inline('A6','TOTAL NACIONAL')}{numeric('E6',9000)}{numeric('F6',3000)}{numeric('G6',4000)}</row>
         <row r="142">{inline('A142','PATAGONIA')}{inline('B142','CHUBUT')}{inline('D142','DISTRIBUIDORA DEL VALLE S.A.')}{numeric('E142',708)}{numeric('F142',50)}{numeric('G142',0)}</row>
       </sheetData></worksheet>'''
    admin = f'''<?xml version="1.0" encoding="UTF-8"?>
       <worksheet xmlns="{main}"><sheetData><row r="142">{inline('D142','DISTRIBUIDORA DEL VALLE S.A.')}{numeric('E142',88888)}</row></sheetData></worksheet>'''
    wb=f'''<workbook xmlns="{main}" xmlns:r="{office}"><sheets><sheet name="PEGAR ASIGNACION" state="hidden" sheetId="1" r:id="rId1"/><sheet name="ANDES ORIGEN" sheetId="2" r:id="rId2"/></sheets></workbook>'''
    rels='''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/><Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>'''
    content=io.BytesIO()
    with zipfile.ZipFile(content,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('xl/workbook.xml',wb)
        z.writestr('xl/_rels/workbook.xml.rels',rels)
        z.writestr('xl/worksheets/sheet1.xml',admin)
        z.writestr('xl/worksheets/sheet2.xml',sheet)
    return content.getvalue()

class Q4LayoutTest(unittest.TestCase):
    def test_ddv_quantities_and_headers_from_row_two(self):
        catalog, issues, meta = catalog_from_excel(make_q4())
        self.assertEqual(len(catalog),3)
        self.assertEqual(len(active_catalog(catalog)),2)
        self.assertEqual(sum(x['cantidad_excel'] for x in active_catalog(catalog)),758)
        self.assertEqual([x['celda'] for x in catalog],['E142','F142','G142'])
        self.assertTrue(all(x['cabecera']==2 for x in catalog))
        self.assertTrue(all(x['hoja']=='ANDES ORIGEN' for x in catalog))
        self.assertTrue(all('ANDES ORIGEN' in x['material'] for x in catalog))
        self.assertEqual(issues,[])
        self.assertEqual(len(meta),1)

    def test_monthly_ingestion_q4(self):
        p, mappings, reports = ingest_excels(empty_period(), [('Q4.xlsx',make_q4())],catalog_from_excel)
        self.assertEqual(reports[0]['Unidades DDV sumadas'],758)
        self.assertEqual(len(mappings),1)
        self.assertEqual(p['sheets'][0]['total'],758)

if __name__ == '__main__': unittest.main()
