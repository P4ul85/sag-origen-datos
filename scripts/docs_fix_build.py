#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construye docs_fix.json: mapa nodo (data.js, enlaces Drive rotos) -> URL oficial del SAG,
resuelto automaticamente desde registros_sag.json (el feed que ya se actualiza solo).
Asi la app reemplaza los enlaces de Drive por el PDF publico del SAG, sin PC y sin hornear URLs:
si el SAG cambia una URL, el feed la trae y este mapa se regenera en el mismo workflow.
Uso: python3 scripts/docs_fix_build.py [--write]  (sin --write solo imprime la revision)
"""
import json, re, sys, os, unicodedata, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FEED = os.path.join(ROOT, 'registros_sag.json')
OUT  = os.path.join(ROOT, 'docs_fix.json')

def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii','ignore').decode().lower()
    return re.sub(r'\s+',' ', s)

# Tabla de nodos oficiales: id -> (clave pais/tema, [palabras clave que DEBEN estar], [palabras que suman], tipo)
# tipo: 'proto'|'lineam'|'circ'|'add'|'instr'|'plan'|'gen'  (solo pondera, no filtra)
# Las plantillas propias del usuario (Cobro en blanco, Planilla despacho, SIF, informes,
# Carta de responsabilidad, Cambio de mercado) NO van aqui: se quedan en Drive.
NODES = {
 '4234500': ('cn', ['carozo'], ['nectarin'], 'lineam'),
 '3942670': ('br', ['arandano'], ['ciruela','smr'], 'lineam'),
 '3942729': ('br', ['uva'], ['smr'], 'lineam'),
 '4151389': ('cn', ['manzana'], [], 'lineam'),
 '4151445': ('tw', ['manzana'], [], 'lineam'),
 '4152411': ('cn', ['pera'], [], 'lineam'),
 '4152730': ('vn', ['manzana'], [], 'lineam'),
 '4152854': ('kr', ['cereza'], [], 'lineam'),
 '4152871': ('cn', ['palta'], [], 'lineam'),
 '4270412': ('cn', ['citrico'], [], 'lineam'),
 '4270713': ('cn', ['arandano'], [], 'lineam'),
 '4343612': ('kr', ['palta'], ['hass'], 'lineam'),
 '4152914': ('kr', ['arandano'], [], 'lineam'),
 '4482643': ('tw', ['manzana'], [], 'lineam'),
 '4482678': ('tw', ['ajo'], [], 'lineam'),
 '4482755': ('vn', ['cereza'], [], 'lineam'),
 '4482806': ('vn', ['manzana'], [], 'lineam'),
 '4482847': ('vn', ['uva'], [], 'lineam'),
 '4152823': ('jp', ['cereza'], [], 'lineam'),
 '9121866': ('tw', ['manzana'], [], 'lineam'),
 # Protocolos
 '4152666': ('cn', ['citrico'], [], 'proto'),
 '4152703': ('in', ['palta'], ['systems','aproximacion','sistema'], 'proto'),
 '4152899': ('cn', ['carozo'], ['nectarin'], 'proto'),
 '4152905': ('cn', ['palta'], [], 'proto'),
 '4270490': ('cn', ['pera'], [], 'proto'),
 '4270558': ('cn', ['avellana'], [], 'proto'),
 '4270861': ('cn', ['manzana'], [], 'proto'),
 '4270889': ('cn', ['uva'], [], 'proto'),
 '4270949': ('cn', ['arandano'], [], 'proto'),
 '4271126': ('cn', ['cereza'], [], 'proto'),
 '4271246': ('cn', ['nue'], ['sin cascara','s-cascara'], 'proto'),
 '4271466': ('cn', ['ciruela'], [], 'proto'),
 '4271521': ('cn', ['kiwi'], [], 'proto'),
 '4331979': ('kr', ['palta'], ['hass'], 'proto'),
 '4349455': ('kr', ['arandano'], [], 'proto'),
 '4152891': ('kr', ['uva'], ['kiwi','naranja','limon'], 'proto'),
 '4152919': ('kr', ['cereza'], [], 'proto'),
 '4482870': ('tw', ['manzana'], [], 'proto'),
 '4547964': ('in', ['palta'], ['systems','aproximacion','sistema'], 'proto'),
 # Addendums
 '4270599': ('cn', ['nue'], ['con cascara','addendum'], 'add'),
 '4270745': ('cn', ['manzana'], ['addendum'], 'add'),
 '4271317': ('cn', ['protocolo'], ['addendum'], 'add'),
 '4349808': ('kr', ['lobesia'], ['addendum'], 'add'),
 '4271589': ('cn', ['frio'], ['indicador','tratamiento'], 'gen'),
 # Instructivos / varios oficiales
 '4151683': ('id', ['muestreo'], ['analisis','indonesia'], 'instr'),
 '4350349': ('co', ['palta'], ['plan'], 'plan'),
 '3939008': ('kr', ['palta'], ['hass'], 'lineam'),   # Paltas Hass a Corea (anterior) -> lineamiento vigente
 '3876296': ('gen', ['manual'], ['certificacion','exportacion'], 'gen'),  # Manual Origen
}

def main():
    feed = json.load(open(FEED, encoding='utf-8'))
    R = feed['R']
    for r in R:
        r['_n'] = norm(r['n'])
    # palabras que marcan un documento-guia (no una nomina de participantes)
    DOCTYPE = ['protocolo','lineamiento','directriz','directric','circular','instructivo',
               'plan de trabajo','requisit','addendum','sistema de mitigacion','medidas de proteccion','anexo']
    out = {}
    review = []
    for nid,(ck, must, nice, typ) in NODES.items():
        best=None; bestsc=-1
        for r in R:
            if r['c']!=ck:
                continue
            if r['s']=='r':      # saltar registros/listados de participantes
                continue
            n=r['_n']
            if not all(m in n for m in must):
                continue
            sc=10+sum(2 for x in nice if x in n)
            if any(w in n for w in DOCTYPE): sc+=6   # es un documento, no una nomina
            TW={'proto':'protocolo','lineam':'lineamiento','add':'addendum','plan':'plan de trabajo','instr':'instructivo'}
            if typ in TW and TW[typ] in n: sc+=4     # el nodo prefiere su propio tipo
            # preferir el mas reciente a igualdad de puntaje
            f=r.get('f','')
            if (sc,f) > (bestsc, best['f'] if best else ''):
                bestsc=sc; best=r
        if best:
            out[nid]=best['u']
            review.append((nid, ck, '/'.join(must), best['n'][:60], best['u'].split('/')[-1][:48]))
        else:
            review.append((nid, ck, '/'.join(must), '*** SIN MATCH ***', ''))
    # imprimir revision
    for row in sorted(review, key=lambda x:(x[1],x[2])):
        print(f"{row[0]} [{row[1]:>3}] {row[2]:<18} -> {row[3]:<62} {row[4]}")
    print(f"\nResueltos {len(out)}/{len(NODES)}")
    if '--write' in sys.argv:
        obj={'rev':datetime.date.today().strftime('%d/%m/%Y'),'n':len(out),'M':out}
        json.dump(obj, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, separators=(',',':'))
        print('escrito', OUT)

if __name__=='__main__':
    main()
