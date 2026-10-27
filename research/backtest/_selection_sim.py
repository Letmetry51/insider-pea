"""Sélection simulée 1997-2026, règles de ES.pickN (sans les comptes ni la liquidité, inconnus dans l'historique) : faut-il
intégrer le 📣 et abaisser le seuil de +60 % sur 12 mois ? (27/10/2026)

Chaque semaine, les n premières sociétés sont achetées à parts égales et gardées 26 semaines (26 tranches en parallèle, comme la
sélection du lundi gardée 6 mois) ; frais 0,3 % par sens. Mesures : rendement annuel, écart avec le marché (moyenne des sociétés),
pire baisse, et rendement à 6 mois de chaque société choisie face à la moyenne (une ligne par choix).

Règles reproduites (core.js, ES.pickThree) :
- palier 0 : pente forte (≥ +41 % en 6 mois), tendance, +60 à +200 % sur 12 mois ;
- palier 1 : pente moyenne ou forte (≥ +14 %), +30 à +200 % ; repêchée en palier 0 par un 📣 bond si au-dessus de sa moyenne 10 sem. ;
- écartées : tiers le plus faible sur 12 mois, ⚡ cours très volatil (≥ 80 %/an) ;
- ordre : 🔊 volumes ×1,5 sur 10 semaines (×2) + 📣, puis au-dessus de la moyenne 10 semaines, puis note, puis pente ;
- 2 sociétés par secteur au plus (3 si besoin).
"""
import numpy as np
exec(open('_longue_base2.py').read().split("if __name__ == '__main__':")[0])

