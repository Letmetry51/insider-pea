"""Contrôle de la source de cours de secours (scrapers/backup_prices.py) sur les vraies données, sans rien écrire.

1. Liste Euronext : clôture de la dernière séance comparée à celle de Yahoo (téléchargée maintenant), titre par titre ;
   titres du catalogue sur une place Euronext sans correspondance dans la liste (symbole différent ?).
2. Nasdaq Nordic : listes complètes de chaque bourse (retenues ou non pour la séance), puis titre par titre sur un
   échantillon (les plus échangés, puis au hasard) ; mêmes comparaisons, titres introuvables.
3. Simulation du calcul du soir sur une copie des fiches publiées et des cours Euro Signal : cases complétées, écarts avec
   Yahoo, durée. En séance, les listes nordiques sont écartées (dernier cours ≠ clôture) : lancer après 18 h pour les voir.

  python backup_check.py        (GitHub Actions : workflow « Recherche (à la demande) », script backup_check.py)
Résultat : out/backup_check.txt
"""
import copy
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

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


def pct(a, b):
    return abs(a / b - 1) * 100


def tally(pairs, title):
    """pairs : [(symbole, date, secours, yahoo)] → répartition des écarts."""
    if not pairs:
        log(f"   {title} : aucune comparaison possible")
        return
    e = [(s, d, a, b, pct(a, b)) for s, d, a, b in pairs]
    n = len(e)
    k = lambda t: sum(1 for x in e if x[4] <= t)
    log(f"   {title} : {n} comparaisons · identiques à 0,1 % près {k(0.1)} ({k(0.1) * 100 // n} %) · à 1 % {k(1)} · à 5 % {k(5)}"
        f" · au-delà {n - k(5)}")
    for s, d, a, b, p in sorted(e, key=lambda x: -x[4])[:8]:
        if p > 0.1:
            log(f"      écart {s} {d} : secours {a} · Yahoo {b} ({p:.1f} %)")


today = datetime.now(timezone.utc).date().isoformat()
files = sorted((B.DATA / "societes").glob("*.json"), key=lambda f: int(f.stem) if f.stem.isdigit() else 999)
shards = [B.read_json(f, None) for f in files]
shards = [s for s in shards if isinstance(s, dict) and isinstance(s.get("items"), dict)]
items = {k: v for s in shards for k, v in s["items"].items()}
dd = shards[0]["dDates"] if shards else []
log(f"Fiches publiées : {len(items)} sociétés, dernière séance {dd[-1] if dd else '?'}, "
    f"générées le {shards[0].get('generatedAt') if shards else '?'} ; contrôle du {today}")
miss_last = {}
for s, x in items.items():
    if isinstance(x.get("d"), list) and x["d"] and x["d"][-1] is None:
        m = s.rsplit(".", 1)[-1]
        miss_last[m] = miss_last.get(m, 0) + 1
log("   sans clôture à la dernière séance (par place) :", ", ".join(f"{k} {v}" for k, v in sorted(miss_last.items(), key=lambda kv: -kv[1])))

# --- 1. Liste Euronext
log("\n== 1. Liste Euronext")
t0 = time.time()
try:
    enx = B.euronext_quotes()
except Exception as e:
    enx = {}
    log("   liste injoignable :", e)
T = B.session_of(list(enx.values()), today)
dates = {}
for q in enx.values():
    dates[q["date"]] = dates.get(q["date"], 0) + 1
log(f"   {len(enx)} cotations en {time.time() - t0:.0f} s ; séance retenue {T} ; dates : "
    + ", ".join(f"{d} {n}" for d, n in sorted(dates.items(), reverse=True)[:5]))
places = {suf for _, suf in B.EURONEXT_PLACES}
on_enx = [s for s in items if s.rsplit(".", 1)[-1] in places]
unmapped = [s for s in on_enx if s not in enx]
log(f"   catalogue sur une place Euronext : {len(on_enx)} ; sans ligne dans la liste : {len(unmapped)}")
by = {}
for s in unmapped:
    by.setdefault(s.rsplit(".", 1)[-1], []).append(s)

def turnover(s):
    return items[s].get("turnoverEur") or 0


