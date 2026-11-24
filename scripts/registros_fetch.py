#!/usr/bin/env python3
# Rastrea las páginas de Registros/Procedimientos/Normativas/Publicaciones del SAG (export + USDA)
# y arma registros_sag.json: un feed público que la app baja sola e integra al catálogo de documentos.
# Corre en GitHub Actions (allí sí se alcanza sag.gob.cl). Solo documentos públicos.
import os, re, json, time, datetime, html
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'registros_sag.json')
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (SAG-Exportaciones registros)'})

# páginas a recorrer: (url_base, sección por defecto, nº de páginas, clave forzada o None)
PAGES = [
 ('https://www.sag.gob.cl/ambitos-de-accion/exportaciones/registros', 'r', 9, None),
 ('https://www.sag.gob.cl/ambitos-de-accion/exportaciones/procedimientos', 'p', 6, None),
 ('https://www.sag.gob.cl/ambitos-de-accion/exportaciones/normativas', 'n', 4, None),
 ('https://www.sag.gob.cl/ambitos-de-accion/exportaciones/publicaciones', 'h', 4, None),
 ('https://www.sag.gob.cl/ambitos-de-accion/productos-vegetales-diferentes-paises/registros', 'r', 9, None),
 ('https://www.sag.gob.cl/ambitos-de-accion/productos-vegetales-diferentes-paises/procedimientos', 'p', 9, None),
 ('https://www.sag.gob.cl/ambitos-de-accion/productos-vegetales-estados-unidos/procedimientos', 'p', 4, None),
 # NIMF 15 · Embalaje de madera (clave forzada n15)
 ('https://www.sag.gob.cl/ambitos-de-accion/embalajes-de-madera/procedimientos', 'p', 3, 'n15'),
 ('https://www.sag.gob.cl/ambitos-de-accion/embalajes-de-madera/registros', 'r', 3, 'n15'),
 ('https://www.sag.gob.cl/ambitos-de-accion/embalajes-de-madera/normativas', 'n', 3, 'n15'),
 ('https://www.sag.gob.cl/ambitos-de-accion/embalajes-de-madera-de-exportacion/procedimientos', 'p', 3, 'n15'),
 ('https://www.sag.gob.cl/ambitos-de-accion/la-marca-nimf-ndeg15/procedimientos', 'p', 2, 'n15'),
 ('https://www.sag.gob.cl/ambitos-de-accion/paises-que-exigen-la-nimf-ndeg-15/procedimientos', 'r', 2, 'n15'),
 # Lobesia botrana · PNLb (clave forzada lob)
 ('https://www.sag.gob.cl/ambitos-de-accion/lobesia-botrana-o-polilla-del-racimo-de-la-vid/registros', 'r', 3, 'lob'),
 ('https://www.sag.gob.cl/ambitos-de-accion/lobesia-botrana-o-polilla-del-racimo-de-la-vid/normativas', 'n', 3, 'lob'),
]
# país/tema -> clave CAT_PAISES (por palabra clave en el título)
KEYS = [('china','cn'),('corea','kr'),('méxico','mx'),('mexico','mx'),('estados unidos','us'),('ee.uu','us'),('brasil','br'),
 ('indonesia','id'),('perú','pe'),('peru','pe'),('rusia','ru'),('vietnam','vn'),('taiw','tw'),('jap','jp'),('canad','ca'),
 ('colombia','co'),('tailandia','th'),('filipinas','ph'),('panam','pa'),('india','in'),('nueva zeland','nz'),('costa rica','cr'),
 ('sri lanka','lk'),('paraguay','py'),('irán','ir'),('iran','ir'),('argentina','ar'),('australia','au'),('sudáfrica','za'),('sudafrica','za'),
 ('lobesia','lob'),('mosca','mos'),('inocuidad','ino'),('maleza','plg'),('propagaci','map')]
def keyof(title):
    t = title.lower()
    for kw, k in KEYS:
        if kw in t: return k
    return 'gen'
def typeof(title, sec):
    t = title.lower()
    if 'circular' in t: return 'Circular'
    if 'resoluci' in t: return 'Resolución'
    if 'protocolo' in t: return 'Protocolo'
    if 'plan de trabajo' in t or 'plan ' in t: return 'Plan de trabajo'
    if 'lineamiento' in t: return 'Lineamiento'
    if 'instructivo' in t: return 'Instructivo'
    if 'procedimiento' in t: return 'Procedimiento'
    if 'nómina' in t or 'nomina' in t: return 'Nómina'
    if 'registro' in t: return 'Registro'
    if 'listado' in t or 'lista' in t: return 'Lista'
    return {'r':'Registro','p':'Procedimiento','n':'Normativa','h':'Guía','c':'Circular'}.get(sec,'Documento')

FILERE = re.compile(r'/sites/default/files/[^"\')>]+\.(?:xlsx|xls|pdf|docx|doc)', re.I)
def scrape(url, sec, pages, forcekey=None):
    out = {}
    for pa in range(pages):
        u = url + ('?title=&field_tema_registros_y_listas_target_id=All&field_tipo_de_registro_target_id=All&page=%d' % pa if 'registros' in url
                   else '?page=%d' % pa)
        try:
            r = S.get(u, timeout=90)
        except Exception as e:
            print('  err', u, e); continue
        soup = BeautifulSoup(r.content.decode('utf-8','replace'), 'html.parser')
        rows = 0
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/sites/default/files/' not in href: continue
            if not re.search(r'\.(xlsx|xls|pdf|docx|doc)$', href, re.I): continue
            full = href if href.startswith('http') else 'https://www.sag.gob.cl' + (href if href.startswith('/') else '/'+href)
            fn = full.split('/sites/default/files/')[-1]
            title = re.sub(r'\s+', ' ', html.unescape(a.get_text())).strip()
            if not title or len(title) < 4:
                # intentar el texto de la fila
                tr = a.find_parent(['tr','article','div'])
                if tr: title = re.sub(r'\s+',' ', tr.get_text(' ')).strip()[:160]
            if not title: continue
            # fecha dd/mm/yyyy cercana
            f = ''
            ctx = (a.find_parent(['tr','article','div']) or a)
            m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', ctx.get_text(' ')) if ctx else None
            if m: f = '%s-%02d-%02d' % (m.group(3), int(m.group(2)), int(m.group(1)))
            out[fn] = {'f': f, 't': typeof(title, sec), 'n': title[:180], 'c': forcekey or keyof(title), 'u': full, 's': sec}
            rows += 1
        print('  %s pag %d -> %d archivos' % (url.split('/')[-1], pa, rows), flush=True)
        if rows == 0 and pa > 0: break
        time.sleep(0.5)
    return out

def main():
    allrows = {}
    for url, sec, pages, fk in PAGES:
        print('==', url)
        allrows.update(scrape(url, sec, pages, fk))
    print('TOTAL archivos:', len(allrows))
    if len(allrows) < 30:
        print('ERROR: muy pocos (%d); no se reemplaza.' % len(allrows)); raise SystemExit(1)
    data = {'rev': datetime.date.today().strftime('%d-%m-%Y'),
            'n': len(allrows),
            'R': sorted(allrows.values(), key=lambda x: (x['f'] or '0'), reverse=True)}
    json.dump(data, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    print('registros_sag.json:', data['n'], 'documentos ·', round(os.path.getsize(OUT)/1024), 'KB')

if __name__ == '__main__':
    main()
