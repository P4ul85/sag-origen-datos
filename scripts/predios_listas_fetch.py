#!/usr/bin/env python3
# Abre los Excel de listados de predios del feed de registros y arma predios_listas.json:
# índice público  Código SAG (CSG) -> en qué listas/mercados del SAG aparece el predio.
# Solo datos públicos (los listados del SAG). Corre en GitHub Actions.
import os, re, io, json, time, datetime
import requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, 'registros_sag.json')
OUT = os.path.join(ROOT, 'predios_listas.json')
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (SAG predios-listas)'})

# ¿es un listado de predios por mercado/especie? (por el título)
LISTA_RE = re.compile(r'predio|participante|aprobad|consolidad|sitios?\b|regla\s+vid|csg|c\.?s\.?g|habilitad|inscrit', re.I)
# columnas que contienen el Código SAG del predio/sitio/productor
COLHDR_RE = re.compile(r'\bcsg\b|c[óo]digo.*(sag|sitio|predio|productor|csg)|sitio\s*de\s*produc|c[óo]d\.?\s*(sitio|predio|sag)|\bcsp\b|cuartel', re.I)
CODE_RE = re.compile(r'^\d{5,8}$')

MERCADOS = [('china','China'),('corea','Corea'),('japón','Japón'),('japon','Japón'),('méxico','México'),('mexico','México'),
 ('ee.uu','EE.UU.'),('estados unidos','EE.UU.'),('usa','EE.UU.'),('brasil','Brasil'),('perú','Perú'),('peru','Perú'),
 ('vietnam','Vietnam'),('indonesia','Indonesia'),('taiw','Taiwán'),('india','India'),('tailandia','Tailandia'),
 ('argentina','Argentina'),('colombia','Colombia'),('canad','Canadá'),('rusia','Rusia'),('filipinas','Filipinas')]
ESPECIES = [('arándano','Arándano'),('arandano','Arándano'),('cerez','Cereza'),('uva','Uva de mesa'),('vid','Uva de mesa'),
 ('carozo','Carozos'),('ciruel','Ciruela'),('nectarin','Nectarina'),('durazno','Durazno'),('damasco','Damasco'),
 ('manzana','Manzana'),('pera','Pera'),('kiwi','Kiwi'),('palta','Palta'),('cítrico','Cítricos'),('citrico','Cítricos'),
 ('naranj','Cítricos'),('limón','Cítricos'),('nuez','Nueces'),('nuec','Nueces'),('avellana','Avellana'),('ajo','Ajo'),
 ('caqui','Caqui'),('granad','Granada'),('pomácea','Pomáceas'),('pomacea','Pomáceas'),('mosca','Mosca de la fruta')]
def pick(title, table, default=''):
    t = title.lower()
    for kw, v in table:
        if kw in t: return v
    return default

def parse_xlsx(content):
    import openpyxl
    codes = set()
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    for ws in wb.worksheets:
        target_cols = None
        nrow = 0
        for row in ws.iter_rows(values_only=True):
            nrow += 1
            if nrow > 60000: break
            if target_cols is None:
                # ¿es fila de encabezado con una columna de código?
                cols = [i for i, c in enumerate(row) if c is not None and COLHDR_RE.search(str(c))]
                if cols:
                    target_cols = cols
                    continue
            else:
                for i in target_cols:
                    if i < len(row) and row[i] is not None:
                        s = str(row[i]).strip().replace('.0', '') if isinstance(row[i], float) else str(row[i]).strip()
                        if CODE_RE.match(s): codes.add(s)
    wb.close()
    return codes

def main():
    reg = json.load(open(REG))
    cand = [r for r in reg['R'] if r.get('s') == 'r' and re.search(r'\.xlsx?$', r['u'], re.I) and LISTA_RE.search(r['n'])]
    print('candidatos (listados de predios):', len(cand))
    L = []      # leyenda de listas
    C = {}      # csg -> [ids de lista]
    for r in cand:
        url = r['u']
        try:
            resp = S.get(url, timeout=120)
            if resp.status_code != 200 or not resp.content: 
                print('  skip', resp.status_code, r['n'][:50]); continue
            if not url.lower().endswith('.xlsx'):
                print('  (no xlsx, omito)', r['n'][:50]); continue
            codes = parse_xlsx(resp.content)
        except Exception as e:
            print('  err', r['n'][:50], str(e)[:60]); continue
        if not codes:
            print('  0 códigos', r['n'][:55]); continue
        lid = len(L)
        L.append({'id': lid, 't': r['n'][:120], 'mk': pick(r['n'], MERCADOS), 'sp': pick(r['n'], ESPECIES), 'f': r.get('f', ''), 'u': url})
        for c in codes:
            C.setdefault(c, [])
            if lid not in C[c]: C[c].append(lid)
        print('  ok %4d códigos · %s' % (len(codes), r['n'][:55]), flush=True)
        time.sleep(0.3)
    print('listas con datos:', len(L), '· códigos únicos:', len(C))
    if len(C) < 50:
        print('ERROR: muy pocos códigos (%d); no se reemplaza.' % len(C)); raise SystemExit(1)
    data = {'rev': datetime.date.today().strftime('%d-%m-%Y'), 'nL': len(L), 'nC': len(C), 'L': L, 'C': C}
    json.dump(data, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    print('predios_listas.json:', len(L), 'listas ·', len(C), 'códigos ·', round(os.path.getsize(OUT)/1024), 'KB')

if __name__ == '__main__':
    main()
