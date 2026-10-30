"""Genera un XLSX BORRADOR desde fotos / PDF, sin dar por válidas las cifras OCR."""
from __future__ import annotations
from io import BytesIO
import re
import xlsxwriter


def make_draft(rows,remito,fecha):
    num=re.sub(r'\D','',str(remito))
    if not num:raise ValueError('Indicá el número de remito.')
    num=num.zfill(8)
    if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',fecha):
        raise ValueError('Fecha esperada AAAA-MM-DD.')
    if not rows:raise ValueError('El OCR no detectó renglones de materiales. Probá otra imagen.')
    b=BytesIO()
    wb=xlsxwriter.Workbook(b,{'in_memory':True})
    ws=wb.add_worksheet('REMITO')
    dark={'font_color':'#000000'}
    head=wb.add_format({**dark,'bold':True,'bg_color':'#CDE8F9','border':1,'text_wrap':True})
    normal=wb.add_format({**dark,'border':1})
    qty=wb.add_format({**dark,'border':1,'num_format':'#,##0','bg_color':'#FFF3C7'})
    inherited=wb.add_format({**dark,'border':1,'bg_color':'#FDE68A'})
    missing=wb.add_format({**dark,'border':1,'bg_color':'#FECACA'})
    cols=['REMITO','FECHA','COLUMNA','FILA','DESCRIPCION POP','CANTIDAD','ORIGEN CANTIDAD','OBSERVACIONES','REFERENCIA','INCLUIR']
    for ci,h in enumerate(cols):ws.write(0,ci,h,head)
    for ri,row in enumerate(rows,1):
        column=str(row.get('pagina') or 'Página 1')
        original=row.get('cantidad');suggestion=row.get('cantidad_sugerida')
        origin=str(row.get('origen_cantidad') or 'OCR SIN VERIFICAR')
        if row.get('cantidad_heredada'):origin='HEREDADA - REVISAR'
        for ci,x in enumerate([num,fecha,column,str(row.get('linea',ri)),str(row.get('detalle','')).strip(),
                                None,origin,'',str(row.get('ocr','')),'SI' if original is not None else 'NO']):
            if ci==5:
                if original is None:ws.write_blank(ri,ci,None,missing)
                else:ws.write_number(ri,ci,int(original),qty)
            else:ws.write(ri,ci,x, inherited if ci==6 and row.get('cantidad_heredada') else normal)
        if suggestion is not None:
            ws.write(ri,7,f'Posible OCR: {suggestion}; revisar fotografía',normal)
    ws.set_column('A:A',13);ws.set_column('B:B',14);ws.set_column('C:C',33)
    ws.set_column('D:D',9);ws.set_column('E:E',57);ws.set_column('F:F',14)
    ws.set_column('G:G',29);ws.set_column('H:H',37);ws.set_column('I:I',65);ws.set_column('J:J',13)
    ws.freeze_panes(1,0)
    ws.autofilter(0,0,len(rows),9)
    rules=wb.add_worksheet('INSTRUCCIONES')
    for i,txt in enumerate([
        'BORRADOR OCR: ESTA PLANILLA NO ESTÁ VERIFICADA.',
        '1. Compará cada descripción contra la foto/PDF.',
        '2. Corregí cada cantidad. Rojo = sin cantidad. Si corresponde, completá cantidad y poné INCLUIR=SI.',
        '3. Amarillo en ORIGEN = cantidad heredada: VERIFICAR.',
        '4. No borres los encabezados REMITO, FECHA, DESCRIPCION POP ni CANTIDAD.',
        '5. Guardá el archivo y recién entonces subilo al tablero en «Excel de remitos revisados».',
        '6. Las cantidades originales del remito no se sustituyen por las del Excel de asignación.'
    ]):rules.write(i,0,txt,normal)
    rules.set_column('A:A',110)
    wb.close()
    return b.getvalue()
