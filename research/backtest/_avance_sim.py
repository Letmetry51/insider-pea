"""Place 📣 de la sélection : choisir le bond de meilleure qualité (volume du bond, accumulation avant, bond répété) plutôt que
l'ordre actuel (🔊, 📣 sur 3 fois le volume, au-dessus de la moyenne 10 semaines, note). Écart par an avec la sélection 4 🎯 + 1 📣
actuelle, portefeuille simulé 1998-2026 (5 lignes chaque semaine gardées 6 mois)."""
import numpy as np
exec(open('_selection_sim2.py').read().split('print("Écart avec')[0])

up_w = np.where(r1 > 0, VO, 0.0); dn_w = np.where(r1 < 0, VO, 0.0)
up_w[~fin(VO) | ~fin(r1)] = np.nan; dn_w[~fin(VO) | ~fin(r1)] = np.nan
ud13 = roll(up_w, 13, np.nansum) / roll(dn_w, 13, np.nansum)
B = R0 | R1
ud_prev = shift(ud13, 1)
big3 = ago_any(B & (vy >= 3), 4)
big5 = ago_any(B & (vy >= 5), 4)
accb = ago_any(B & (ud_prev >= 1.5), 4)
repb = ago_any(B & bshift(ago_any(B, 26), 1), 4)
qual = big3.astype(int) + big5.astype(int) + accb.astype(int) + repb.astype(int)
bv0 = np.where(B & fin(vy), vy, 0.0)
bvx = np.maximum.reduce([bv0, shift(bv0, 1), shift(bv0, 2), shift(bv0, 3)])
bvx = np.nan_to_num(bvx)


def pick2(t, n=5, reserve=1, bondOrder='pri', perSec=2, qmin=None):
    ok = okn[:, t] & ~(mpn[:, t] < 1/3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
    strong = trend[:, t] & (s26[:, t] >= .41)
    mid = trend[:, t] & (s26[:, t] >= .14)
    bump = bp8[:, t]
    t0 = ok & strong & (mom[:, t] >= .6)
    t1 = ok & mid & (mom[:, t] >= .3) & ~t0
    promo = t1 & bump & ~wait[:, t]
    tier0 = t0 | promo
    tier1 = t1 & ~promo
    pri = 2 * hot[:, t] + bump

    def order(M, extra=None):
        idx = np.where(M)[0]
        keys = [-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t], -pri[idx]]
        if extra is not None:
            keys.append(-extra[idx])
        return idx[np.lexsort(tuple(keys))]
    out, seen = [], {}
    q = order(tier0).tolist() + order(tier1).tolist()
    for cap in (perSec, perSec + 1):
        for i in q:
            if len(out) >= n - reserve:
                break
            if i in out or seen.get(secs[i], 0) >= cap:
                continue
            seen[secs[i]] = seen.get(secs[i], 0) + 1
            out.append(i)
    if reserve:
        dm = ok & dem[:, t] & ~np.isin(np.arange(N), out)
        if qmin is not None:
            dm = dm & (qual[:, t] >= qmin)
        extra = None if bondOrder == 'pri' else qual[:, t] if bondOrder == 'q' else np.nan_to_num(bvx[:, t])
        for i in order(dm, extra):
            if len(out) >= n:
                break
            if seen.get(secs[i], 0) >= perSec:
                continue
            seen[secs[i]] = seen.get(secs[i], 0) + 1
            out.append(i)
        for cap in (perSec, perSec + 1):
            for i in q:
                if len(out) >= n:
                    break
                if i not in out and seen.get(secs[i], 0) < cap:
                    seen[secs[i]] = seen.get(secs[i], 0) + 1
                    out.append(i)
    return out


cache2 = {}


def run2(n, kw):
    key = (n, tuple(sorted(kw.items())))
    if key not in cache2:
        cache2[key] = weekly(lambda t: pick2(t, n=n, **kw), t1997, T)
    return cache2[key]


def report2(lab, n, kw, base_kw):
    A, Bw = run2(n, kw), run2(n, base_kw)
    d = A - Bw
    out = []
    for el, a, b in ERAS:
        a0, b0 = a - t1997, min(b, T - 1) - t1997
        x = d[a0:b0]
        blk = np.array([x[k:k+26].sum() for k in range(0, len(x) - 25, 26)])
        t_ = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk))) if len(blk) > 3 else np.nan
        out.append(f"{el} {x.mean()*52*100:+5.1f} pts/an (t {t_:4.1f})")
    print(f"  {lab:46s} " + " · ".join(out))


if __name__ == '__main__':
    print("Écart avec la sélection actuelle 4 🎯 + 1 📣 (rendement annualisé, t sur blocs de 6 mois)")
    base5 = dict(reserve=1)
    print("  bonds avec volume connu :", int((bvx > 0).sum()), "semaines-sociétés")
    report2('📣 rangé par qualité du bond', 5, dict(reserve=1, bondOrder='q'), base5)
    report2('📣 rangé par volume du bond', 5, dict(reserve=1, bondOrder='vx'), base5)
    report2('📣 de qualité seulement (≥ 2 marques), sinon 🎯', 5, dict(reserve=1, bondOrder='q', qmin=2), base5)
    report2('📣 de qualité seulement (≥ 1 marque), sinon 🎯', 5, dict(reserve=1, bondOrder='q', qmin=1), base5)
    report2('2 places 📣 rangées par qualité (3 🎯 + 2 📣)', 5, dict(reserve=2, bondOrder='q'), base5)
    base10 = dict(reserve=2)
    report2('10 lignes : 📣 rangés par qualité', 10, dict(reserve=2, bondOrder='q'), base10)
    report2('10 lignes : 📣 rangés par volume du bond', 10, dict(reserve=2, bondOrder='vx'), base10)
    # contrôle : la sélection simulée 4 🎯 + 1 📣 de pick2 = celle de pick (bond limité à 2 par secteur)
    print("  contrôle pick2 = pick :", all(pick2(t, n=5, reserve=1) == pick(t, n=5, reserve=1, bondCap=2) for t in range(t1997, T - 1, 52)))
