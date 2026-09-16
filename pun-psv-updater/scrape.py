#!/usr/bin/env python3
"""
Aggiorna data.json con i valori PUN e PSV di oggi, ricavati da pagine
pubbliche che elaborano i dati ufficiali GME (Gestore dei Mercati Energetici).

Se una delle due estrazioni fallisce (il sito sorgente ha cambiato formato),
lo script mantiene il valore precedente gia' presente in data.json invece di
sovrascriverlo con un dato mancante o rotto.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
import urllib.request

DATA_FILE = Path(__file__).parent / "data.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VenchiPunPsvBot/1.0)"}

MESI = ["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio",
        "agosto","settembre","ottobre","novembre","dicembre"]
MESI_BREVI = ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"]


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def strip_tags(html):
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def to_float(s):
    return float(s.replace(".", "").replace(",", "."))


def scrape_pun():
    """Ritorna (oggi, mensile) in EUR/kWh dalla pagina Quifinanza sul PUN."""
    html = fetch("https://quifinanza.it/osservatorio-prezzi/prezzo-pun-luce-oggi/919954/")
    text = strip_tags(html)

    m_oggi = re.search(r"si attesta a\s*([\d.,]+)\s*€/kWh", text)
    m_mensile = re.search(r"valore medio mensile di[^(]*\(([\d.,]+)\s*€/kWh\)", text)

    oggi = to_float(m_oggi.group(1)) if m_oggi else None
    mensile = to_float(m_mensile.group(1)) if m_mensile else None
    return oggi, mensile


def scrape_psv():
    """Ritorna (oggi, mensile) in EUR/Smc dalla pagina bolletta-energia.it sul PSV."""
    html = fetch("https://bolletta-energia.it/gas/psv")
    text = strip_tags(html)

    m_oggi = re.search(r"PSV è pari a\s*([\d.,]+)\s*€/Smc", text)
    m_mensile = re.search(r"media mensile di\s*([\d.,]+)\s*€/Smc", text)

    oggi = to_float(m_oggi.group(1)) if m_oggi else None
    mensile = to_float(m_mensile.group(1)) if m_mensile else None
    return oggi, mensile


def load_existing():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return None


def main():
    existing = load_existing()
    today = datetime.now()
    updated_str = today.strftime("%d/%m/%Y")

    try:
        pun_oggi, pun_mensile = scrape_pun()
    except Exception as e:
        print("Errore scraping PUN:", e, file=sys.stderr)
        pun_oggi = pun_mensile = None

    try:
        psv_oggi, psv_mensile = scrape_psv()
    except Exception as e:
        print("Errore scraping PSV:", e, file=sys.stderr)
        psv_oggi = psv_mensile = None

    # Fallback sui valori precedenti se lo scraping fallisce
    prev = existing or {}
    prev_pun = prev.get("pun", {})
    prev_psv = prev.get("psv", {})

    if pun_oggi is None:
        pun_oggi = prev_pun.get("oggi")
    if pun_mensile is None:
        pun_mensile = prev_pun.get("mensile")
    if psv_oggi is None:
        psv_oggi = prev_psv.get("oggi")
    if psv_mensile is None:
        psv_mensile = prev_psv.get("mensile")

    if None in (pun_oggi, pun_mensile, psv_oggi, psv_mensile):
        print("Impossibile ottenere tutti i valori e nessun dato precedente disponibile.", file=sys.stderr)
        sys.exit(1)

    # Gestione dello storico mensile: aggiorna il mese corrente nell'array
    months = prev.get("months") or [
        {"m": "Gen", "pun": 0.133, "psv": 0.404},
        {"m": "Feb", "pun": 0.114, "psv": 0.373},
        {"m": "Mar", "pun": 0.143, "psv": 0.568},
        {"m": "Apr", "pun": 0.119, "psv": 0.492},
        {"m": "Mag", "pun": 0.119, "psv": 0.504},
        {"m": "Giu", "pun": 0.124, "psv": 0.504},
        {"m": "Lug", "pun": 0.157, "psv": 0.606},
        {"m": "Ago", "pun": 0.180, "psv": 0.689},
    ]
    current_label = MESI_BREVI[today.month - 1]
    if months and months[-1]["m"] == current_label:
        months[-1] = {"m": current_label, "pun": round(pun_mensile, 3), "psv": round(psv_mensile, 3)}
    elif len(months) < 12:
        months.append({"m": current_label, "pun": round(pun_mensile, 3), "psv": round(psv_mensile, 3)})
    else:
        months = months[1:] + [{"m": current_label, "pun": round(pun_mensile, 3), "psv": round(psv_mensile, 3)}]

    # Variazione % rispetto al mese precedente nello storico
    def pct_change(vals, key):
        if len(vals) < 2:
            return 0.0, 0.0
        cur, prev_v = vals[-1][key], vals[-2][key]
        return round(cur - prev_v, 5), round((cur - prev_v) / prev_v * 100, 1) if prev_v else 0.0

    pun_delta_abs, pun_delta_pct = pct_change(months, "pun")
    psv_delta_abs, psv_delta_pct = pct_change(months, "psv")

    data = {
        "updated": updated_str,
        "pun": {
            "oggi": round(pun_oggi, 5),
            "mensile": round(pun_mensile, 5),
            "deltaAbs": pun_delta_abs,
            "deltaPct": pun_delta_pct,
        },
        "psv": {
            "oggi": round(psv_oggi, 5),
            "mensile": round(psv_mensile, 5),
            "deltaAbs": psv_delta_abs,
            "deltaPct": psv_delta_pct,
        },
        "months": months,
    }

    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print("data.json aggiornato:", data["updated"])


if __name__ == "__main__":
    main()
