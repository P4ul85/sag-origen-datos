#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
noticias_fetch.py — recolecta noticias del mundo exportador/agrícola (prensa) con
título, resumen corto, imagen (miniatura) y enlace, para el carrusel del inicio de la app.

Fuentes: feeds RSS de prensa frutícola/agrícola chilena. Solo titular + resumen breve +
miniatura + enlace a la fuente (agregación tipo titulares, no reproduce el artículo).
Las imágenes se enlazan desde la fuente (no se descargan).

Salida: noticias.json = {rev, n, N:[{t,d,u,img,src,f}]} en el repo público.
Corre por GitHub Actions (el runner sí alcanza estos sitios). Uso: python3 scripts/noticias_fetch.py
"""
import json, os, re, sys, datetime, html
import requests, feedparser
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "noticias.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/rss+xml, application/xml, text/xml, */*"}

# (nombre, URL del feed RSS, ag)  ag=True → portal agrícola (se incluye todo);
# ag=False → prensa general/nacional/regional (se filtra por palabras clave agro/exportación)
FEEDS = [
    # Portales agrícolas / frutícolas (todo)
    ("Portal Frutícola", "https://www.portalfruticola.com/feed/", True),
    ("Simfruit",         "https://www.simfruit.cl/feed/", True),
    ("Frutas de Chile",  "https://www.frutasdechile.cl/feed/", True),
    ("Redagrícola",      "https://www.redagricola.com/feed/", True),
    ("Mundoagro",        "https://www.mundoagro.cl/feed/", True),
    ("Agronomía INIA",   "https://www.inia.cl/feed/", True),
    # Prensa nacional (se filtra por relevancia agro/exportación)
    ("El Mostrador",     "https://www.elmostrador.cl/feed/", False),
    ("BioBioChile · Economía", "https://www.biobiochile.cl/lista/categorias/economia/feed", False),
    ("La Tercera",       "https://www.latercera.com/feed/", False),
    ("El Dínamo",        "https://www.eldinamo.cl/feed/", False),
    ("ADN Radio",        "https://www.adnradio.cl/feed/", False),
    ("Emol · Economía",  "https://www.emol.com/rss/rss.asp?canal=economia", False),
    ("Cooperativa · Economía", "https://www.cooperativa.cl/noticias/site/edic/base/port/rss_economia.xml", False),
    # Prensa regional (Arica a Punta Arenas; se filtra por relevancia agro/exportación)
    ("Diario de Antofagasta", "https://www.diarioantofagasta.cl/feed/", False),
    ("El Día (Coquimbo)", "https://www.diarioeldia.cl/feed/", False),
    ("El Ovallino (Coquimbo)", "https://www.elovallino.cl/feed/", False),
    ("El Observador (Quillota)", "https://www.observador.cl/feed/", False),
    ("El Rancagüino (O'Higgins)", "https://www.elrancaguino.cl/feed/", False),
    ("El Tipógrafo (O'Higgins)", "https://eltipografo.cl/feed/", False),
    ("Diario El Centro (Maule)", "https://diarioelcentro.cl/feed/", False),
    ("La Discusión (Ñuble)", "https://www.ladiscusion.cl/feed/", False),
    ("Crónica Chillán (Ñuble)", "https://www.cronicachillan.cl/feed/", False),
    ("Diario Concepción", "https://www.diarioconcepcion.cl/feed/", False),
    ("La Prensa Austral (Magallanes)", "https://laprensaaustral.cl/feed/", False),
]
PER_FEED = 6          # noticias por fuente (variedad entre diarios)
MAX_TOTAL = 40        # total en el carrusel
MIN_OK = 6            # salvaguarda: no publicar si quedan menos que esto
MAX_AGE_DAYS = 75     # descarta noticias más viejas que esto (si traen fecha)

# Palabras clave (sin tildes) para dejar solo prensa general relevante al agro/exportación
KW = ("frut","agric","agro","export","hortal","palta","cereza","uva","arandano","manzana",
      "kiwi","ciruela","durazno","nectarin","pera","citric","naranja","limon","mandarina",
      "huerto","campo","cosecha","temporada","packing","exportador","fitosanit","sag ",
      " sag","aduana","puerto","embalaje","vino","vinedo","nuez","almendra","avellana",
      "berries","frambuesa","mosca de la fruta","lobesia","usda","aphis","arancel","inia",
      "odepa","asoex","fedefruta","riego","sequia","temporeros","packing","agroindustria")

def _norm(s):
    s = (s or "").lower()
    for a,b in (("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ü","u"),("ñ","n")):
        s = s.replace(a,b)
    return s

def is_relevant(title, summary):
    t = _norm(title + " " + summary)
    return any(k in t for k in KW)

def clean(txt, n=180):
    if not txt:
        return ""
    txt = BeautifulSoup(html.unescape(txt), "html.parser").get_text(" ", strip=True)
    txt = re.sub(r"\s+", " ", txt).strip()
    return (txt[:n].rstrip() + "…") if len(txt) > n else txt

def clean_title(t):
    t = clean(t, 150)
    if " | " in t:            # el pipe casi siempre separa el nombre de la fuente
        t = t.rsplit(" | ", 1)[0].strip()
    return t

def tkey(t):                  # clave para deduplicar la misma noticia entre diarios
    s = re.sub(r"[^a-z0-9 ]", "", _norm(t))
    return re.sub(r"\s+", " ", s).strip()[:60]

def ok_img(u):
    return isinstance(u, str) and u.startswith("http") and \
        not re.search(r"(placeholder|default|blank|spacer|1x1|sprite|avatar|logo)", u, re.I)

def fetch_feed(url):
    """Descarga el feed con un reintento para errores transitorios (p. ej. conexión
    cortada). NO desactiva la verificación TLS: si un sitio manda mal su certificado,
    se omite solo (que lo corrija la fuente)."""
    last = None
    for _ in range(2):
        try:
            r = requests.get(url, headers=UA, timeout=25)
            return feedparser.parse(r.content)
        except Exception as ex:
            last = ex
    raise last

def img_from_entry(e):
    # media:content / media:thumbnail
    for key in ("media_content", "media_thumbnail"):
        v = e.get(key)
        if v and isinstance(v, list) and v and v[0].get("url"):
            return v[0]["url"]
    # enclosures
    for enc in e.get("enclosures", []) or []:
        if "image" in (enc.get("type") or "") and enc.get("href"):
            return enc["href"]
    # primer <img> dentro del contenido/resumen
    body = ""
    if e.get("content"):
        body = e["content"][0].get("value", "")
    body = body or e.get("summary", "")
    m = re.search(r'<img[^>]+src="([^"]+)"', body or "")
    if m:
        return m.group(1)
    return ""

def og_image(url):
    try:
        r = requests.get(url, headers=UA, timeout=12)
        if r.status_code != 200:
            return ""
        s = BeautifulSoup(r.text, "html.parser")
        for prop in ("og:image", "twitter:image"):
            tag = s.find("meta", property=prop) or s.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                return tag["content"]
    except Exception:
        pass
    return ""

def date_iso(e):
    t = e.get("published_parsed") or e.get("updated_parsed")
    if t:
        return datetime.date(t.tm_year, t.tm_mon, t.tm_mday).isoformat()
    return ""

def main():
    items, seen, seen_t = [], set(), set()
    today = datetime.date.today()
    for src, url, ag in FEEDS:
        try:
            d = fetch_feed(url)
        except Exception as ex:
            print(f"  ! {src}: {ex}")
            continue
        n = 0
        for e in d.entries:
            link = (e.get("link") or "").strip()
            title = clean_title(e.get("title"))
            if not link or not title or link in seen:
                continue
            tk = tkey(title)
            if tk and tk in seen_t:        # misma noticia en otro diario
                continue
            summ = clean(e.get("summary"), 170)
            if not ag and not is_relevant(title, summ):
                continue
            f = date_iso(e)
            if f:                          # descarta lo viejo
                try:
                    if (today - datetime.date.fromisoformat(f)).days > MAX_AGE_DAYS:
                        continue
                except Exception:
                    pass
            img = img_from_entry(e)
            if not img:
                img = og_image(link)
            if not ok_img(img):
                img = ""
            items.append({"t": title, "d": summ, "u": link, "img": img, "src": src, "f": f})
            seen.add(link);
            if tk: seen_t.add(tk)
            n += 1
            if n >= PER_FEED:
                break
        print(f"  {src}: {n} noticias" + ("" if ag else " (filtrado agro)"))

    # ordenar: primero las que traen fecha (desc), luego el resto
    items.sort(key=lambda x: x["f"] or "0000-00-00", reverse=True)
    items = items[:MAX_TOTAL]

    if len(items) < MIN_OK:
        print(f"Solo {len(items)} noticias (<{MIN_OK}); no se actualiza para no dejar el carrusel vacío.")
        sys.exit(0 if os.path.exists(OUT) else 1)

    obj = {"rev": datetime.date.today().strftime("%d/%m/%Y"), "n": len(items), "N": items}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    con_img = sum(1 for x in items if x["img"])
    print(f"noticias.json: {len(items)} noticias ({con_img} con imagen)")

if __name__ == "__main__":
    main()