for m, l in sorted(by.items(), key=lambda kv: -len(kv[1])):
    top = ", ".join("%s %d k€" % (s, round(turnover(s) / 1e3)) for s in sorted(l, key=turnover, reverse=True)[:6])
    log(f"      {m} : {len(l)} (les plus échangés : {top})")

# --- vérité : Yahoo maintenant (clôtures brutes des 10 derniers jours)
log("\n== Yahoo maintenant (référence)")
import pandas as pd  # noqa: E402
import yahoo  # noqa: E402

nordic_syms = [s for s in items if s.rsplit(".", 1)[-1] in B.NORDIC]
random.seed(7)
liquid = sorted(nordic_syms, key=lambda s: -(items[s].get("turnoverEur") or 0))
sample = liquid[:40] + random.sample(liquid[40:], min(20, max(0, len(liquid) - 40)))
want = sorted(set(on_enx) | set(nordic_syms))  # toutes les sociétés couvertes : comparaison complète
t0 = time.time()
Y = yahoo.download(want, "contrôle", period="10d", interval="1d", fields=("Close",), auto_adjust=False)["Close"]
log(f"   {Y.shape[1] if not Y.empty else 0} titres, séances {', '.join(str(d.date()) for d in Y.index[-4:])} ({time.time() - t0:.0f} s)")


def yv(s, d):
    try:
        v = float(Y.loc[pd.Timestamp(d), s])
        return v if v > 0 else None
    except Exception:
        return None


pairs = []
for s in on_enx:
    q = enx.get(s)
    if q:
        b = yv(s, q["date"])
        if b:
            pairs.append((s, q["date"], q["close"], b))
tally(pairs, "Euronext contre Yahoo, même séance")
by_m = {}
for p in pairs:
    by_m.setdefault(p[0].rsplit(".", 1)[-1], []).append(p)
for m, l in sorted(by_m.items()):
    good = sum(1 for p in l if pct(p[2], p[3]) <= 1)
    log(f"      {m} : {good}/{len(l)} à 1 % près")

# --- 2. Nasdaq Nordic
log("\n== 2. Nasdaq Nordic : listes complètes")
ids = {}
N = B.Nordic(ids, today, max_n=400, seconds=600)
t0 = time.time()
nl, ninfo = N.lists(T) if T else ({}, {})
log(f"   {json.dumps(ninfo)} ; {len(nl)} cours retenus pour le {T} ({time.time() - t0:.0f} s) ; en séance, listes écartées (normal)")
lpairs = [(s, q["date"], q["close"], yv(s, q["date"])) for s, q in nl.items() if s in items and yv(s, q["date"])]
tally(lpairs, "listes Nasdaq Nordic contre Yahoo, même séance")
nordic_cat = [s for s in items if s.rsplit(".", 1)[-1] in B.NORDIC]
log(f"   catalogue nordique : {len(nordic_cat)} ; présents dans les listes (numéro Nasdaq connu) : {sum(1 for s in nordic_cat if s in N.ids)}")
miss = sorted((s for s in nordic_cat if s not in N.ids), key=turnover, reverse=True)
if miss:
    log("      absents des listes, les plus échangés :", ", ".join("%s %d k€" % (s, round(turnover(s) / 1e3)) for s in miss[:10]))

log("\n== 2b. Nasdaq Nordic titre par titre (échantillon)")
t0 = time.time()
got, notfound, none = [], [], []
for s in sample:
    qs = N.quotes(s)
    if qs is None:
        none.append(s)
    elif not qs:
        notfound.append(s)
    else:
        got.append(s)
log(f"   {len(sample)} titres en {time.time() - t0:.0f} s : {len(got)} avec des cours, {len(notfound)} introuvables, {len(none)} sans réponse ;"
    f" {N.errors} erreurs")
if notfound:
    log("      introuvables :", ", ".join(notfound[:15]))
if got:
    log("      exemple :", got[0], N.cache[got[0]][-1])
npairs = []
for s in got:
    for q in N.cache[s]:
        b = yv(s, q["date"])
        if b:
            npairs.append((s, q["date"], q["close"], b))
tally(npairs, "Nasdaq Nordic contre Yahoo, mêmes séances")

