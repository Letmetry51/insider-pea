"""
Euro Signal — TradingView (screener public, scanner.tradingview.com) : clôture du soir et F-score de Piotroski de chaque bourse.

Pourquoi (17/11/2026, sonde research/tradingview_probe.py lancée depuis GitHub Actions) :
- source indépendante de Yahoo pour les 15 bourses, en une requête par bourse (0,1 à 0,2 s chacune) ; seule source de secours
  pour l'Allemagne, l'Espagne, Vienne, Londres et Zurich si Yahoo coupe l'accès (les listes Euronext et Nasdaq Nordic ne les
  couvrent pas) ;
- F-score calculé par TradingView sur ses propres comptes : contrôle des comptes Yahoo (euro_signal/tv_check.py). Sur 1 176
  sociétés du classement : 38 % de F-scores identiques, 83 % à un point près, 34 écarts de 3 points ou plus.

Ce que l'outil en fait :
- cours : dernier secours de scrapers/backup_prices.py (après les listes des bourses et Yahoo titre par titre), cases vides
  seulement, avec les mêmes garde-fous (séance attendue, devise, fourchette ÷2 à ×2) ; volume jamais repris ;
- F-score : simple contrôle affiché dans l'onglet Aide, jamais utilisé par le classement (barème gelé jusqu'au 31/01/2027).

Format écrit (data/tradingview.json, fichier de travail jamais publié : supprimé à la publication comme data/prices.json) :
  {"date", "at", "places": {suffixe: {"rows", "session"}}, "errors": {suffixe: texte},
   "items": {symbole Yahoo: [séance, clôture, ouverture, plus haut, plus bas, devise, F-score, fin d'exercice]}}
Une bourse injoignable est notée dans « errors » sans faire échouer l'étape : l'outil tourne alors comme avant.

  python scrapers/tradingview.py
"""
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "tradingview.json"
URL = "https://scanner.tradingview.com/{}/scan"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Content-Type": "application/json", "Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"}
COLS = ["name", "close", "open", "high", "low", "currency", "daily-bar.time", "piotroski_f_score_fy", "fiscal_period_end_fy"]
# (marché TradingView, place TradingView, suffixe Yahoo, fuseau de la bourse) ; une requête par ligne
PLACES = (("france", "EURONEXT", "PA", "Europe/Paris"), ("netherlands", "EURONEXT", "AS", "Europe/Amsterdam"),
          ("belgium", "EURONEXT", "BR", "Europe/Brussels"), ("portugal", "EURONEXT", "LS", "Europe/Lisbon"),
          ("ireland", "EURONEXT", "IR", "Europe/Dublin"), ("italy", "MIL", "MI", "Europe/Rome"),
          ("spain", "BME", "MC", "Europe/Madrid"), ("germany", "XETR", "DE", "Europe/Berlin"),
          ("austria", "VIE", "VI", "Europe/Vienna"), ("switzerland", "SIX", "SW", "Europe/Zurich"),
          ("uk", "LSE", "L", "Europe/London"), ("sweden", "OMXSTO", "ST", "Europe/Stockholm"),
          ("finland", "OMXHEX", "HE", "Europe/Helsinki"), ("denmark", "OMXCOP", "CO", "Europe/Copenhagen"),
          ("norway", "OSL", "OL", "Europe/Oslo"))
CURRENCY = {"GBX": "GBp"}  # pence : notation Yahoo des fiches sociétés
MAX_ROWS = 5000


def log(*a):
    print(*a, flush=True)


