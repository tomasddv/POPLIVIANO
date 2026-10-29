"""Comparador tolerante al OCR para descripción de POP (no corrige cantidades).

Separa similitud de texto y certeza: cantidades nunca son parte del score.
Los materiales indistinguibles entre sí no se autoasignan.
"""
from __future__ import annotations

import re
import unicodedata
from rapidfuzz import fuzz

# Normalización limitada a convenciones frecuentes en los remitos, no a marcas.
REPLACEMENTS = {
    'CENEFAS':'CENEFA', 'CENFAS':'CENEFA', 'CENFAS':'CENEFA',
    'CENEF':'CENEFA','CENERA':'CENEFA', 'CENEFA':'CENEFA',
    'AFICHES':'AFICHE', 'AFICH':'AFICHE', 'AFÍCME':'AFICHE',
    'AICHE':'AFICHE','ASICHE':'AFICHE','AFFICHE':'AFICHE','AFICME':'AFICHE',
    'ESTELLA':'STELLA','NEALITORAL':'NEA LITORAL', 'NEAMLITORAL':'NEA LITORAL',
    'NEAMITORAL':'NEA LITORAL', 'NEAVLITORAL':'NEA LITORAL',
    'NEALITORA':'NEA LITORAL', 'NEALITORAL':'NEA LITORAL',
    'GENERICA':'GENERICO', 'GENERICAS':'GENERICO', 'GENERICOS':'GENERICO',
    'LATA':'LATA', 'LATONES':'LATON', 'LATON':'LATON',
    'BOT':'BOTELLA', 'CERVEZA':'',
    'REG':'REGIONES', 'VARIAS':'VARIAS', 'REGION':'REGIONES',
    'OFERTA':'OFERTA', 'CANEFAS':'CENEFA', 'AO':'ANDES ORIGEN ORO',
}
TYPE_MARKERS = {'AFICHE','CENEFA','STICKER','COLLARIN','BANNER','VINILO','WOBBLER',
                'CARTEL','FLEJE','COMBO'}
GENERIC_WORDS = {'DE','DEL','LA','LAS','EL','LOS','EN','CON','Y','X','PARA','POP','K','T','EXTERNO',
                 'AS','FAMILIA','FAMILIAR','S','SA','OFERTA','INTERNO','GENERAL'}


def clean(s: str) -> str:
    s=unicodedata.normalize('NFKD',str(s or '').upper())
    s=''.join(c for c in s if not unicodedata.combining(c))
    s=s.replace('×','X').replace('·',' ').replace('+',' + ')
    # Reparar O vs 0 e I vs 1 en cifras conectadas por X, dejando intactas marcas.
    s=re.sub(r'(?<![A-Z0-9])([0-9OILSB]{1,3})\s*[X*]\s*([0-9OILSB]{1,3})(?![A-Z0-9])',
             lambda m: _numeric_part(m.group(1))+'X'+_numeric_part(m.group(2)),s)
    # Convertir 7X3,5 -> 7X3 5
    s=re.sub(r'\bAFICHE\s+AS\b','AFICHE A3',s)
    s=re.sub(r'\b7X35\b', '7X3 5',s)
    s=re.sub(r'[^A-Z0-9]+',' ',s)
    words=s.split()
    result=[]
    for w in words:
        w=REPLACEMENTS.get(w,w)
        if w:result.extend(w.split())
    # Alianzas frecuentes de OCR en formatos (sin tocar números de cantidades)
    return ' '.join(result)


def _numeric_part(s):
    return s.translate(str.maketrans({'O':'0','I':'1','L':'1','S':'5','B':'8'}))


def _sig(s):
    text=clean(s)
    tokens=text.split()
    # Formatos dimensiones: normalizar si Tesseract insertó espacios
    sizes=re.findall(r'\b\d{1,3}\s*X\s*\d{1,3}\b',text)
    sizes += re.findall(r'\bA3\b',text)
    if re.search(r'\b7\s*X\s*3\s*5\b',text):sizes.append('7X3 5')
    types={t for t in tokens if t in TYPE_MARKERS}
    # Interpreta como afiche los formatos A3, 35x50, 50x70, 20x30 solo cuando no haya otro tipo explícito
    if not types and (('A3' in tokens) or any(s in ('35X50','50X70','20X30') for s in sizes)):
        types={'AFICHE'}
    elif not types and any(s in ('20X7','7X3','7X3 5') for s in sizes):
        types={'CENEFA'}
    meaningful={t for t in tokens if t not in GENERIC_WORDS and len(t)>1 and not t.isdigit()}
    return text,types,tuple(sizes),meaningful


