import argparse
import html
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import requests

from update_latest import TZ, clean_page, collect, fmt_eur

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paid_reports"


def normalize(value):
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in value if not unicodedata.combining(c)).lower()


def make_terms(sector, zone, keywords):
    raw = [sector, zone] + re.split(r"[,;]", keywords or "")
    terms = []
    for item in raw:
        item = normalize(item).strip()
        if item and item not in terms:
            terms.append(item)
    return terms


def slugify(value):
    value = re.sub(r"[^a-z0-9]+", "-", normalize(value)).strip("-")
    return value[:50] or "radar"

def rank_rows(rows, terms, required_terms=None):
    ranked = []
    with requests.Session() as session:
        for row in rows:
            text = clean_page(session, row["url"])
            title_text = normalize(row["title"])
            page_text = normalize(text)
            matched_title = [term for term in terms if term in title_text]
            matched = [term for term in terms if term in page_text or term in title_text]
            if not matched:
                continue
            if required_terms and not any(term in page_text or term in title_text for term in required_terms):
                continue
            score = sum(5 * title_text.count(term) + page_text.count(term) for term in matched)
            if not matched_title and len(matched) < 2 and score < 6:
                continue
            item = dict(row)
            item["score"] = score
            item["matched_terms"] = matched
            ranked.append(item)
    ranked.sort(key=lambda x: (x["score"], x["value_eur"] or 0), reverse=True)
    return ranked


def render(date_key, rows, sector, zone, keywords):
    generated = datetime.now(TZ).strftime("%d/%m/%Y %H:%M %Z")
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(row['title'])}</td>"
            f"<td>{html.escape(fmt_eur(row['value_eur']))}</td>"
            f"<td>{html.escape(row['deadline'] or 'No extraído')}</td>"
            f"<td>{html.escape(', '.join(row['matched_terms']))}</td>"
            f"<td><a href=\"{html.escape(row['url'])}\">BOE</a></td>"
            "</tr>"
        )
    rows_html = "\n".join(body) or "<tr><td colspan='5'>Sin coincidencias para estos criterios.</td></tr>"
    return f"""<!doctype html><html lang='es'><meta charset='utf-8'>
<title>Radar BOE sectorial</title><meta name='viewport' content='width=device-width,initial-scale=1'>
<h1>Radar BOE sectorial</h1>
<p><b>Edición BOE:</b> {date_key} · <b>Generado:</b> {generated}</p>
<p><b>Sector:</b> {html.escape(sector or '—')} · <b>Zona:</b> {html.escape(zone or '—')} · <b>Keywords:</b> {html.escape(keywords or '—')}</p>
<p><b>Coincidencias:</b> {len(rows)}</p>
<table border='1' cellspacing='0' cellpadding='6'><thead><tr><th>Oportunidad</th><th>Valor estimado</th><th>Plazo</th><th>Coincidencias</th><th>Fuente</th></tr></thead><tbody>{rows_html}</tbody></table>
<p><small>Servicio independiente. Verifica siempre los pliegos y requisitos en las fuentes oficiales antes de actuar.</small></p></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sector", required=True)
    parser.add_argument("--zona", default="")
    parser.add_argument("--keywords", default="")
    args = parser.parse_args()
    terms = make_terms(args.sector, args.zona, args.keywords)
    keyword_terms = make_terms("", "", args.keywords)
    date_key, rows = collect()
    ranked = rank_rows(rows, terms, keyword_terms)
    OUT.mkdir(exist_ok=True)
    stem = f"{date_key}-{slugify(args.sector)}"
    payload = {"boe_date": date_key, "sector": args.sector, "zona": args.zona, "keywords": args.keywords, "count": len(ranked), "items": ranked}
    (OUT / f"{stem}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"{stem}.html").write_text(render(date_key, ranked, args.sector, args.zona, args.keywords), encoding="utf-8")
    print(json.dumps({"boe_date": date_key, "count": len(ranked), "html": str(OUT / f'{stem}.html')}, ensure_ascii=False))


if __name__ == "__main__":
    main()