# --- 3. Simulation du calcul du soir sur une copie
log("\n== 3. Simulation sur une copie des fiches publiées")
sim = copy.deepcopy(shards)
t0 = time.time()
bulk = {**nl, **enx}
st = B.patch_catalogue(sim, bulk, N.quotes, today, T)
log(f"   mode {st['mode']} · séance {st['session']} · {st['needed']} cases à compléter · {st['filled']} complétées · {st['rejected']} écartées"
    f" · {time.time() - t0:.0f} s · par place : {st['byMarket']}")
spairs = []
if st["mode"]:
    simd = sim[0]["dDates"]
    k = simd.index(T) if T in simd else None
    for sh0, sh in zip(shards, sim):
        for s, x in sh["items"].items():
            d0 = sh0["items"][s].get("d")
            if k is not None and isinstance(x.get("d"), list) and len(x["d"]) == len(simd) and x["d"][k] is not None \
                    and (st["mode"] == "append" or (isinstance(d0, list) and d0[k] is None)):
                b = yv(s, T)
                if b:
                    spairs.append((s, T, x["d"][k], b))
tally(spairs, "cases complétées contre Yahoo")
log(f"   Nasdaq Nordic pendant la simulation : {N.asked} titres demandés au total, {N.got} avec des cours, {N.errors} erreurs")
# soir où Yahoo n'a rien donné : fiches sans leur dernière séance (ni sa semaine), qui doit être ajoutée partout
if T and dd and dd[-1] == T:
    sim2 = copy.deepcopy(shards)
    for sh in sim2:
        nw = 1 if B.friday(sh["wDates"][-1]) == B.friday(T) and B.friday(sh["wDates"][-2]) < B.friday(T) else 0
        sh["dDates"] = sh["dDates"][:-1]
        sh["wDates"] = sh["wDates"][:len(sh["wDates"]) - nw]
        for x in sh["items"].values():
            if isinstance(x.get("d"), list):
                x["d"] = x["d"][:-1]
            if nw and isinstance(x.get("w"), list):
                x["w"] = x["w"][:-1]
            if nw and isinstance(x.get("wv"), list):
                x["wv"] = x["wv"][:-1]
    simT = sim2  # la séance T est alors plus récente que les fiches : ajout
else:
    simT = copy.deepcopy(shards)
t0 = time.time()
st2 = B.patch_catalogue(simT, bulk, N.quotes, today, T)
L = {len(sh["dDates"]) for sh in simT}
okd = all(sh["dDates"][-1] == T for sh in simT) if st2["mode"] == "append" else None
badlen = sum(1 for sh in simT for x in sh["items"].values()
             if (isinstance(x.get("d"), list) and len(x["d"]) != len(sh["dDates"])) or (isinstance(x.get("w"), list) and len(x["w"]) != len(sh["wDates"])))
apairs = [(s, T, x["d"][-1], yv(s, T)) for sh in simT for s, x in sh["items"].items()
          if st2["mode"] == "append" and isinstance(x.get("d"), list) and x["d"] and x["d"][-1] is not None and yv(s, T)]
log(f"   ajout d'une séance (fiches privées de la dernière) : mode {st2['mode']} · {st2['filled']} clôtures · séance en fin de dates partout : {okd}"
    f" · longueurs {sorted(L)} · séries de longueur fausse : {badlen} · semaines {simT[0]['wDates'][-2:]} · {time.time() - t0:.0f} s")
tally(apairs, "clôtures ajoutées contre Yahoo")
pf = B.DATA / "prices.json"
if pf.exists():
    prices = B.read_json(pf, {})
    p2 = copy.deepcopy(prices)
    sp = B.patch_prices(p2, bulk, N.quotes, today, T)
    log(f"   cours Euro Signal : {len((prices or {}).get('items') or {})} titres · {sp['needed']} en retard · {sp['filled']} complétés · "
        f"{sp['rejected']} écartés")
    ppairs = []
    for isin, it in (p2.get("items") or {}).items():
        if it.get("backup"):
            r = it["rows"][-1]
            b = yv(it["ticker"], r[0]) if it["ticker"] in Y.columns else None
            if b:
                ppairs.append((it["ticker"], r[0], r[4], b))
    tally(ppairs, "cours Euro Signal complétés contre Yahoo")
else:
    log("   cours Euro Signal (data/prices.json) absents : non simulés")

open(os.path.join(OUT, "backup_check.txt"), "w").write("\n".join(lines) + "\n")
