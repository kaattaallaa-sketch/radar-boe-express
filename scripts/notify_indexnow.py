import time

import requests

HOST = "kaattaallaa-sketch.github.io"
BASE = f"https://{HOST}/radar-boe-express"
KEY = "a20f9fcd4c64468dac510447ca05affb"
KEY_LOCATION = f"{BASE}/{KEY}.txt"
URLS = [
    f"{BASE}/",
    f"{BASE}/latest.html",
    f"{BASE}/sectores/mantenimiento.html",
    f"{BASE}/sectores/limpieza.html",
    f"{BASE}/sectores/seguridad-privada.html",
    f"{BASE}/sectores/obras.html",
]


def wait_until_public(session, attempts=24, pause=5):
    for attempt in range(1, attempts + 1):
        statuses = {}
        for url in URLS:
            try:
                statuses[url] = session.get(url, timeout=(5, 15)).status_code
            except requests.RequestException:
                statuses[url] = None
        if all(status == 200 for status in statuses.values()):
            print({"public": True, "attempt": attempt, "urls": len(URLS)})
            return
        if attempt < attempts:
            time.sleep(pause)
    raise RuntimeError(f"Pages not public after {attempts} attempts: {statuses}")


def main():
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": URLS,
    }
    with requests.Session() as session:
        wait_until_public(session)
        response = session.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            timeout=(5, 20),
        )
        print({"indexnow_status": response.status_code, "urls": len(URLS)})
        response.raise_for_status()


if __name__ == "__main__":
    main()
