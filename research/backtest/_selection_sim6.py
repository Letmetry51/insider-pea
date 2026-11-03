"""Place 📣 de la sélection (4 🎯 + 1 📣, 2 par secteur) : faut-il y admettre la relance après un 📣 (cassure du plus haut atteint
depuis le bond, 2 à 6 semaines après) ? Portefeuille simulé 1998-2026 de _selection_sim.py ; écart de rendement hebdomadaire avec
la règle actuelle, t sur blocs de 6 mois, par période."""
import numpy as np
exec(open('_selection_sim2.py').read().split('print("Écart avec')[0])
BND = (R0 | R1) & trend


def relance(lo=2, hi=6):
    hiS = np.full_like(P, np.nan)
    for k in range(lo, hi + 1):
        m = bshift(BND, k)
        hk = shift(roll(P, k + 1, np.nanmax), 1)
        hiS = np.where(m & ~np.isfinite(hiS), hk, hiS)
    return np.isfinite(hiS) & (P > hiS) & ~(shift(P, 1) > hiS)


base_dem = dem.copy()
okd = trend & okn & (mpn >= 1/3) & ~(v52 >= .8)
REL = relance(2, 6)
REL2 = relance(4, 8)
variants = [
    ('📣 + relance 2-6 sem. (semaine de la cassure)', base_dem | (REL & okd)),
    ('📣 + relance 2-6 sem. (cassure dans les 2 sem.)', base_dem | (ago_any(REL, 2) & okd)),
    ('📣 + relance 4-8 sem. (semaine de la cassure)', base_dem | (REL2 & okd)),
    ('relance seule à la place du 📣', REL & okd),
]


def blocks(d):
    out = []
    for el, a, b in ERAS:
        a0, b0 = a - t1997, min(b, T - 1) - t1997
        x = d[a0:b0]
        blk = np.array([x[k:k + 26].sum() for k in range(0, len(x) - 25, 26)])
        t_ = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk))) if len(blk) > 3 else np.nan
        out.append(f"{el} {x.mean() * 52 * 100:+5.1f} pts/an (t {t_:4.1f})")
    blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
    tt = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
    return f"tout {d.mean() * 52 * 100:+5.1f} (t {tt:4.1f}) · " + " · ".join(out)


if __name__ == '__main__':
    kw = dict(reserve=1, bondCap=2)
    globals()['dem'] = base_dem
    A = weekly(lambda t: pick(t, n=5, **kw), t1997, T)
    print(f"Règle actuelle (4 🎯 + 1 📣) : {A.mean() * 52 * 100:+.1f} % par an avant marché")
    print("Écart avec la règle actuelle :")
    for lab, M in variants:
        globals()['dem'] = M
        B = weekly(lambda t: pick(t, n=5, **kw), t1997, T)
        print(f"  {lab:48s} {blocks(B - A)}")
    globals()['dem'] = base_dem
    n_rel = int((REL & okd).sum()); n_dem = int(base_dem.sum())
    print(f"semaines-sociétés : 📣 actuel {n_dem}, relance 2-6 sem. {n_rel} (dont {int((REL & okd & base_dem).sum())} déjà 📣)")
