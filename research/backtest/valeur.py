"""💎 Valeur : premier test de la règle sur nos propres données (comptes annuels Yahoo 2022-2025, cours hebdomadaires).

Règle testée, identique au calcul du soir (ES.pickValue) : sociétés liquides (≥ 1 M€ échangés par jour), cours / fonds
propres dans le tiers le plus bas, F-score de Piotroski ≥ 7 (même calcul que core.js), hausse sur 12 mois ≥ −40 %,
banques et assurances exclues. Chaque mois de mai 2024 à avril 2026, avec les seuls comptes publiés à cette date
(clôture + 120 jours) : résultat 6 mois plus tard (dividendes inclus), comparé à la société moyenne du même mois.

  cd research/backtest && python valeur.py            # long.npz (voir _long.py) et ../../data (tools/donnees.sh)

Limites : 2 ans de mesure seulement (4 périodes de 6 mois indépendantes), sociétés encore cotées aujourd'hui,
cours ajustés des dividendes (cours / fonds propres passé un peu sous-estimé pour les gros payeurs de dividendes).
"""
import glob, json, re, sys
from datetime import date, timedelta
import numpy as np

NPZ = sys.argv[1] if len(sys.argv) > 1 else 'long.npz'
DATA = sys.argv[2] if len(sys.argv) > 2 else '../../data'
COST = 0.01  # aller-retour (courtage + écart achat/vente) pour le chiffre net
FX = {'ST': 11.2, 'OL': 11.7, 'CO': 7.46, 'WA': 4.3, 'SW': 0.94}  # devise locale pour 1 € (ordre de grandeur 2024-2026)
FIN_RE = re.compile(r'financial|bank|insurance|banque|assurance|capital markets|asset management|credit services', re.I)

d = np.load(NPZ)
P = d['P'].astype(float); V = d['V'].astype(float); dates = [str(x) for x in d['dates']]; cols = [str(x) for x in d['cols']]
P = np.where(P > 0, P, np.nan); V = np.where(V > 0, V, np.nan); T = len(dates)
col = {c: i for i, c in enumerate(cols)}
fin = json.load(open(f'{DATA}/financials.json'))['items']
inst = json.load(open(f'{DATA}/euro-signal.json'))['inst']
cat = {}  # catalogue : secteur et cours / fonds propres Yahoo du jour, pour les sociétés sans dossier Euro Signal
for g in glob.glob(f'{DATA}/societes/*.json'):
    for sym, x in json.load(open(g))['items'].items():
        cat[sym] = x


def div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def fscore(cur, prv):
    """Copie de fscoreOf (core.js) : 9 critères, ramenés sur 9 quand 7 au moins sont calculables."""
    roa = lambda y: div(y.get('netIncome'), y.get('totalAssets'))
    cr = lambda y: div(y.get('currentAssets'), y.get('currentLiabilities'))
    gm = lambda y: div(y.get('grossProfit'), y.get('revenue'))
    ato = lambda y: div(y.get('revenue'), y.get('totalAssets'))

    def lev(y):
        if not y.get('totalAssets'):
            return None
        x = y.get('longTermDebt') if y.get('longTermDebt') is not None else y.get('totalDebt')
        return None if x is None else x / y['totalAssets']

    up = lambda a, b: None if a is None or b is None else a > b
    lc, lp = lev(cur), lev(prv)
    crit = [None if roa(cur) is None else roa(cur) > 0,
            None if cur.get('cfo') is None else cur['cfo'] > 0,
            up(roa(cur), roa(prv)),
            None if cur.get('cfo') is None or cur.get('netIncome') is None else cur['cfo'] > cur['netIncome'],
            None if lc is None or lp is None else (lc < lp or (lc == 0 and lp == 0)),
            up(cr(cur), cr(prv)),
            None if cur.get('shares') is None or prv.get('shares') is None else cur['shares'] <= prv['shares'] * 1.01,
            up(gm(cur), gm(prv)),
            up(ato(cur), ato(prv))]
    known = [c for c in crit if c is not None]
    return round(sum(known) * 9 / len(known)) if len(known) >= 7 else None


# Sociétés : exercices publiés (date de publication supposée = clôture + 120 jours), F-score, fonds propres par action
cos = []
for isin, f in fin.items():
    i = inst.get(isin) or {}
    tk = f.get('ticker') or i.get('ticker')
    if tk not in col:
        continue
    fu, cx = i.get('fund') or {}, cat.get(tk) or {}
    sec = i.get('sector') or fu.get('sector') or cx.get('sector') or ''
    if FIN_RE.search(f"{sec} {fu.get('industry') or cx.get('industry') or ''}"):
        continue
    Y = sorted([y for y in f.get('years') or [] if y.get('date')], key=lambda y: y['date'])
    yrs = []
    for k in range(1, len(Y)):
        cur, prv = Y[k], Y[k - 1]
        if cur.get('revenue') is None or cur.get('netIncome') is None:
            continue
        f9 = fscore(cur, prv)
        if f9 is None or not (cur.get('equity') or 0) > 0 or not (cur.get('shares') or 0) > 0:
            continue
        pub = (date.fromisoformat(cur['date']) + timedelta(days=120)).isoformat()
        yrs.append((pub, f9, cur['equity'] / cur['shares']))
    if not yrs:
        continue
    # devise ou unité des comptes ≠ devise de cotation : corrigé par le rapport avec le cours / fonds propres calculé ce soir
    ix = col[tk]; last = P[ix][np.isfinite(P[ix])]
    pbE = (i.get('value') or {}).get('pb') or cx.get('pb')
    if not len(last) or not pbE or pbE <= 0:
        continue
    k = pbE / (last[-1] / yrs[-1][2])
    if not (0.6 < k < 1.6) and not any(0.6 < k / r < 1.6 for r in (1 / 11.2, 11.2, 1 / 11.7, 11.7, 1 / 7.46, 7.46, 100, 0.01, 1.08, 1 / 1.08)):
        continue  # écart inexpliqué : société écartée plutôt qu'un cours / fonds propres faux
    fx = FX.get(tk.rsplit('.', 1)[-1], 1.0)
    cos.append({'isin': isin, 'ix': ix, 'yrs': yrs, 'k': k, 'fx': fx, 'sec': sec or '?'})
