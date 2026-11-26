"""Couverture des comptes historiques chez EODHD (26/11/2026 : François a pris un mois de la formule « Fundamentals » pour tester le
filtre « comptes solides » du 🎯 sur 25 ans : « C'est fait, j'ai pris l'abonnement donc TOUT faire ce que tu proposes »).

Avant le test complet : pour 4 sociétés cotées et 4 retirées de la cote par bourse (univers de survivant_eodhd.py, tirage fixe),
exercices annuels disponibles (premier, nombre), postes du F-score (chiffre d'affaires, résultat net, flux d'exploitation, total du
bilan, actifs et passifs courants, dette à long terme, nombre d'actions, marge brute), date de dépôt des comptes, secteur. Coût :
10 appels par société. Rien n'est écrit (données EODHD gardées en mémoire seulement).
"""
import collections
import random

import survivant_eodhd as SE

log = SE.log
NEED = {'Income_Statement': ('totalRevenue', 'netIncome', 'grossProfit'),
        'Balance_Sheet': ('totalAssets', 'totalCurrentAssets', 'totalCurrentLiabilities', 'longTermDebt', 'commonStockSharesOutstanding'),
        'Cash_Flow': ('totalCashFromOperatingActivities',)}


def fetch(sym):
    for flt in ('General::Sector,General::Industry,Financials', 'Financials'):
        x, err = SE.get('fundamentals/' + sym, filter=flt)
        if isinstance(x, dict) and x:
            return x, flt, None
    return None, None, err


def years_of(x):
    """Exercices avec au moins le chiffre d'affaires ou le résultat net, et la part des postes du F-score présents."""
    fin = (x.get('Financials') if 'Financials' in x else x) or {}
    out = {}
    for st, keys in NEED.items():
        y = ((fin.get(st) or {}).get('yearly') or {}) if isinstance(fin.get(st), dict) else {}
        for d, v in y.items():
            if not isinstance(v, dict):
                continue
            e = out.setdefault(str(d)[:10], {'n': 0, 'k': 0, 'filing': bool(v.get('filing_date'))})
            for k in keys:
                e['k'] += 1
                try:
                    if v.get(k) not in (None, '', 'None') and float(v.get(k)) == float(v.get(k)):
                        e['n'] += 1
                except (TypeError, ValueError):
                    pass
    return {d: e for d, e in out.items() if e['n'] >= 3}


def main():
    if not SE.KEY:
        log("Pas de clé EODHD")
        return 1
    u, err = SE.get('user')
    log(f"Formule « {(u or {}).get('subscriptionType')} », {(u or {}).get('apiRequests')} appels utilisés aujourd'hui" if u else f"Compte : {err}")
    rows = SE.universe()
    rnd = random.Random(26112026)
    by = collections.defaultdict(lambda: {0: [], 1: []})
    for r in rows:
        by[r['ex']][r['dl']].append(r)
    stat = collections.defaultdict(list)
    for ex in sorted(by):
        for dl in (0, 1):
            pool = by[ex][dl]
            for r in rnd.sample(pool, min(4, len(pool))):
                x, flt, err = fetch(r['sym'])
                if not x:
                    log(f"  {r['sym']:16s} {'retirée' if dl else 'cotée  '} : {err}")
                    stat[(ex, dl)].append(None)
                    continue
                ys = years_of(x)
                g = x.get('General') or {}
                full = sorted(d for d, e in ys.items() if e['n'] >= 7)
                log(f"  {r['sym']:16s} {'retirée' if dl else 'cotée  '} : {len(ys)} exercices"
                    + (f" de {min(ys)[:4]} à {max(ys)[:4]}" if ys else '') + f", complets (7 postes sur 9) {len(full)}"
                    + f", date de dépôt {'oui' if any(e['filing'] for e in ys.values()) else 'non'}"
                    + (f", secteur {g.get('Sector') or '?'} / {g.get('Industry') or '?'}" if g else f" (filtre {flt})"))
                stat[(ex, dl)].append((len(ys), min(ys) if ys else None, len(full)))
    log("\nPar bourse (cotées | retirées) : sociétés avec des comptes, exercices en médiane, premier exercice médian")
    tot = {0: [0, 0], 1: [0, 0]}
    for ex in sorted(by):
        cells = []
        for dl in (0, 1):
            v = stat[(ex, dl)]
            have = [a for a in v if a and a[0]]
            tot[dl][0] += len(have)
            tot[dl][1] += len(v)
            med = sorted(a[0] for a in have)[len(have) // 2] if have else 0
            fst = sorted(a[1] for a in have)[len(have) // 2][:4] if have else '—'
            cells.append(f"{len(have)}/{len(v)}, {med} exercices, depuis {fst}")
        log(f"  {ex:6s} {cells[0]:34s} | {cells[1]}")
    log(f"\nEn tout : comptes pour {tot[0][0]}/{tot[0][1]} cotées et {tot[1][0]}/{tot[1][1]} retirées ; {SE.calls[0]} appels")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
