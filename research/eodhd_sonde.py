"""Sonde EODHD avant le test sans biais du survivant (22/11/2026, François a pris la formule « Historian ») : formule active,
sociétés cotées et retirées de la cote par bourse (actions ordinaires, ISIN, devises), forme des cours hebdomadaires d'une
société disparue et d'une société cotée, change. Une soixantaine d'appels. La clé n'est jamais affichée ni écrite : en cas
d'erreur, seuls le code HTTP et le type d'erreur sont imprimés (le message d'une erreur contient l'adresse, donc la clé).
"""
import collections
import os
import random
import sys

import requests

KEY = os.environ.get("EODHD_API_KEY", "").strip()
EX = ['PA', 'XETRA', 'MI', 'MC', 'AS', 'BR', 'LS', 'VI', 'HE', 'ST', 'CO', 'OL', 'IR']
EEA = set('AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IS IT LI LT LU LV MT NL NO PL PT RO SE SI SK'.split())


def log(*a):
    print(*a, flush=True)


def get(path, **params):
    try:
        r = requests.get("https://eodhd.com/api/" + path, params={"api_token": KEY, "fmt": "json", **params}, timeout=90)
    except Exception as e:
        return None, type(e).__name__
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        return r.json(), None
    except Exception as e:
        return None, type(e).__name__


if not KEY:
    log("Secret EODHD_API_KEY absent.")
    sys.exit(0)
u, err = get("user")
if u:
    # seulement la formule et les quotas : jamais le nom, l'adresse ni le moyen de paiement (journal public)
    log(f"Formule « {u.get('subscriptionType')} », {u.get('dailyRateLimit')} appels par jour, {u.get('apiRequests')} déjà utilisés "
        f"aujourd'hui")
else:
    log(f"Compte : {err}")
random.seed(1)
samples = []
for ex in EX:
    rows = {}
    for dl in (0, 1):
        x, err = get(f"exchange-symbol-list/{ex}", **({"delisted": 1} if dl else {}))
        rows[dl] = x if isinstance(x, list) else []
        if err:
            log(f"  {ex} {'retirées' if dl else 'cotées'} : {err}")
    for dl in (0, 1):
        R = rows[dl]
        cs = [r for r in R if r.get('Type') == 'Common Stock']
        isin = [r for r in cs if r.get('Isin')]
        eea = [r for r in isin if str(r['Isin'])[:2] in EEA]
        cur = collections.Counter(r.get('Currency') for r in cs).most_common(3)
        log(f"  {ex:6s} {'retirées' if dl else 'cotées  '} : {len(R):5d} lignes, {len(cs):5d} actions ordinaires, {len(isin):5d} avec ISIN "
            f"({len(eea)} de l'EEE) ; devises {cur}")
        if dl and cs:
            samples += [(ex, r) for r in random.sample(cs, min(2, len(cs)))]
    act = {r['Code'] for r in rows[0]}
    reused = sum(1 for r in rows[1] if r.get('Type') == 'Common Stock' and r['Code'] in act)
    log(f"         codes de sociétés retirées repris par une société cotée : {reused}")

log("\nCours hebdomadaires de sociétés retirées de la cote (échantillon)")
for ex, r in samples[:14]:
    x, err = get(f"eod/{r['Code']}.{ex}", period='w', **{"from": "1998-01-01"})
    if not x:
        log(f"  {r['Code']}.{ex} ({r.get('Name', '')[:30]}) : {err or 'vide'}")
        continue
    a, b = x[0], x[-1]
    log(f"  {r['Code']}.{ex:6s} {r.get('Name', '')[:28]:28s} {len(x):5d} semaines, {a['date']} → {b['date']} ; dernière clôture "
        f"{b.get('close')} (ajustée {b.get('adjusted_close')}), volume {b.get('volume')} ; colonnes {sorted(a)}")
for sym in ('AIR.PA', 'SAP.XETRA'):
    x, err = get(f"eod/{sym}", period='w', **{"from": "2026-10-01"})
    log(f"  {sym} : " + (', '.join(f"{y['date']} {y['adjusted_close']}" for y in x[-4:]) if x else str(err)))
    x, err = get(f"eod/{sym}", **{"from": "2026-11-09"})
    log("    journalier : " + (', '.join(f"{y['date']} {y['adjusted_close']}" for y in x[-8:]) if x else str(err)))
for fx in ('EURSEK.FOREX', 'EURNOK.FOREX', 'EURDKK.FOREX'):
    x, err = get(f"eod/{fx}", period='w', **{"from": "1999-01-01"})
    log(f"  {fx} : " + (f"{len(x)} semaines, {x[0]['date']} {x[0]['close']} → {x[-1]['date']} {x[-1]['close']}" if x else str(err)))
u, err = get("user")
if u:
    log(f"\nappels utilisés aujourd'hui : {u.get('apiRequests')}")