print(f'{len(cos)} sociétés (cours depuis 1985, comptes 2022-2025, hors banques et assurances)')

H = 26
fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 52:] / P[:, :-52] - 1
tv = P * V / 5  # échanges par jour (devise locale), moyenne sur 26 semaines
liq = np.full_like(P, np.nan)
c = np.nancumsum(np.nan_to_num(tv), 1)
liq[:, 26:] = (c[:, 26:] - c[:, :-26]) / 26
starts = [t for t in range(1, T) if dates[t][:7] != dates[t - 1][:7] and '2024-05' <= dates[t][:7] <= '2026-04']
groups = {'💎 règle complète (toutes)': [], '💎 les 10 premières (comme le calcul du soir)': [], 'bon marché, tout F-score': [],
          'F-score ≥ 7, tout prix': [], 'chères (tiers le plus haut)': [], 'F-score ≤ 3': [], 'toutes (repère)': []}
cohorts = []
for t in starts:
    D = dates[t]; rows = []
    for co in cos:
        ix = co['ix']
        if not np.isfinite(P[ix, t]) or not np.isfinite(fut[ix, t]):
            continue
        pub = [y for y in co['yrs'] if y[0] <= D]
        if not pub or not np.isfinite(liq[ix, t]):
            continue
        _, f9, bvps = pub[-1]
        rows.append((ix, f9, P[ix, t] * co['k'] / bvps, liq[ix, t] / co['fx'], mom[ix, t], co['sec']))
    rows = [r for r in rows if r[3] >= 1e6 and r[2] > 0]
    if len(rows) < 60:
        continue
    pbs = sorted(r[2] for r in rows); cut = pbs[len(pbs) // 3]; hiCut = pbs[2 * len(pbs) // 3]
    allix = np.array([r[0] for r in rows]); F = fut[allix, t]
    lo, hi = np.nanpercentile(F, [2, 98]); Fc = np.clip(F, lo, hi); base = Fc.mean()
    val = lambda r: r[2] <= cut and r[1] >= 7 and (not np.isfinite(r[4]) or r[4] >= -0.4)
    pool = sorted([r for r in rows if val(r)], key=lambda r: (-r[1], r[2]))
    top, seen = [], {}
    for r in pool:
        if len(top) >= 10 or seen.get(r[5], 0) >= 2:
            continue
        seen[r[5]] = seen.get(r[5], 0) + 1; top.append(r)
    sets = {'💎 règle complète (toutes)': pool, '💎 les 10 premières (comme le calcul du soir)': top,
            'bon marché, tout F-score': [r for r in rows if r[2] <= cut], 'F-score ≥ 7, tout prix': [r for r in rows if r[1] >= 7],
            'chères (tiers le plus haut)': [r for r in rows if r[2] >= hiCut], 'F-score ≤ 3': [r for r in rows if r[1] <= 3],
            'toutes (repère)': rows}
    pos = {r[0]: k for k, r in enumerate(rows)}
    for g, S in sets.items():
        if len(S) < 3:
            continue
        e = np.array([Fc[pos[r[0]]] for r in S]); raw = np.array([F[pos[r[0]]] for r in S])
        groups[g].append((D, e.mean() - base, (raw > base).mean(), (raw <= -0.25).mean(), len(S)))
    cohorts.append((D, len(rows), len(pool)))

print(f'{len(cohorts)} mois de départ, de {cohorts[0][0]} à {cohorts[-1][0]} ; '
      f'{int(np.mean([c[1] for c in cohorts]))} sociétés liquides par mois, dont {int(np.mean([c[2] for c in cohorts]))} 💎 en moyenne\n')
print('Écart à 6 mois avec la société moyenne du même mois (dividendes inclus, avant frais)')
for g, L in groups.items():
    if not L:
        continue
    e = np.array([x[1] for x in L]); n = len(e)
    t_ = e.mean() / e.std(ddof=1) * np.sqrt(n) / np.sqrt(6) if n > 2 and e.std() > 0 else float('nan')  # départs mensuels, horizon 6 mois
    halves = [np.mean([x[1] for x in L if x[0][:7] in p] or [np.nan]) * 100 for p in (
        ('2024-05', '2024-06', '2024-07', '2024-08', '2024-09', '2024-10'), ('2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04'),
        ('2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10'), ('2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04'))]
    print(f"  {g:46s} {e.mean()*100:+5.1f} pts (net {e.mean()*100 - COST*100:+5.1f}) t {t_:4.1f} | battent la moyenne "
          f"{np.mean([x[2] for x in L])*100:3.0f} % | chutes ≤ −25 % {np.mean([x[3] for x in L])*100:4.1f} % | "
          f"{np.mean([x[4] for x in L]):5.0f} soc. | par semestre : " + ' / '.join(f'{h:+.1f}' for h in halves))
