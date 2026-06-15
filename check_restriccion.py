#!/usr/bin/env python3
"""
Alerta de restriccion vehicular por preemergencia / emergencia ambiental (RM).
Uso personal. Avisa por Telegram y publica un status.json para el dashboard web.

Flujo:
  1. Lee la ultima noticia de Aire RM (MMA) via WordPress REST API.
  2. Detecta nivel (PREEMERGENCIA/EMERGENCIA/ALERTA), fecha y digitos de
     "Transporte de carga (incluye camionetas)" -> CON SELLO VERDE.
  3. Decide si hay restriccion de carga c/sello verde para hoy o manana.
  4. Escribe data/status.json (lo lee el dashboard) y, si corresponde, avisa por
     Telegram y agrega el episodio a data/history.json (esto tambien deduplica).
"""

import os
import re
import sys
import json
import html
import datetime as dt
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

WP_API = "https://airerm.mma.gob.cl/wp-json/wp/v2/posts"
TZ = ZoneInfo("America/Santiago")
DATA_DIR = os.environ.get("DATA_DIR", "data")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# --- Parsing -----------------------------------------------------------------
def to_text(raw_html: str) -> str:
    soup = BeautifulSoup(html.unescape(raw_html or ""), "html.parser")
    return soup.get_text(separator=" ", strip=True)


def detect_level(title: str, body: str) -> str | None:
    for source in (title, body):
        low = source.lower()
        if "preemergencia" in low:
            return "PREEMERGENCIA"
        if "emergencia" in low:
            return "EMERGENCIA"
        if "alerta" in low:
            return "ALERTA"
    return None


def detect_date(text: str, default_year: int) -> dt.date | None:
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéí]+)(?:\s+de\s+(\d{4}))?", text, re.IGNORECASE)
    if not m:
        return None
    day, month = int(m.group(1)), MESES.get(m.group(2).lower())
    if not month:
        return None
    year = int(m.group(3)) if m.group(3) else default_year
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def extract_carga_sello_verde(text: str) -> str | None:
    """Digitos de carga CON sello verde, ej '2-3'; None si 'no hay' o ausente.

    Soporta los dos formatos reales de airerm:
      - Prosa:  '...Transporte de Carga Con Sello Verde ... que terminan en 2 y 3.'
      - Tabla:  'Transporte de carga (incluye camionetas) ... Con Sello Verde: 4-5'
    """
    low = text.lower()

    # 1) Formato en prosa (el que usan las noticias de preemergencia).
    m = re.search(r"transporte de carga con sello verde", low)
    if m:
        window = low[m.end(): m.end() + 300]
        if "no hay" in window[:60]:
            return None
        m2 = re.search(r"termin[a-z]*\s+en\s+([0-9][0-9\s,yo\-]*)", window)
        if m2:
            digits = re.findall(r"\d", m2.group(1))
            if digits:
                return "-".join(digits)

    # 2) Formato en tabla (bloque de carga, sin confundir con automoviles).
    idx = low.find("transporte de carga")
    if idx != -1:
        chunk = low[idx: idx + 400]
        m3 = re.search(r"con sello verde:\s*(no hay|[\d\-\s]+)", chunk)
        if m3 and "no hay" not in m3.group(1):
            digits = re.findall(r"\d", m3.group(1))
            if digits:
                return "-".join(digits)
    return None


def parse_post(post: dict) -> dict:
    title = to_text(post.get("title", {}).get("rendered", ""))
    body = to_text(post.get("content", {}).get("rendered", ""))
    year = dt.datetime.now(TZ).year
    return {
        "level": detect_level(title, body),
        "date": detect_date(title, year) or detect_date(body, year),
        "carga_sv": extract_carga_sello_verde(f"{title} . {body}"),
        "link": post.get("link", "https://airerm.mma.gob.cl/noticias/"),
    }


# --- Decision (pura, testeable sin red) --------------------------------------
def compute_status(ep: dict | None, today: dt.date) -> dict:
    """Construye el payload de status.json a partir del episodio parseado."""
    now_iso = dt.datetime.now(TZ).replace(microsecond=0).isoformat()
    base = {"updated_at": now_iso, "restricted": False, "level": None,
            "date": None, "carga_sello_verde": None,
            "link": "https://airerm.mma.gob.cl/noticias/"}
    if not ep:
        return base

    aplica = ep["date"] in (today, today + dt.timedelta(days=1)) if ep["date"] else False
    restricted = bool(
        ep["level"] in ("PREEMERGENCIA", "EMERGENCIA") and ep["carga_sv"] and aplica
    )
    base.update({
        "restricted": restricted,
        "level": ep["level"] if aplica else None,
        "date": ep["date"].isoformat() if ep["date"] and aplica else None,
        "carga_sello_verde": ep["carga_sv"] if aplica else None,
        "link": ep["link"],
    })
    return base


# --- IO ----------------------------------------------------------------------
def fetch_latest_episode() -> dict | None:
    r = requests.get(WP_API, params={"per_page": 6, "_fields": "title,content,date,link"},
                     timeout=20, headers={"User-Agent": "restriccion-mvp/1.0"})
    r.raise_for_status()
    for post in r.json():
        t = to_text(post.get("title", {}).get("rendered", "")).lower()
        if "ambiental" in t or "preemergencia" in t or "emergencia" in t:
            return parse_post(post)
    return None


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_telegram(text: str) -> None:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("[WARN] Faltan TELEGRAM_TOKEN/CHAT_ID; no se envia. Mensaje:\n", text)
        return
    r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=20)
    print(f"[INFO] Telegram status={r.status_code}")


def build_message(status: dict) -> str:
    return (
        f"\u26a0\ufe0f {status['level']} AMBIENTAL para el {status['date']}.\n"
        f"Carga CON sello verde no circula si tu patente termina en: {status['carga_sello_verde']}.\n"
        f"Horario 10:00-18:00, interior Anillo Americo Vespucio.\n"
        f"Detalle: {status['link']}"
    )


# --- Main --------------------------------------------------------------------
def main() -> int:
    today = dt.datetime.now(TZ).date()
    ep = fetch_latest_episode()
    status = compute_status(ep, today)
    save_json(STATUS_FILE, status)
    print(f"[INFO] status: restricted={status['restricted']} level={status['level']} "
          f"date={status['date']} carga_sv={status['carga_sello_verde']}")

    if not status["restricted"]:
        return 0

    key = f"{status['date']}|{status['level']}|{status['carga_sello_verde']}"
    history = load_json(HISTORY_FILE, [])
    if any(h.get("key") == key for h in history):
        print("[INFO] Episodio ya avisado. Skip Telegram.")
        return 0

    send_telegram(build_message(status))
    history.insert(0, {
        "key": key, "date": status["date"], "level": status["level"],
        "carga_sello_verde": status["carga_sello_verde"],
        "alerted_at": status["updated_at"],
    })
    save_json(HISTORY_FILE, history[:60])  # ultimos 60
    print("[OK] Aviso enviado y registrado en historial.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
