import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from persistence import LocalStore, write_zip_assets, read_zip_assets, GitHubStore
from media_core import image_jpeg, extract_pop_images
from period_store import empty_period, archive_bytes, restore_archive, merge_quantities
from PIL import Image

P=Path(__file__).resolve().parents[1]

class PhotosTests(unittest.TestCase):
    def test_q3_has_real_images_connected_to_known_ids(self):
        import json
        photo_map=json.loads((P/'data/q3_pop_map.json').read_text(encoding='utf-8'))
        assets=read_zip_assets((P/'data/q3_gallery.zip').read_bytes())
        self.assertGreaterEqual(len(photo_map),90)
        self.assertEqual(set(photo_map.values()) | {'remitos/q3_base/pagina_01.jpg'}, set(assets))
        self.assertIn('Oferta::G',photo_map)
        self.assertIn('Brahma::J',photo_map)
        self.assertIn('remitos/q3_base/pagina_01.jpg',assets)
        Image.open(io.BytesIO(assets[photo_map['Oferta::G']])).verify()

    def test_image_compression(self):
        im=Image.new('RGBA',(900,700),(255,0,0,0)); out=io.BytesIO();im.save(out,format='PNG')
        blob=image_jpeg(out.getvalue())
        photo=Image.open(io.BytesIO(blob))
        self.assertEqual(photo.format,'JPEG')
        self.assertLessEqual(photo.width,660)

    def test_zip_rejects_bad_names(self):
        raw=write_zip_assets({'pop/a.jpg':b'photo','../secret.jpg':b'no','remitos/x/a.jpg':b'yes'})
        self.assertEqual(read_zip_assets(raw),{'pop/a.jpg':b'photo','remitos/x/a.jpg':b'yes'})

    def test_state_local_roundtrip_and_history(self):
        p=empty_period()
        p['remito_history']=[{'id':'a','archivos':['foto_q4.png'],'estado':'Aplicado','imagen_keys':['remitos/1/pagina_01.jpg']}]
        p['pop_images']={'Brahma::G':'pop/a.jpg'}
        catalog={'id':'Brahma::G','hoja':'Brahma','cantidad_excel':50}
        p['catalog']=[catalog]
        periods={'Q4 2026':p}
        assets={'Q4 2026':{'pop/a.jpg':b'aaa','remitos/1/pagina_01.jpg':b'bb'}}
        with tempfile.TemporaryDirectory() as d:
            with patch('persistence.LOCAL',Path(d)):
                store=LocalStore()
                store.save(periods,assets,['Q4 2026'])
                restored=restore_archive(store.load())
                self.assertEqual(restored['Q4 2026']['remito_history'][0]['id'],'a')
                self.assertEqual(restored['Q4 2026']['pop_images']['Brahma::G'],'pop/a.jpg')
                self.assertEqual(store.load_assets('Q4 2026'),assets['Q4 2026'])

    def test_merge_a_new_remito_adds_quantities(self):
        self.assertEqual(merge_quantities({'a':10},{'a':5,'b':20},'Agregar un remito nuevo al período'),{'a':15,'b':20})

    def test_large_git_blob_is_handled(self):
        import base64
        store=GitHubStore('owner/private','test-token')
        store._call=lambda method,path,data=None: (
            {'sha':'abcd','size':2_100_000,'content':'','encoding':'none'}
            if 'contents/' in path else {'encoding':'base64','content':base64.b64encode(b'123').decode()})
        raw,sha=store._get('assets/Q3_2026.zip')
        self.assertEqual(raw,b'123');self.assertEqual(sha,'abcd')

if __name__=='__main__':unittest.main()
