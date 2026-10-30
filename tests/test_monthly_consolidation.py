import unittest
from hashlib import sha256
from period_store import empty_period,archive_bytes,restore_archive, merge_quantities
from monthly_core import (MONTH_RE,scope_label,scope_sort,merge_catalog,ingest_excels,
                          check_new_remitos,digest_files)
from physical_checks import approve_material


def item(qty,name='AFICHE 35x50 Andes',id_='Andes::H'):
    return {'id':id_,'hoja':'Andes','grupo':'Andes','formato':name,
            'material':'Andes · '+name,'cantidad_excel':qty,'oculta':False,
            'celda':'H15','fila':15}


def parser(data):
    if data==b'bad': raise ValueError('Archivo dañado')
    if data==b'other':
        return [item(3,'AFICHE 20x30 Stella','Andes::H')],[],[{'hoja':'Andes','oculta':False,'fila_ddv':15,'materiales':1,'total':3}]
    qty=int(data)
    return [item(qty)],[],[{'hoja':'Andes','oculta':False,'fila_ddv':15,'materiales':1,'total':qty}]

class MonthlyTests(unittest.TestCase):
    def test_scope_year_month_and_historic(self):
        self.assertTrue(MONTH_RE.fullmatch('2026-10'))
        self.assertEqual(scope_label('2026-10'),'Octubre 2026 · mensual')
        self.assertEqual(scope_sort('Q3 2026'), (2026,7,0))
        self.assertFalse(MONTH_RE.fullmatch('2026-13'))

    def test_two_excel_sum_once_ddv_and_history(self):
        state,images,report=ingest_excels(empty_period(),[('a.xlsx',b'30'),('b.xlsx',b'40')],parser)
        self.assertEqual(state['catalog'][0]['cantidad_excel'],70)
        self.assertEqual(len(state['catalog']),1)
        self.assertEqual(len(state['excel_history']),2)
        self.assertEqual(len(images),2)
        self.assertEqual(sum(x['Unidades DDV sumadas'] for x in report),70)
        self.assertEqual(state['sheets'][0]['total'],70)

    def test_same_excel_in_a_second_batch_rejected(self):
        state,_,_=ingest_excels(empty_period(),[('a.xlsx',b'30')],parser)
        with self.assertRaisesRegex(ValueError,'ya incorporado'):
            ingest_excels(state,[('renamed.xlsx',b'30')],parser)
        self.assertEqual(state['catalog'][0]['cantidad_excel'],30)

    def test_same_excel_within_batch_rejected_atomically(self):
        with self.assertRaisesRegex(ValueError,'ya incorporado'):
            ingest_excels(empty_period(),[('a.xlsx',b'30'),('a-copy.xlsx',b'30')],parser)

    def test_invalid_second_excel_cannot_modify_first(self):
        state,_,_=ingest_excels(empty_period(),[('a.xlsx',b'30')],parser)
        with self.assertRaisesRegex(ValueError,'dañado'):
            ingest_excels(state,[('b.xlsx',b'40'),('bad.xlsx',b'bad')],parser)
        self.assertEqual(state['catalog'][0]['cantidad_excel'],30)

    def test_different_product_same_cell_does_not_mix(self):
        state,_,_=ingest_excels(empty_period(),[('a.xlsx',b'30'),('b.xlsx',b'other')],parser)
        self.assertEqual(len(state['catalog']),2)
        self.assertEqual(sorted(x['cantidad_excel'] for x in state['catalog']),[3,30])
        self.assertNotEqual(state['catalog'][0]['id'],state['catalog'][1]['id'])

    def test_keep_remito_quantities_when_adding_excel_and_invalidate_physical(self):
        state,_,_=ingest_excels(empty_period(),[('a.xlsx',b'30')],parser)
        state['remito_entries']={'Andes::H':25}
        approve_material(state,'Andes::H')
        revised,_,_=ingest_excels(state,[('b.xlsx',b'40')],parser)
        self.assertEqual(revised['remito_entries']['Andes::H'],25)
        self.assertNotIn('Andes::H',revised['physical_checks'])
        self.assertIn('Andes::H',state['physical_checks'])

    def test_remito_duplicate_detects_same_bytes_different_names(self):
        state=empty_period()
        state['processed_remito_files']=[sha256(b'image1').hexdigest()]
        with self.assertRaisesRegex(ValueError,'ya se habían incorporado'):
            check_new_remitos(state,[('otro-nombre.png',b'image1')])
        self.assertEqual(check_new_remitos(state,[('nuevo.pdf',b'image2')]),[sha256(b'image2').hexdigest()])

    def test_month_archive_restores_all(self):
        month,_,_=ingest_excels(empty_period(),[('a.xlsx',b'30'),('b.xlsx',b'40')],parser)
        month['remito_entries']={'Andes::H':64}
        archive=archive_bytes({'Q3 2026':empty_period(),'2026-10':month})
        restored=restore_archive(archive)
        self.assertEqual(restored['2026-10']['catalog'][0]['cantidad_excel'],70)
        self.assertEqual(restored['2026-10']['remito_entries']['Andes::H'],64)
        self.assertEqual(len(restored['2026-10']['excel_history']),2)

    def test_add_remito_batches_cumulative(self):
        self.assertEqual(merge_quantities({'Andes::H':21},{'Andes::H':30,'X':5},'Agregar un remito nuevo al período'),
                         {'Andes::H':51,'X':5})

if __name__=='__main__': unittest.main()

class RealCatalogIdentityTests(unittest.TestCase):
    def test_equal_descriptions_in_same_excel_keep_separate_columns(self):
        from monthly_core import merge_catalog
        a=item(100,'AFICHE OFERTA 35x50','Oferta::H')
        b=item(200,'AFICHE OFERTA 35x50','Oferta::K')
        state,mapping,_,_,_=merge_catalog([], [a,b], 'aabbcc')
        self.assertEqual(len(state),2)
        self.assertEqual(sum(x['cantidad_excel'] for x in state),300)
        self.assertEqual(mapping['Oferta::H'],'Oferta::H')
        self.assertEqual(mapping['Oferta::K'],'Oferta::K')

    def test_original_historical_excel_can_not_be_added_again(self):
        period=empty_period()
        period['catalog']=[item(30)]
        period['source_digest']=sha256(b'30').hexdigest()
        period['source_name']='Original.xlsx'
        with self.assertRaisesRegex(ValueError,'ya incorporado'):
            ingest_excels(period,[('Duplicado.xlsx',b'30')],parser)
