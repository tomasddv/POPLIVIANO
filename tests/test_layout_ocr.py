import unittest
from ocr_layout import spatial_lines
from pop_core import parse_ocr_text


def data_for(rows):
    # rows: texto, x, y, conf. La cantidad y el texto pueden estar en bloques
    # distintos y no tener exactamente el mismo centro vertical.
    data={k:[] for k in ('text','left','top','width','height','conf')}
    for text,x,y,conf in rows:
        for k,v in zip(data,(text,x,y,7*len(text),13,conf)):
            data[k].append(v)
    return data

class LayoutOCRTests(unittest.TestCase):
    def test_quantity_and_description_come_from_same_height(self):
        d=data_for([
            ('350',12,101,86),('AFICHE',97,103,89),('20X30',164,102,79),('OFERTA',215,102,90),
            ('2840',12,125,78),('CENEFA',97,125,92),('20X7',164,125,80),('OFERTA',210,125,87),
            ('410',12,150,82),('STICKER',97,149,89),('EDF',170,149,86),('42X6',205,150,79),
        ])
        lines=spatial_lines(d)
        self.assertEqual(len(lines),3)
        self.assertEqual([x['text'].split()[0] for x in lines],['350','2840','410'])
        parsed=parse_ocr_text('\n'.join(r['text'] for r in lines),'foto')
        self.assertEqual([x['cantidad'] for x in parsed],[350,2840,410])
    def test_no_mix_between_different_rows(self):
        d=data_for([('40',8,300,95),('AFICHE',90,300,95),('35X50',150,300,95),('QUILMES',210,300,95),
                    ('AFICHE',90,331,95),('20X30',150,331,95),('QUILMES',210,331,95)])
        parsed=parse_ocr_text('\n'.join(r['text'] for r in spatial_lines(d)),'foto')
        self.assertEqual([r['cantidad'] for r in parsed],[40,40])
        self.assertTrue(parsed[1]['cantidad_heredada'])
    def test_no_false_inheritance_if_number_is_uncertain(self):
        s='350 AFICHE 20X30 OFERTA\npe 6820 MINI CENEFA 7X3,5 BRAHMA\nAFICHE A3 BRAHMA'
        rows=parse_ocr_text(s,'foto')
        self.assertEqual(rows[0]['cantidad'],350)
        self.assertIsNone(rows[1]['cantidad'])
        self.assertEqual(rows[1]['cantidad_sugerida'],6820)
        self.assertIsNone(rows[2]['cantidad'])
        self.assertNotIn('pe 6820',rows[1]['detalle'])

if __name__=='__main__':unittest.main()

class NativePDFLayoutTests(unittest.TestCase):
    def test_native_text_pdf_separates_columns(self):
        from ocr_core import _native_pdf_texts
        class R: width=800
        class Page:
            rect=R()
            def get_text(self,mode):
                assert mode=='words'
                return [(20,100,45,110,'350',0,0,0),(100,100,150,110,'AFICHE',0,0,1),
                        (175,100,220,110,'20X30',0,0,2),(225,100,290,110,'OFERTA',0,0,3),
                        (430,100,460,110,'930',0,0,4),(480,100,540,110,'AFICHE',0,0,5),
                        (545,100,590,110,'A3',0,0,6),(595,100,660,110,'STELLA',0,0,7)]
        parts=_native_pdf_texts(Page(),True,.5)
        self.assertEqual(len(parts),2)
        self.assertIn('350 AFICHE 20X30 OFERTA',parts[0][1])
        self.assertIn('930 AFICHE A3 STELLA',parts[1][1])