okn = fin(P) & fin(mom) & fin(s26) & fin(mpn)
R0 = (r1 >= .08) & (vy >= 3)
R1 = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
bp8 = ago_any(R0, 8)                      # 📣 actuel (3 fois le volume), 8 dernières semaines
bh8 = ago_any(R1, 8)                      # 📣 au plus haut de l'année (2 fois le volume), 8 dernières semaines
dem = ago_any(R0 | R1, 4) & trend & okn & (mpn >= 1/3) & ~(v52 >= .8)   # 📣 démarrage affiché (bond il y a 3 semaines au plus)
hot = vx >= 1.5
wait = ~(P >= m10)
ratio = P / hi52
note = 50 * mpn + 10 * np.clip((ratio - .6) / .4, 0, 1) + np.where(trend, 15, 0)
retw = np.clip(np.nan_to_num(r1), -.6, 1.5)
mkw = np.array([np.nanmean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
secs = np.array([str(s) for s in z['sec']])


def pick(t, n=5, momMin=.6, wide=False, reserve=0, door=False, perSec=2, demNote=None, bondCap=None):
    ok = okn[:, t] & ~(mpn[:, t] < 1/3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
    strong = trend[:, t] & (s26[:, t] >= .41)
    mid = trend[:, t] & (s26[:, t] >= .14)
    bump = bp8[:, t] | (bh8[:, t] if wide else False)
    t0 = ok & strong & (mom[:, t] >= momMin)
    t1 = ok & mid & (mom[:, t] >= .3) & ~t0
    promo = t1 & bump & ~wait[:, t]
    tier0 = t0 | promo
    tier1 = t1 & ~promo
    if door:
        tier0 = tier0 | (ok & dem[:, t])
        tier1 = tier1 & ~tier0
    pri = 2 * hot[:, t] + bump

    def order(M):
        idx = np.where(M)[0]
        return idx[np.lexsort((-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t], -pri[idx]))]
    out, seen = [], {}
    q = order(tier0).tolist() + order(tier1).tolist()
    m = n - reserve
    for cap in (perSec, perSec + 1):
        for i in q:
            if len(out) >= m:
                break
            if i in out or seen.get(secs[i], 0) >= cap:
                continue
            seen[secs[i]] = seen.get(secs[i], 0) + 1
            out.append(i)
    if reserve:
        dm = ok & dem[:, t] & ~np.isin(np.arange(N), out)
        if demNote is not None:
            dm = dm & (np.nan_to_num(note[:, t]) >= demNote)
        d = [i for i in order(dm)]
        bc = perSec + 1 if bondCap is None else bondCap
        for i in d:
            if len(out) >= n:
                break
            if seen.get(secs[i], 0) >= bc:
                continue
            seen[secs[i]] = seen.get(secs[i], 0) + 1
            out.append(i)
        for i in q:                      # pas de 📣 cette semaine : la place revient au 🎯 suivant
            if len(out) >= n:
                break
            if i not in out and seen.get(secs[i], 0) < perSec + 1:
                seen[secs[i]] = seen.get(secs[i], 0) + 1
                out.append(i)
    return out


def simulate(f, a, b, hold=26, cost=.003):
    sleeves, R, M, picks = [], [], [], []
    for t in range(a, min(b, T - 1)):
        s = np.array(f(t), dtype=int)
        if len(s):
            sleeves.append([t, s, np.ones(len(s)) / len(s)])
            picks.append((t, s))
        sleeves = [x for x in sleeves if t - x[0] < hold]
        if not sleeves:
            continue
        r = 0.0
        for x in sleeves:
            rr = retw[x[1], t + 1]
            r += (x[2] * rr).sum()
            x[2] = x[2] * (1 + rr)
        r = r / len(sleeves) - cost * 2 / hold
        R.append(r)
        M.append(mkw[t + 1])
    R, M = np.array(R), np.array(M)

    def cg(x):
        eq = np.cumprod(1 + x)
        return eq[-1] ** (52 / len(x)) - 1, (eq / np.maximum.accumulate(eq) - 1).min()
    c, dd = cg(R)
    cm, _ = cg(M)
    # rendement à 6 mois de chaque choix face à la moyenne (écrêtée), une ligne par choix et par semaine
    ex = []
    for t, s in picks:
        if t + 26 >= T:
            continue
        F = P[:, t + 26] / P[:, t] - 1
        okk = okn[:, t] & fin(F)
        if okk.sum() < 30:
            continue
        lo_, hi_ = np.nanpercentile(F[okk], [2, 98])
        Fc = np.clip(F, lo_, hi_)
        v = Fc[s][fin(Fc[s])]
        if len(v):
            ex.append(v.mean() - Fc[okk].mean())
    return c, cm, dd, np.mean(ex) * 100 if ex else np.nan, np.mean([len(s) for _, s in picks]) if picks else 0


t1997 = int(np.searchsorted(dates, '1998-01-01'))
ERAS = [('1998-2008', t1997, int(np.searchsorted(yr, 2009))), ('2009-2017', int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))),
        ('2018-2026', int(np.searchsorted(yr, 2018)), T), ('1998-2026', t1997, T)]
VARIANTS = [
    ('actuel (+60 %, 📣 3 fois le volume)', dict()),
    ('📣 élargi dans l\'ordre et le repêchage', dict(wide=True)),
    ('4 🎯 + 1 📣 démarrage', dict(reserve=1)),
    ('📣 démarrage admis au palier 0', dict(door=True)),
    ('seuil 12 mois +50 %', dict(momMin=.5)),
    ('seuil 12 mois +40 %', dict(momMin=.4)),
    ('seuil 12 mois +30 %', dict(momMin=.3)),
]
if __name__ == '__main__':
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"Sélection de {n} sociétés chaque semaine, gardées 6 mois (frais 0,3 % par sens) ; {N} sociétés, {dates[t1997]} → {dates[-1]}")
    for lab, kw in VARIANTS:
        cells = []
        for el, a, b in ERAS:
            c, cm, dd, ex, k = simulate(lambda t: pick(t, n=n, **kw), a, b)
            cells.append(f"{el} {c*100:+5.1f} %/an (marché {cm*100:+4.1f}, écart {(c-cm)*100:+5.1f}) pire {dd*100:+4.0f} % · 6 mois/choix {ex:+4.1f}")
        print(f"\n  {lab} :\n    " + "\n    ".join(cells))