def _variants(item,alias):
    parts=[str(item.get(k) or '').strip() for k in ('material','grupo','formato','hoja')]
    sheet,grp,fmt=parts[3],parts[1],parts[2]
    phrases=[alias, parts[0],f'{grp} {fmt}',f'{sheet} {fmt}',f'{sheet} {grp} {fmt}']
    # Variante con palabra «afiche» aunque el Excel solo diga «35x50».
    if re.search(r'\b(?:A3|35\s*X\s*50|50\s*X\s*70|20\s*X\s*30)\b',clean(fmt)):
        phrases.append(f'{sheet} {grp} AFICHE {fmt}')
    # Denominaciones del remito: Andes = AO (Andes Origen Oro) del Excel.
    if sheet.upper() == 'AO':
        phrases += [f'ANDES ORIGEN ORO {grp} {fmt}', f'AFICHE ANDES {fmt}',
                    f'ANDES {fmt}',f'ANDES ORO {fmt}']
    # En Q3 el remito identifica como REG VARIAS a los AFICHES genéricos
    # positivos DDV del grupo regional GBA/COSTA/... del Excel. Se usan alias
    # de búsqueda, sin reescribir ni ocultar el encabezado original del Excel.
    if clean(sheet).startswith('GENERICO LATON') and 'GBA' in clean(grp) and item.get('cantidad_excel',0)>0:
        kind='LATON' if 'LATON' in clean(grp) else 'LITRO'
        phrases += [f'AFICHE OFERTA {kind} {fmt} REG VARIAS',
                    f'AFICHE OFERTA {kind} {fmt} REGIONES VARIAS']
    # Pasar SOLO alias completo o expresión del excel con material y grupo. Nunca el formato suelto.
    unique=[]
    for p in phrases:
        cp=clean(p)
        if cp and cp not in unique:unique.append(cp)
    return unique


def _size_similarity(a,b):
    if not a or not b:return 0,False
    if set(a) & set(b):return 10,False
    # Distancias por carácter: número equivocado -> tolerable pero debe revisarse.
    def distance(x,y):
        from rapidfuzz.distance import Levenshtein
        return Levenshtein.distance(x,y)
    near=min(distance(x,y) for x in a for y in b)
    if near<=2:return -5,True
    return -21,True


def score_detail(detail,variant):
    q,qtypes,qsizes,qtoks=_sig(detail)
    v,vtypes,vsizes,vtoks=_sig(variant)
    if not q or not v:return 0.0,[]
    ratio=fuzz.ratio(q,v)
    token=fuzz.token_set_ratio(q,v)
    token_sort=fuzz.token_sort_ratio(q,v)
    # Fuzzy word coverage permite pequeños errores en palabras no idénticas.
    term_coverage=0.0
    if qtoks and vtoks:
        term_coverage=sum(max((fuzz.ratio(a,b) for b in vtoks),default=0)
                          for a in qtoks)/len(qtoks)
    base=.23*ratio+.38*token+.16*token_sort+.23*term_coverage
    flags=[]
    if qtypes and vtypes and not (qtypes & vtypes):
        base-=24;flags.append('Tipo de material diferente')
    offset,size_conflict=_size_similarity(qsizes,vsizes)
    base+=offset
    if size_conflict:flags.append('Formato o medida diferente: revisar')
    # Cualquier match de texto de una sola palabra es insuficiente, salvo etiqueta singular.
    if len(qtoks & vtoks)<=1 and len(qtoks)>=3 and len(vtoks)>=3:
        base-=4
    return max(0.0,min(100.0,base)),flags


