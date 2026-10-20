"""Nasdaq Nordic : la liste complète d'une bourse (« screener ») donne-t-elle symbole, date et clôture du soir ?
Champs d'une ligne, catégories (marché principal, First North), pages, et comparaison avec l'historique d'un titre.

  python nordic_probe.py        (GitHub Actions : workflow « Recherche (à la demande) », script nordic_probe.py)
Résultat : out/nordic_probe.txt
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scrapers"))
import backup_prices as B  # noqa: E402

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)


first = {}
for mk in ("STO", "HEL", "CPH"):
    for cat in ("MAIN_MARKET", "FIRST_NORTH", "FIRSTNORTH", "ALL"):
        try:
            r = B.http_get(f"{B.NASDAQ}/screener/shares", params={"category": cat, "tableonly": "false", "market": mk},
                           accept="application/json", tries=1, timeout=30)
            js = r.json()
            d0 = js.get("data") if isinstance(js, dict) else None
            il = d0.get("instrumentListing") if isinstance(d0, dict) else None
            rows = il.get("rows") if isinstance(il, dict) else None
            log(f"{mk} {cat} : {len(rows) if isinstance(rows, list) else '?'} lignes · clés {list(il.keys()) if isinstance(il, dict) else il}"
                f" · pages {json.dumps(d0.get('pagination') if isinstance(d0, dict) else None)[:200]}")
            if isinstance(il, dict):
                log("   en-têtes :", json.dumps(il.get("headers"), ensure_ascii=False)[:600])
            if isinstance(d0, dict) and cat == "MAIN_MARKET":
                log("   filtres :", json.dumps(d0.get("filters"), ensure_ascii=False)[:800])
            if rows:
                log("   première ligne :", json.dumps(rows[0], ensure_ascii=False))
                first.setdefault(mk, rows)
        except Exception as e:
            log(f"{mk} {cat} : ✗ {e}")

# comparaison : dernier cours de la liste et historique du même titre (3 titres par bourse)
log("\n== Liste contre historique")
for mk, rows in first.items():
    top = sorted(rows, key=lambda r: -(B.num(r.get("turnover")) or 0))[:3]
    for r in top:
        sym = r.get("symbol") or r.get("ticker")
        oid = r.get("orderbookId")
        log(f"   {mk} {sym} {oid} : dernier {r.get('lastSalePrice')} · volume {r.get('volume')} · {r.get('lastTraded')} {r.get('time')}")
        if oid:
            try:
                h = B.http_get(f"{B.NASDAQ}/instruments/{oid}/chart/download",
                               params={"assetClass": "SHARES", "fromDate": "2026-10-10", "toDate": "2026-10-31"},
                               accept="application/json", tries=1, timeout=30)
                q = B.parse_nordic_chart(h.json())
                log("      historique :", [(x["date"], x["close"]) for x in q[-3:]])
            except Exception as e:
                log("      historique ✗", e)

open(os.path.join(OUT, "nordic_probe.txt"), "w").write("\n".join(lines) + "\n")
