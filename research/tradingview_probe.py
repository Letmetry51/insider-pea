"""TradingView (screener public, scanner.tradingview.com) comme source de secours et de contrôle : répond-il depuis GitHub
Actions, donne-t-il la même dernière clôture que les fiches Euro Signal, et le même F-score de Piotroski que nos comptes ?

Sonde en lecture seule (17/11/2026), avant d'en faire une source :
- une requête par bourse (toutes les actions, cotation principale), quelques secondes en tout ;
- format brut de quelques lignes (date de la séance : champ « daily-bar.time ») ;
- correspondance symbole TradingView → symbole Yahoo, mesurée sur les fiches sociétés (data/societes) ;
- clôture du dernier jour des fiches comparée à celle de TradingView (écart relatif) ;
- F-score (exercice) comparé aux F-scores du classement (data/euro-signal.json, rank.rows[].f9).

  python tradingview_probe.py   (GitHub Actions : workflow « Recherche (à la demande) », script tradingview_probe.py)
Résultat : out/tradingview_probe.txt
"""
import glob
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Content-Type": "application/json", "Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"}
URL = "https://scanner.tradingview.com/{}/scan"
COLS = ["name", "exchange", "close", "open", "high", "low", "volume", "currency", "isin", "daily-bar.time",
        "last_bar_update_time", "update_mode", "piotroski_f_score_fy", "piotroski_f_score_ttm", "altman_z_score_fy",
        "fiscal_period_end_fy" , "market_cap_basic", "country"]
# marché TradingView → fuseau de la bourse
MARKETS = {"france": "Europe/Paris", "netherlands": "Europe/Amsterdam", "belgium": "Europe/Brussels", "portugal": "Europe/Lisbon",
           "italy": "Europe/Rome", "spain": "Europe/Madrid", "germany": "Europe/Berlin", "austria": "Europe/Vienna",
           "switzerland": "Europe/Zurich", "uk": "Europe/London", "sweden": "Europe/Stockholm", "finland": "Europe/Helsinki",
           "denmark": "Europe/Copenhagen", "norway": "Europe/Oslo", "ireland": "Europe/Dublin"}
# (marché, place TradingView) → suffixe Yahoo
SUFFIX = {("france", "EURONEXT"): "PA", ("netherlands", "EURONEXT"): "AS", ("belgium", "EURONEXT"): "BR",
          ("portugal", "EURONEXT"): "LS", ("ireland", "EURONEXT"): "IR", ("italy", "MIL"): "MI", ("italy", "EUROTLX"): None,
          ("spain", "BME"): "MC", ("germany", "XETR"): "DE", ("austria", "VIE"): "VI", ("switzerland", "SIX"): "SW",
          ("uk", "LSE"): "L", ("sweden", "OMXSTO"): "ST", ("finland", "OMXHEX"): "HE", ("denmark", "OMXCOP"): "CO",
          ("norway", "OSL"): "OL", ("norway", "EURONEXT"): "OL"}
lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)


def scan(market, n=5000):
    body = {"columns": COLS, "filter": [{"left": "type", "operation": "equal", "right": "stock"},
                                         {"left": "is_primary", "operation": "equal", "right": True}],
            "options": {"lang": "en"}, "range": [0, n], "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "markets": [market]}
    t0 = time.time()
    r = requests.post(URL.format(market), json=body, headers=UA, timeout=30)
    dt = time.time() - t0
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} {r.text[:150]!r}", dt
    js = r.json()
    rows = [dict(zip(COLS, d["d"]), s=d["s"]) for d in js.get("data") or []]
    return rows, js.get("totalCount"), dt


def bar_date(v, tz):
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
        return None
    if v > 1e12:  # millisecondes
        v /= 1000
    return datetime.fromtimestamp(v, ZoneInfo(tz)).date().isoformat()


def yahoo_symbol(name, suf):
    t = str(name or "").upper()
    if suf in ("ST", "HE", "CO", "OL", "L"):
        t = t.replace("_", "-").replace(".", "-")
    return f"{t}.{suf}" if t and suf else None


