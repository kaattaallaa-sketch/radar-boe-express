import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TZ = ZoneInfo("Europe/Madrid")
HEADERS = {"Accept": "application/json", "User-Agent": "Radar-BOE-Express/1.0"}
API = "https://www.boe.es/datosabiertos/api/boe/sumario/{date}"


def flatten(node):
    if isinstance(node, dict):
        if "identificador" in node and "titulo" in node:
            yield node
        for value in node.values():
            yield from flatten(value)
    elif isinstance(node, list):
        for value in node:
            yield from flatten(value)

def latest_payload(session):
    today = datetime.now(TZ).date()
    last_error = None
    for offset in range(5):
        day = today - timedelta(days=offset)
        date_key = day.strftime("%Y%m%d")
        response = session.get(API.format(date=date_key), headers=HEADERS, timeout=(5, 20))
        if response.status_code == 200:
            payload = response.json()
            if payload.get("status", {}).get("code") == "200":
                return date_key, payload
        last_error = f"{date_key}: HTTP {response.status_code}"
    raise RuntimeError(f"No BOE publication found in last 5 days; last={last_error}")


def clean_page(session, url):
    response = session.get(url, timeout=(5, 20))
    response.raise_for_status()
    stripped = re.sub(r"<[^>]+>", " ", response.text)
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()


def parse_euros(text):
    match = re.search(r"Valor estimado:\s*([\d\.]+,\d{2}) euros", text, re.I)
    return float(match.group(1).replace(".", "").replace(",", ".")) if match else None

def parse_deadline(text):
    match = re.search(
        r"Plazo para la recepci[oó]n de ofertas[^:]*:\s*(.*?)(?=\.\s*20\.|\.\s*21\.|$)",
        text,
        re.I,
    )
    return match.group(1).strip() if match else None


def collect():
    with requests.Session() as session:
        date_key, payload = latest_payload(session)
        rows = []
        for item in flatten(payload):
            title = item.get("titulo", "")
            if "Anuncio de licitaci" not in title:
                continue
            url = item.get("url_html")
            if not url:
                continue
            text = clean_page(session, url)
            rows.append({
                "id": item["identificador"],
                "title": title,
                "url": url,
                "value_eur": parse_euros(text),
                "deadline": parse_deadline(text),
            })
    rows.sort(key=lambda row: row["value_eur"] or 0, reverse=True)
    return date_key, rows

def fmt_eur(value):
    if value is None:
        return "No indicado"
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def render(date_key, rows):
    generated = datetime.now(TZ).strftime("%d/%m/%Y %H:%M %Z")
    body = []
    sample = rows[:3]
    for row in sample:
        body.append(
            "<tr>"
            f"<td>{html.escape(row['id'])}</td>"
            f"<td>{html.escape(row['title'])}</td>"
            f"<td>{html.escape(fmt_eur(row['value_eur']))}</td>"
            f"<td>{html.escape(row['deadline'] or 'No extraído')}</td>"
            f"<td><a href=\"{html.escape(row['url'])}\">BOE</a></td>"
            "</tr>"
        )
    rows_html = "\n".join(body) or "<tr><td colspan='5'>Sin licitaciones detectadas.</td></tr>"
    return f"""<!doctype html><html lang='es'><meta charset='utf-8'>
<title>Últimas licitaciones | Radar BOE Express</title>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<h1>Últimas licitaciones detectadas</h1>
<p>Edición BOE: <b>{date_key}</b>. Actualizado: {generated}. Total: <b>{len(rows)}</b>.</p>
<p><a href='index.html'>← Volver a Radar BOE Express</a></p>
<table border='1' cellspacing='0' cellpadding='6'><thead><tr><th>Referencia</th><th>Objeto</th><th>Valor estimado</th><th>Plazo</th><th>Fuente</th></tr></thead><tbody>{rows_html}</tbody></table>
<p><small>Fuente oficial: Agencia Estatal BOE. Verifica siempre los pliegos oficiales antes de actuar.</small></p></html>"""

def main():
    date_key, rows = collect()
    DATA_DIR.mkdir(exist_ok=True)
    known = [row for row in rows if row["value_eur"] is not None]
    payload = {
        "boe_date": date_key,
        "generated_at": datetime.now(TZ).isoformat(),
        "count": len(rows),
        "known_value_count": len(known),
        "total_value_eur": sum(row["value_eur"] for row in known),
        "deadline_count": sum(bool(row["deadline"]) for row in rows),
        "items": rows[:3],
    }
    (DATA_DIR / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "latest.html").write_text(render(date_key, rows), encoding="utf-8")
    print(json.dumps({"boe_date": date_key, "count": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
