#!/usr/bin/env python3
# Rastrea el Registro SDP (sitios de producción, dato público) desde sispmex.sag.gob.cl y
# actualiza mexico_sdp.json. Pensado para correr en GitHub Actions (allí sí hay acceso al SAG).
# Réplica en Python de scripts/sdp_crawler.js. Dato público, sin datos personales.
# Uso: python3 sdp_fetch.py [daily|full]   (sin argumento: full los domingos, daily el resto)
import sys, os, re, json, time, datetime
import requests
from bs4 import BeautifulSoup

BASE = 'https://sispmex.sag.gob.cl/pubsber/'
REGIONS = [13,6,7,5,4,3,16,8,9,10,14,1,2,11,12]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'mexico_sdp.json')

M = {'Ene':1,'Feb':2,'Mar':3,'Abr':4,'May':5,'Jun':6,'Jul':7,'Ago':8,'Sep':9,'Set':9,'Oct':10,'Nov':11,'Dic':12,
     'Jan':1,'Apr':4,'Aug':8,'Dec':12}
def fecha(s):
    m = re.match(r'(\w{3})\w*\.?\s+(\d+),\s*(\d+)', s or '')
    if not m: return s or ''
    y = int(m.group(3)); y += 2000 if y < 100 else 0
    return '%04d-%02d-%02d' % (y, M.get(m.group(1)[:3], 1), int(m.group(2)))
def esp(x):
    m = re.match(r'(.*?)\.(.*?)\s*-\s*Clasificaci.n:\s*(.*)$', x)
    return [m.group(1).strip(), m.group(2).strip(), m.group(3).strip()] if m else [x, '', '']

def parse(html, rows):
    soup = BeautifulSoup(html, 'html.parser')
    n = 0
    for sp in soup.select('span.titulo2'):
        td = sp.find_parent('td')
        tr = td.find_parent('tr') if td else None
        if not tr: continue
        c = tr.find_all(recursive=False)
        if len(c) < 6: continue
        code = sp.get_text().strip()
        if not re.match(r'^\d+$', code): continue
        strong = td.find('strong')
        name = re.sub(r'^\s*SDP:\s*', '', strong.get_text()).strip() if strong else ''
        cell = c[2]
        for br in cell.find_all('br'): br.replace_with('\n')
        esps = [l.strip() for l in cell.get_text().split('\n') if l.strip()]
        rows[code] = [name, c[1].get_text().strip(), esps, c[3].get_text().strip(), c[4].get_text().strip(), c[5].get_text().strip()]
        n += 1
    return n

def crawl(mode):
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 (SAG-Exportaciones SDP updater)'})
    try: s.get(BASE + 'reporteSDP.asp', timeout=60)  # establece la cookie de sesión ASP
    except Exception as e: print('aviso: base no respondió:', e)
    TP = 300 if mode == 'daily' else 1000
    raw = {}
    for reg in REGIONS:
        pa = 1
        while True:
            url = BASE + 'reporteSDP.asp?TP=%d&PA=%d&BRIDREGION=%d&BRMUESTREO=99&BRESTADO=99&BCODSAG=&BRIDCOMUNA=0' % (TP, pa, reg)
            t0 = time.time()
            r = s.get(url, timeout=600)
            html = r.content.decode('iso-8859-1', 'replace')
            n = parse(html, raw)
            print('region %d pag %d -> %d filas (%ds)' % (reg, pa, n, round(time.time()-t0)), flush=True)
            if mode == 'daily' or n < TP: break
            pa += 1
    return raw

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ('full' if datetime.date.today().weekday() == 6 else 'daily')
    print('modo:', mode)
    db = json.load(open(OUT)) if os.path.exists(OUT) else {'R': {}}
    prev = len(db.get('R', {}))
    raw = crawl(mode)
    print('filas crudas obtenidas:', len(raw))
    if not raw:
        print('ERROR: sin filas; no se escribe nada (posible sesión/estructura distinta).'); sys.exit(1)
    built = {code: [r[0], 1 if r[1].upper().startswith('S') else 0,
                    [esp(x) for x in r[2] if 'lasific' in x], r[3], r[4], fecha(r[5])] for code, r in raw.items()}
    if mode == 'full':
        # Salvaguarda: no reemplazar con un conjunto sospechosamente chico
        if len(built) < max(5000, int(prev * 0.7)):
            print('ERROR: full trajo %d sitios (<70%% de %d); no se reemplaza.' % (len(built), prev)); sys.exit(1)
        db['R'] = built
    else:
        db['R'].update(built)  # daily: fusiona/actualiza, nunca reduce
    db['rev'] = datetime.date.today().strftime('%d-%m-%Y')
    db['n'] = len(db['R'])
    json.dump(db, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    print('mexico_sdp.json:', db['n'], 'sitios (antes', prev, ') ·', round(os.path.getsize(OUT)/1024), 'KB')

if __name__ == '__main__':
    main()