def main():
    co = {}
    for f in glob.glob(os.path.join(DATA, "societes", "*.json")):
        sh = json.load(open(f, encoding="utf-8"))
        dd = sh.get("dDates") or []
        for sym, x in (sh.get("items") or {}).items():
            d = x.get("d") or []
            last = next(((dd[i], d[i]) for i in range(len(d) - 1, -1, -1) if i < len(dd) and d[i]), None)
            co[sym] = {"last": last, "cur": x.get("currency"), "turn": x.get("turnoverEur") or 0}
    rank = {}
    try:
        es = json.load(open(os.path.join(DATA, "euro-signal.json"), encoding="utf-8"))
        for r in (es.get("rank") or {}).get("rows") or []:
            if r.get("sym"):
                rank[r["sym"]] = r
    except Exception as e:
        log("classement illisible :", e)
    log(f"Fiches sociétés : {len(co)} ; lignes du classement : {len(rank)} (dont {sum(1 for r in rank.values() if r.get('f9') is not None)} avec F-score)")
    log(f"Départ {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    tv = {}
    for m, tz in MARKETS.items():
        try:
            rows, total, dt = scan(m)
        except Exception as e:
            log(f"\n== {m} : ERREUR {type(e).__name__} {str(e)[:150]}")
            continue
        if rows is None:
            log(f"\n== {m} : {total} ({dt:.1f} s)")
            continue
        ex = Counter(r.get("exchange") for r in rows)
        dates = Counter(bar_date(r.get("daily-bar.time"), tz) for r in rows)
        log(f"\n== {m} : {len(rows)} lignes / {total} ({dt:.1f} s) ; places {ex.most_common(6)} ; séances {dates.most_common(4)}")
        log("   modes", Counter(r.get("update_mode") for r in rows).most_common(3))
        for r in rows[:3]:
            log("   brut", json.dumps(r, ensure_ascii=False)[:600])
        for r in rows:
            suf = SUFFIX.get((m, r.get("exchange")))
            y = yahoo_symbol(r.get("name"), suf)
            if y:
                tv.setdefault(y, dict(r, market=m, date=bar_date(r.get("daily-bar.time"), tz)))
        time.sleep(1)

    log("\n== Correspondance des symboles (fiches sociétés liquides, ≥ 1 M€ par jour)")
    by = {}
    for sym, x in co.items():
        if x["turn"] < 1e6:
            continue
        suf = sym.rsplit(".", 1)[-1] if "." in sym else "-"
        b = by.setdefault(suf, {"n": 0, "found": 0, "same_day": 0, "close_ok": 0, "cur_diff": 0, "ex": []})
        b["n"] += 1
        t = tv.get(sym)
        if not t:
            if len(b["ex"]) < 4:
                b["ex"].append(sym)
            continue
        b["found"] += 1
        if x["cur"] and t.get("currency") and x["cur"] != t["currency"]:
            b["cur_diff"] += 1
        if x["last"] and t.get("date") == x["last"][0] and t.get("close"):
            b["same_day"] += 1
            if abs(t["close"] / x["last"][1] - 1) < 0.005:
                b["close_ok"] += 1
    for suf, b in sorted(by.items(), key=lambda kv: -kv[1]["n"]):
        log(f"   {suf:3} {b['found']}/{b['n']} trouvés, {b['same_day']} même séance, {b['close_ok']} clôture à ±0,5 %,"
            f" {b['cur_diff']} devise différente ; absents ex. {b['ex']}")

    log("\n== F-score : classement Euro Signal (comptes Yahoo) contre TradingView (exercice)")
    diffs, both = Counter(), 0
    big = []
    for sym, r in rank.items():
        t = tv.get(sym)
        if r.get("f9") is None or not t or t.get("piotroski_f_score_fy") is None:
            continue
        both += 1
        d = int(round(t["piotroski_f_score_fy"])) - int(r["f9"])
        diffs[d] += 1
        if abs(d) >= 3:
            big.append((sym, r["f9"], t["piotroski_f_score_fy"], t.get("fiscal_period_end_fy")))
    log(f"   {both} sociétés comparables ; écart TradingView − Euro Signal : {sorted(diffs.items())}")
    if both:
        log(f"   identiques {diffs[0]} ({diffs[0] / both:.0%}), à 1 point près {sum(v for k, v in diffs.items() if abs(k) <= 1) / both:.0%},"
            f" écart ≥ 3 : {len(big)}")
    for b in big[:25]:
        log("   écart", b)
    sel = (es.get("rank") or {}).get("selection", {}).get("items", []) if rank else []
    log("\n== Sélection de la semaine")
    for it in sel:
        t = tv.get(it.get("sym")) or {}
        log(f"   {it.get('sym')} F-score ES {it.get('f9')} / TV {t.get('piotroski_f_score_fy')} ; clôture TV {t.get('close')} du {t.get('date')}")

    with open(os.path.join(OUT, "tradingview_probe.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
