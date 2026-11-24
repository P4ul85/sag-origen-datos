#!/usr/bin/env python3
# Actualiza labs.json (laboratorios autorizados del SAG) sin PC, desde GitHub Actions.
# Baja la página del SAG, ubica el Excel vigente, lo parsea (igual que scripts/lab_build.py del repo
# privado) y reescribe labs.json si cambió. Solo datos del laboratorio (sin C.I. ni nombres de personas).
import os, re, io, json, datetime, sys
import requests, openpyxl

PAGE = 'https://www.sag.cl/content/lista-de-laboratorios-autorizados-para-monitoreo-muestreo-y-analisis-en-el-marco-del-programa-de-certificacion-fitosanitaria'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'labs.json')
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (SAG-Exportaciones labs updater)'})

def find_xlsx(html):
    cands = re.findall(r'href="([^"]*certificacion_fitosanitaria_lab_autorizados[^"]*\.xlsx)"', html, re.I)
    if not cands: return None
    u = cands[0].replace('&amp;', '&')
    if u.startswith('//'): u = 'https:' + u
    elif u.startswith('/'): u = 'https://www.sag.cl' + u
    return u

def cl(v):
    if v is None: return ''
    if isinstance(v, (datetime.date, datetime.datetime)): return v.strftime('%Y-%m-%d')
    v = str(v).replace('\xa0', ' '); v = re.sub(r'[ \t]+', ' ', v); v = re.sub(r'\s*\n\s*', '\n', v).strip()
    return v

def parse_xlsx(content):
    wb = openpyxl.load_workbook(io.BytesIO(content)); ws = wb.active
    M = {}
    for r in ws.merged_cells.ranges:
        v = ws.cell(r.min_row, r.min_col).value
        for row in range(r.min_row, r.max_row + 1):
            for col in range(r.min_col, r.max_col + 1): M[(row, col)] = (v, r.min_row)
    def val(row, col):
        return M.get((row, col), (ws.cell(row, col).value, row))
    rev = ''; hdr = None
    for row in range(1, 40):
        a = cl(ws.cell(row, 1).value); m = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', a)
        if m and 'ctualizado' in a: rev = m.group(1)
        if a.lower().startswith('nombre o raz'): hdr = row
    assert hdr, 'no se encontró la fila de encabezado'
    labs = []; cur = None; last = {}
    for row in range(hdr + 2, ws.max_row + 1):
        name, top = val(row, 1); name = cl(name)
        if not name and not cl(val(row, 7)[0]) and not cl(val(row, 8)[0]): continue
        if name and (cur is None or top != cur['_top']):
            g = lambda c: cl(val(row, c)[0]); vig = g(4)
            m = re.match(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})$', vig)
            if m: vig = '%s-%02d-%02d' % (m.group(3), int(m.group(2)), int(m.group(1)))
            cur = {'_top': top, 'n': re.sub(r'\s+', ' ', name), 'rg': g(2), 'res': re.sub(r'\n+', ' · ', g(3)),
                   'vig': vig, 'rut': g(5), 'dir': re.sub(r'\n+', ' ', g(9)), 'mail': re.sub(r'\s+', ' ', g(10)),
                   'tel': re.sub(r'\n+', ' / ', g(11)), 'obs': g(16), 'A': []}
            labs.append(cur); last = {}
        if cur is None: continue
        p = cl(val(row, 6)[0]) or last.get('p', ''); e = cl(val(row, 7)[0]) or last.get('e', ''); pl = cl(val(row, 8)[0])
        if not (p or e or pl): continue
        last = {'p': p, 'e': e}
        pl = re.sub(r'\s*\n\s*', ', ', pl).strip(' ,'); e = re.sub(r'\s*\n\s*', ', ', e).strip(' ,.')
        p = p.strip(); p = {'USA': 'Estados Unidos', 'EE.UU.': 'Estados Unidos'}.get(p, p)
        cur['A'].append([p, e, pl])
    for l in labs: l.pop('_top')
    return rev, labs

def main():
    force = ('--force' in sys.argv) or os.environ.get('FORCE')=='1'
    r = S.get(PAGE, timeout=90); url = find_xlsx(r.text)
    if not url:
        print('ERROR: no encontré el enlace al Excel en la página.'); sys.exit(1)
    fname = requests.utils.unquote(url.split('/')[-1])
    print('Excel en el SAG:', fname, '|', url)
    old = json.load(open(OUT)) if os.path.exists(OUT) else None
    if old and old.get('file') == fname and not force:
        print('Sin cambios: labs.json ya está en', fname); return
    content = S.get(url, timeout=120).content
    rev, labs = parse_xlsx(content)
    if len(labs) < 3:
        print('ERROR: el Excel trajo', len(labs), 'laboratorios; no se reemplaza.'); sys.exit(1)
    out = {'rev': rev, 'file': fname, 'url': 'https://www.sag.gob.cl/sites/default/files/' + fname.replace(' ', '%20'),
           'n': len(labs), 'L': labs}
    json.dump(out, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    if old:
        on = {l['n']: l for l in old['L']}; nn = {l['n']: l for l in labs}
        add = [n for n in nn if n not in on]; rem = [n for n in on if n not in nn]
        ch = [n for n in nn if n in on and (nn[n]['A'] != on[n]['A'] or nn[n]['vig'] != on[n]['vig'] or nn[n]['res'] != on[n]['res'])]
        print('CAMBIOS vs', old.get('rev'), '| nuevos:', add, '| retirados:', rem, '| modificados:', ch)
    print('labs.json', len(labs), 'laboratorios ·', sum(len(l['A']) for l in labs), 'alcances · rev', rev)

if __name__ == '__main__':
    main()
