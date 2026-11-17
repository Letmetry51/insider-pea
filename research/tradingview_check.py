"""Contrôle de bout en bout de la source TradingView (17/11/2026), sur les données du dernier calcul, avant la première mise en
service : collecteur réel (scrapers/tradingview.py), clôtures comparées aux fiches, garde-fous du secours, contrôle des F-scores.

- clôture de la veille d'après TradingView (clôture du jour / (1 + variation du jour)) comparée à la dernière clôture des
  fiches sociétés liquides, bourse par bourse : mesure la justesse des cours, des devises et de la correspondance des symboles ;
- cotations du jour qui passeraient les garde-fous du secours (scrapers/backup_prices.py : devise, fourchette ÷2 à ×2) ;
- rapport du contrôle des F-scores (euro_signal/tv_check.py) sur le classement publié.
Rien n'est écrit hors de research/out/ (les fichiers de data/ de la machine du workflow sont jetés).

  python tradingview_check.py   (GitHub Actions : workflow « Recherche (à la demande) », script tradingview_check.py)
Résultat : out/tradingview_check.txt et out/fscore-tv.json
"""
import json
import os
import sys
import time
from collections import Counter

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scrapers"))
sys.path.insert(0, os.path.join(ROOT, "euro_signal"))
import backup_prices as B  # noqa: E402
import tradingview as T  # noqa: E402
import tv_check as C  # noqa: E402

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)


def prev_closes():
    """Clôture de la séance précédente d'après TradingView : clôture / (1 + variation du jour en %)."""
    out = {}
    for market, place, suffix, tz in T.PLACES:
        b = T.body(market, place)
        b["columns"] = ["name", "close", "change", "currency"]
        try:
            r = requests.post(T.URL.format(market), json=b, headers=T.HEADERS, timeout=20)
            r.raise_for_status()
            for row in r.json().get("data") or []:
                name, close, chg, cur = row["d"]
                sym = T.yahoo_symbol(name, suffix)
                if sym and isinstance(close, (int, float)) and isinstance(chg, (int, float)) and close > 0:
                    out.setdefault(sym, (close / (1 + chg / 100), T.CURRENCY.get(cur, cur)))
        except Exception as e:  # noqa: BLE001
            log(f"   {suffix} : variation illisible ({e})")
        time.sleep(0.5)
    return out


def main():
    t0 = time.time()
    T.main()
    tv = json.load(open(T.OUT, encoding="utf-8"))
    log(f"Collecteur : {len(tv['items'])} titres, {len(tv['places'])} bourses, erreurs {tv['errors']} ({time.time() - t0:.0f} s)")
    for k, v in tv["places"].items():
        log(f"   {k:3} {v['rows']:5} titres, séance {v['session']}")
    today = tv["date"]
    sess = Counter(v[0] for v in tv["items"].values()).most_common(1)[0][0]

    co = B.DATA / "societes"
    shards = [json.load(open(f, encoding="utf-8")) for f in sorted(co.glob("*.json"))]
    prev = prev_closes()
    log(f"\n== Clôture de la veille TradingView contre dernière clôture des fiches (sociétés à 1 M€ par jour ou plus) ; séance TradingView {sess}")
    by, worst = {}, []
    for sh in shards:
        dd = sh.get("dDates") or []
        for sym, x in (sh.get("items") or {}).items():
            if (x.get("turnoverEur") or 0) < 1e6:
                continue
            d = x.get("d") or []
            suf = sym.rsplit(".", 1)[-1]
            b = by.setdefault(suf, Counter())
            b["n"] += 1
            if sym not in tv["items"]:
                b["absent"] += 1
                continue
            last = d[-1] if d and dd and dd[-1] < sess else (d[-2] if len(d) > 1 else None)
            p = prev.get(sym)
            if not p or not last:
                b["sans comparaison"] += 1
                continue
            if x.get("currency") and p[1] and x["currency"].upper() != str(p[1]).upper():
                b["devise différente"] += 1
            e = abs(p[0] / last - 1)
            b["≤ 0,5 %" if e <= 0.005 else "≤ 2 %" if e <= 0.02 else "> 2 %"] += 1
            if e > 0.02:
                worst.append((round(e * 100, 1), sym, last, round(p[0], 4), x.get("currency"), p[1]))
            q = B.quote(sess, tv["items"][sym][1], currency=tv["items"][sym][5])
            b["garde-fous OK" if B.acceptable(q, B.last_pos(d), x.get("currency")) else "garde-fous refus"] += 1
    for suf, b in sorted(by.items(), key=lambda kv: -kv[1]["n"]):
        log(f"   {suf:3} " + ", ".join(f"{k} {v}" for k, v in b.items()))
    worst.sort(reverse=True)
    log(f"   écarts de plus de 2 % : {len(worst)}")
    for w in worst[:20]:
        log("   ", w)

    q, st = B.tradingview_quotes(sess, today, T.OUT)
    log(f"\n== Lecture par le secours des cours : {st} (séance {sess}, jour {today})")

    es = json.load(open(B.DATA / "euro-signal.json", encoding="utf-8"))
    rep = C.compare(es.get("rank"), tv["items"])
    log(f"\n== Contrôle des F-scores : {json.dumps({k: v for k, v in rep.items() if k != 'check'}, ensure_ascii=False)}")
    for c in rep["check"]:
        log("   à vérifier", json.dumps(c, ensure_ascii=False))
    with open(os.path.join(OUT, "fscore-tv.json"), "w", encoding="utf-8") as f:
        json.dump(dict(rep, date=today, available=True), f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "tradingview_check.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
