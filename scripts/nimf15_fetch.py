#!/usr/bin/env python3
# Baja el Excel "Terceros Autorizados para tratamientos de embalajes de madera (NIMF 15)" del SAG
# y arma nimf15.json (registro público de empresas; sin datos personales). Corre en GitHub Actions.
import os, re, io, json, datetime
import requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'nimf15.json')
PAGE = 'https://www.sag.gob.cl/content/terceros-autorizados-para-la-ejecucion-de-tratamientos-embalajes-de-madera-de-exportacion'
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (SAG NIMF15)'})

def find_excel():
    # ubicar el .xlsx vigente desde la página (por si cambia el nombre)
    try:
        html = S.get(PAGE, timeout=90).text
        m = re.findall(r'(/sites/default/files/[^"\')>]+\.xlsx)', html, re.I)
        if m:
            u = m[0]
            return 'https://www.sag.gob.cl' + u, html
    except Exception as e:
        print('aviso: no pude leer la página:', e)
    return 'https://www.sag.gob.cl/sites/default/files/NIMF15%20listado%20web%20forestal%20%284%29_0.xlsx', ''

# palabras clave de columnas (sin datos personales: se descartan cédula/representante/responsable/contacto/correo/telefono)
COLS = [
 ('cod', r'c[oó]digo|n[°º]\s*autoriz|n[°º]\s*empresa|n[°º]\s*registro|^n[°º]$|autorizaci[oó]n|marca'),
 ('emp', r'raz[oó]n\s*social|empresa|nombre\s*(de\s*la\s*)?empresa'),
 ('rut', r'\brut\b'),
 ('trat', r'tratamiento|t[eé]cnica|medida|ht|bromuro'),
 ('reg', r'regi[oó]n'),
 ('com', r'comuna'),
 ('dir', r'direcci[oó]n|domicilio|ubicaci[oó]n'),
 ('vig', r'vigenc|vencimiento|fecha\s*de\s*t[eé]rmino|hasta|caduc'),
 ('res', r'resoluci[oó]n|res\.'),
]
SKIP = re.compile(r'c[eé]dula|\bc\.?i\.?\b|representante|responsable|contacto|correo|e-?mail|tel[eé]fono|celular|nombre\s*(del\s*)?(representante|responsable|t[eé]cnico|profesional)', re.I)

def main():
    url, _ = find_excel()
    print('Excel:', url)
    r = S.get(url, timeout=120)
    if r.status_code != 200 or not r.content:
        print('ERROR: no pude bajar el Excel (HTTP %s)' % r.status_code); raise SystemExit(1)
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = [[('' if c is None else str(c).strip()) for c in row] for row in ws.iter_rows(values_only=True)]
    wb.close()
    # fila de encabezado = la primera con >=3 celdas no vacías que parezca títulos
    hdr_i = 0
    for i, row in enumerate(rows[:15]):
        joined = ' '.join(row).lower()
        if re.search(r'raz[oó]n|empresa|rut|tratamiento|regi[oó]n', joined) and len([c for c in row if c]) >= 3:
            hdr_i = i; break
    header = rows[hdr_i]
    print('ENCABEZADO (fila %d):' % hdr_i, header)
    # mapear columnas
    colmap = {}
    for idx, h in enumerate(header):
        hl = h.lower()
        if SKIP.search(hl): continue
        for key, pat in COLS:
            if key in colmap: continue
            if re.search(pat, hl, re.I): colmap[key] = idx; break
    print('MAPEO:', colmap)
    out = []
    for row in rows[hdr_i+1:]:
        if not any(row): continue
        rec = {}
        for key, idx in colmap.items():
            if idx < len(row) and row[idx]:
                rec[key] = re.sub(r'\s+', ' ', row[idx]).strip()[:120]
        # requiere al menos empresa o código
        if rec.get('emp') or rec.get('cod'):
            out.append(rec)
    print('FILAS:', len(out))
    for s in out[:4]: print('  ej:', json.dumps(s, ensure_ascii=False))
    if len(out) < 5:
        print('ERROR: muy pocas filas (%d); no se reemplaza.' % len(out)); raise SystemExit(1)
    data = {'rev': datetime.date.today().strftime('%d-%m-%Y'), 'file': url.split('/')[-1], 'url': url, 'n': len(out), 'R': out}
    json.dump(data, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    print('nimf15.json:', len(out), 'empresas ·', round(os.path.getsize(OUT)/1024), 'KB')

if __name__ == '__main__':
    main()
