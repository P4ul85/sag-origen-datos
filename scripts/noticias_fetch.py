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
UA = {"User-Agent": "Mozilla/5.0 (compatible; SAG-Origen-news/1.0)"}

# (nombre de la fuente, URL del feed RSS)
FEEDS = [
    ("Portal Frutícola", "https://www.portalfruticola.com/feed/"),
    ("Simfruit",         "https://www.simfruit.cl/feed/"),
    ("Frutas de Chile",  "https://www.frutasdechile.cl/feed/"),
    ("Redagrícola",      "https://www.redagricola.com/cl/feed/"),
]
PER_FEED = 8          # noticias por fuente
MAX_TOTAL = 40        # total en el carrusel
MIN_OK = 6            # salvaguarda: no publicar si quedan menos que esto

def clean(txt, n=180):
    if not txt:
        return ""
    txt = BeautifulSoup(html.unescape(txt), "html.parser").get_text(" ", strip=True)
    txt = re.sub(r"\s+", " ", txt).strip()
    return (txt[:n].rstrip() + "…") if len(txt) > n else txt

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
    items, seen = [], set()
    for src, url in FEEDS:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            d = feedparser.parse(r.content)
        except Exception as ex:
            print(f"  ! {src}: {ex}")
            continue
        n = 0
        for e in d.entries:
            link = (e.get("link") or "").strip()
            title = clean(e.get("title"), 140)
            if not link or not title or link in seen:
                continue
            img = img_from_entry(e)
            if not img:
                img = og_image(link)
            items.append({
                "t": title,
                "d": clean(e.get("summary"), 170),
                "u": link,
                "img": img,
                "src": src,
                "f": date_iso(e),
            })
            seen.add(link)
            n += 1
            if n >= PER_FEED:
                break
        print(f"  {src}: {n} noticias")

    # ordenar por fecha desc y recortar
    items.sort(key=lambda x: x["f"] or "", reverse=True)
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