def num(v):
    """Nombre fini strictement positif, sinon None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    x = float(v)
    return x if x > 0 and x != float("inf") else None


def day_of(ts, tz):
    """Horodatage de la barre du jour (secondes ou millisecondes depuis 1970) → date de la séance à l'heure de la bourse."""
    ts = num(ts)
    if ts is None:
        return None
    if ts > 1e12:
        ts /= 1000
    try:
        return datetime.fromtimestamp(ts, ZoneInfo(tz)).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def yahoo_symbol(name, suffix):
    """Symbole TradingView → symbole Yahoo : « BA. » → BA.L, « BT.A » → BT-A.L, « VOLV_B » → VOLV-B.ST, « NDA_FI » → NDA-FI.HE."""
    t = str(name or "").strip().upper()
    if suffix in ("L", "ST", "HE", "CO", "OL"):
        t = t.rstrip(".").replace("_", "-").replace(".", "-")
    return f"{t}.{suffix}" if t and suffix and " " not in t else None


def body(market, place, n=MAX_ROWS):
    return {"columns": COLS, "options": {"lang": "en"}, "markets": [market], "range": [0, n],
            "filter": [{"left": "type", "operation": "equal", "right": "stock"},
                       {"left": "exchange", "operation": "equal", "right": place}],
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}}


def parse(js, suffix, tz):
    """Réponse du screener → {symbole Yahoo : [séance, clôture, ouverture, haut, bas, devise, F-score, fin d'exercice]}.
    Ligne sans clôture ou sans date de séance : ignorée ; F-score hors de 0 à 9 : vide."""
    out = {}
    for row in (js or {}).get("data") or []:
        d = row.get("d") if isinstance(row, dict) else None
        if not isinstance(d, list) or len(d) != len(COLS):
            continue
        r = dict(zip(COLS, d))
        sym, day, close = yahoo_symbol(r["name"], suffix), day_of(r["daily-bar.time"], tz), num(r["close"])
        if not sym or not day or close is None or sym in out:
            continue
        f9 = r["piotroski_f_score_fy"]
        f9 = int(f9) if isinstance(f9, (int, float)) and not isinstance(f9, bool) and 0 <= f9 <= 9 and f9 == int(f9) else None
        cur = r["currency"] if isinstance(r["currency"], str) else None
        out[sym] = [day, close, num(r["open"]), num(r["high"]), num(r["low"]), CURRENCY.get(cur, cur), f9,
                    day_of(r["fiscal_period_end_fy"], "UTC")]
    return out


def fetch(post=None, places=PLACES, pause=0.5):
    """Une requête par bourse. post(url, body) → réponse JSON (tests : réponses préparées). Renvoie (items, places, erreurs)."""
    if post is None:
        import requests

        def post(url, b):
            r = requests.post(url, json=b, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.json()
    items, info, errors = {}, {}, {}
    for k, (market, place, suffix, tz) in enumerate(places):
        if k and pause:
            time.sleep(pause)
        try:
            got = parse(post(URL.format(market), body(market, place)), suffix, tz)
        except Exception as e:  # noqa: BLE001 - une bourse en panne n'arrête pas les autres
            errors[suffix] = f"{type(e).__name__}: {str(e)[:120]}"
            continue
        sess = Counter(v[0] for v in got.values()).most_common(1)
        info[suffix] = {"rows": len(got), "session": sess[0][0] if sess else None}
        for sym, v in got.items():
            items.setdefault(sym, v)
    return items, info, errors


def main():
    t0 = time.time()
    if OUT.exists():  # jamais de fichier de la veille : sans réponse ce soir, aucune donnée TradingView n'est utilisée
        OUT.unlink()
    try:
        items, info, errors = fetch()
    except Exception as e:  # noqa: BLE001 - module requests absent, etc. : l'outil tourne comme avant
        items, info, errors = {}, {}, {"*": f"{type(e).__name__}: {str(e)[:120]}"}
    now = datetime.now(timezone.utc)
    out = {"date": now.date().isoformat(), "at": now.isoformat(timespec="seconds"), "places": info, "errors": errors,
           "items": items}
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    log(f"TradingView : {len(items)} titres sur {len(info)} bourses en {time.time() - t0:.0f} s ; "
        + ", ".join(f"{k} {v.get('rows')} ({v.get('session')})" for k, v in info.items())
        + (f" ; injoignables : {errors}" if errors else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