def rank_matches(detail,catalog,aliases=None):
    aliases=aliases or {}
    results=[]
    # Identidades distintivas del propio Excel: no confundir Stella con Corona
    # aunque los dos tengan AFICHE A3 / CENEFA 20x7.
    sheet_tokens=set()
    for item in catalog:
        if item.get('hoja'):
            terms=clean(item['hoja']).split()
            if len(terms)==1 and len(terms[0])>=4 and terms[0] not in ('GENERICO','COMBOS','STICKER','OFERTA','VALUE'):
                sheet_tokens.add(terms[0])
    query_tokens=set(clean(detail).split())
    identified=query_tokens & sheet_tokens
    if 'OFERTA' in query_tokens and not ({'LATON','LITRO'} & query_tokens):
        identified.add('OFERTA')
    # Protección contra falsos positivos: un afiche de LITRO o LATONES
    # no puede enlazarse automáticamente a Pepsi solo porque comparta medida.
    identity_tokens={'LATON','LITRO','COMBO','BRAHMA','STELLA','CORONA','QUILMES',
                     'BUD','PEPSI','GATORADE','MICHELOB','ANDES','ROCKSTAR','H2OH',
                     'PANCHO','PANCHUQUE','EMPANADAS','SANDWICH','LATONES'}
    category_anchors=query_tokens & identity_tokens
    region_tokens={'CUYO','NEA','LITORAL','PATAGONIA','NOA','MUNDIAL','GOLD','INVIERNO'}
    region_anchors=query_tokens & region_tokens

    for item in catalog:
        al=aliases.get(item['id'],'')
        group_tokens=set(clean(item.get('grupo','')).split())
        group_conflict=bool(('LATON' in query_tokens and 'LITRO' in group_tokens and 'LATON' not in group_tokens)
                            or ('LITRO' in query_tokens and 'LATON' in group_tokens and 'LITRO' not in group_tokens))
        best=(-1,None,[])
        for phrase in _variants(item,al):
            score,flags=score_detail(detail,phrase)
            if identified and not identified.intersection(set(clean(phrase).split())):
                score-=25
                flags=[*flags,'Marca u hoja diferente: revisar']
            missing=category_anchors.difference(set(clean(phrase).split()))
            if missing:
                score-=32
                flags=[*flags,'Producto o campaña diferente: '+', '.join(sorted(missing))]
            if group_conflict:
                score-=28
                flags=[*flags,'Subgrupo LATON/LITRO diferente: revisar']
            # Campañas y regiones no son intercambiables aunque compartan 35x50.
            missing_region=region_anchors.difference(set(clean(phrase).split()))
            if missing_region:
                score-=10 * len(missing_region)
                flags=[*flags,'Campaña/región diferente: '+', '.join(sorted(missing_region))]
            if score>best[0]:best=(score,phrase,flags)
        results.append({'id':item['id'],'score':round(best[0],1),'variant':best[1],'flags':best[2],
                        'excel':item['cantidad_excel']})
    return sorted(results,key=lambda x:(-x['score'],x['id']))


def suggest_matches(rows,catalog,aliases=None,high=86,margin=9,minimum=48):
    """Sugerir enlace textual; el usuario debe aceptar el OCR antes de conciliar.

    ``high`` y ``margin`` son umbrales conservadores para evitar productos similares.
    Nunca se usa ``cantidad_excel`` para decidir el material.
    """
    output=[]
    for r in rows:
        ranks=rank_matches(r.get('detalle',''),catalog,aliases)
        best=ranks[0] if ranks else {'id':'','score':0,'flags':[]}
        second=ranks[1] if len(ranks)>1 else {'score':0}
        margin_actual=best['score']-second['score']
        suggested=best['id'] if best['score']>=minimum else ''
        strong=best['score']>=high and margin_actual>=margin and not best['flags']
        # Hay OCR con errores en 1-2 caracteres, se puede proponer pero no validar recepción.
        proposed=strong or (best['score']>=73 and margin_actual>=14 and not best['flags'])
        quantity=r.get('cantidad')
        row={**r, 'sugerido':suggested,
             'puntaje':round(best['score']), 'segunda_opcion':round(second['score']),
             'alternativas':[{'id':x['id'],'score':x['score']} for x in ranks[:3]],
             'alertas_match':best['flags'],
             'id':best['id'] if proposed else '',
             'estado_match':('Propuesta alta · revisar' if proposed else
                       'Posible · revisar' if suggested else 'Sin coincidencia'),
             'cantidad_excel_sugerida':best.get('excel') if suggested else None}
        if quantity is None and r.get('cantidad_sugerida') is not None:
            row['estado_match']+=' / cifra OCR dudosa'
        output.append(row)
    return output
