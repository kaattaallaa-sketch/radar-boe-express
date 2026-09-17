import html
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from update_latest import API, HEADERS, flatten, get_with_retries, make_session

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sectores"
TZ = ZoneInfo("Europe/Madrid")
BASE = "https://kaattaallaa-sketch.github.io/radar-boe-express"
BUY_ONCE = "https://buy.stripe.com/cNi4gBfkz1X13BQcf5efC00"
BUY_MONTHLY = "https://buy.stripe.com/dRm00l5JZfNRfkyendefC01"

SECTORS = {
    "mantenimiento": ("Mantenimiento", r"\bmantenimiento\b"),
    "limpieza": ("Limpieza", r"\blimpieza\b"),
    "seguridad-privada": ("Vigilancia y seguridad privada", r"\bvigilancia\b"),
    "obras": ("Obras", r"\bobras?\b"),
}


def normalize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))

def collect_history(days=30):
    records = []
    publication_days = 0
    today = datetime.now(TZ).date()
    with make_session() as session:
        for offset in range(days):
            day = today - timedelta(days=offset)
            date_key = day.strftime("%Y%m%d")
            response = get_with_retries(session, API.format(date=date_key), headers=HEADERS)
            if response.status_code != 200:
                continue
            payload = response.json()
            if payload.get("status", {}).get("code") != "200":
                continue
            publication_days += 1
            for item in flatten(payload):
                title = item.get("titulo", "")
                if "Anuncio de licitaci" not in title:
                    continue
                records.append({
                    "date": date_key,
                    "id": item.get("identificador", ""),
                    "title": title,
                    "url": item.get("url_html", ""),
                })
    return publication_days, records


def tracked(link, slug, plan):
    return f"{link}?client_reference_id=seo_{slug}_{plan}&utm_source=radar-boe&utm_medium=seo&utm_campaign={slug}&utm_content={plan}"

def render_page(slug, label, pattern, publication_days, records):
    matches = [r for r in records if re.search(pattern, normalize(r["title"]))]
    examples = matches[:6]
    rows = []
    for row in examples:
        pretty = f"{row['date'][6:8]}/{row['date'][4:6]}/{row['date'][:4]}"
        rows.append(
            "<li>"
            f"<strong>{html.escape(pretty)}</strong> — {html.escape(row['title'])} "
            f"<a href=\"{html.escape(row['url'])}\" rel=\"noopener\">BOE</a>"
            "</li>"
        )
    examples_html = "\n".join(rows) or "<li>Sin coincidencias en la ventana actual.</li>"
    once = html.escape(tracked(BUY_ONCE, slug, "single"), quote=True)
    monthly = html.escape(tracked(BUY_MONTHLY, slug, "monthly"), quote=True)
    updated = datetime.now(TZ).strftime("%d/%m/%Y")
    page = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Licitaciones de {html.escape(label)} | Radar BOE Express</title>
<meta name='description' content='Radar de licitaciones de {html.escape(label)} publicadas en el BOE. Ejemplos recientes y filtrado sectorial.'>
<link rel='canonical' href='{BASE}/sectores/{slug}.html'>
<style>body{{font-family:system-ui;max-width:860px;margin:40px auto;padding:0 20px;line-height:1.55;color:#171717}}a{{color:#174ea6}}.cta{{display:inline-block;background:#111;color:white;padding:12px 16px;border-radius:8px;text-decoration:none;margin:4px}}.box{{padding:18px;border:1px solid #ddd;border-radius:12px;background:#fafafa}}li{{margin:10px 0}}</style></head><body>
"""
    page += f"""<p><a href='../index.html'>← Radar BOE Express</a></p>
<h1>Licitaciones de {html.escape(label)}</h1>
<p>Monitorizamos anuncios de licitación del BOE y destacamos coincidencias relacionadas con {html.escape(label.lower())}.</p>
<div class='box'><strong>{len(matches)} coincidencias textuales</strong> detectadas en los últimos 30 días naturales, sobre {publication_days} días con publicación BOE. Actualizado: {updated}.</div>
<h2>Ejemplos recientes</h2><ul>{examples_html}</ul>
<p>La coincidencia se calcula sobre el título/objeto del anuncio; no sustituye la revisión de pliegos ni garantiza que la licitación encaje con una empresa concreta.</p>
<h2>Filtrado a medida</h2>
<p>Indica sector, zona y palabras clave para recibir una selección más precisa.</p>
<p><a class='cta' href='{once}'>Informe sectorial · 9 € IVA incl.</a><a class='cta' href='{monthly}'>Radar · 19 €/mes IVA incl.</a></p>
<p><small><a href='../condiciones.html'>Condiciones</a> · <a href='../privacidad.html'>Privacidad</a> · <a href='../aviso-legal.html'>Aviso legal</a></small></p>
</body></html>"""
    return page


def write_sitemap():
    today = datetime.now(TZ).date().isoformat()
    paths = ["", "latest.html", "aviso-legal.html", "privacidad.html", "condiciones.html", "desistimiento.html"]
    paths += [f"sectores/{slug}.html" for slug in SECTORS]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines += [f"  <url><loc>{BASE}/{path}</loc><lastmod>{today}</lastmod></url>" for path in paths]
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    publication_days, records = collect_history(30)
    OUT.mkdir(exist_ok=True)
    summary = {}
    for slug, (label, pattern) in SECTORS.items():
        page = render_page(slug, label, pattern, publication_days, records)
        (OUT / f"{slug}.html").write_text(page, encoding="utf-8")
        summary[slug] = len([r for r in records if re.search(pattern, normalize(r["title"]))])
    write_sitemap()
    print({"publication_days": publication_days, "tenders": len(records), "sectors": summary})


if __name__ == "__main__":
    main()
