"""Solidité de « 4 🎯 + 1 📣 » : écart de rendement hebdomadaire avec la sélection actuelle (t), par période, et sur 10 lignes."""
import numpy as np
exec(open('_selection_sim.py').read().split("\nif __name__ == '__main__':")[0])
def weekly(f, a, b, hold=26, cost=.003):
    sleeves, R = [], []
    for t in range(a, min(b, T - 1)):
        s = np.array(f(t), dtype=int)
        if len(s): sleeves.append([t, s, np.ones(len(s)) / len(s)])
        sleeves = [x for x in sleeves if t - x[0] < hold]
        if not sleeves: R.append(0.0); continue
        r = 0.0
        for x in sleeves:
            rr = retw[x[1], t + 1]; r += (x[2] * rr).sum(); x[2] = x[2] * (1 + rr)
        R.append(r / len(sleeves) - cost * 2 / hold)
    return np.array(R)
cache = {}
def run(n, kw):
    key = (n, tuple(sorted(kw.items())))
    if key not in cache: cache[key] = weekly(lambda t: pick(t, n=n, **kw), t1997, T)
    return cache[key]
def report(lab, n, kw, base_kw=dict()):
    A, B = run(n, kw), run(n, base_kw)
    d = A - B
    out = []
    for el, a, b in ERAS:
        a0, b0 = a - t1997, min(b, T - 1) - t1997
        x = d[a0:b0]
        # t avec blocs de 26 semaines (rendements de tranches qui se chevauchent)
        blk = np.array([x[k:k+26].sum() for k in range(0, len(x) - 25, 26)])
        t_ = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk))) if len(blk) > 3 else np.nan
        out.append(f"{el} {x.mean()*52*100:+5.1f} pts/an (t {t_:4.1f})")
    print(f"  {lab:44s} " + " · ".join(out))
print("Écart avec la sélection actuelle (rendement hebdomadaire annualisé, t sur blocs de 6 mois)")
print("— 5 lignes")
report('4 🎯 + 1 📣', 5, dict(reserve=1))
report('📣 élargi dans l\'ordre et le repêchage', 5, dict(wide=True))
report('📣 admis au palier 0', 5, dict(door=True))
report('seuil +40 %', 5, dict(momMin=.4))
report('seuil +30 %', 5, dict(momMin=.3))
report('4 🎯 + 1 📣, et seuil +40 %', 5, dict(reserve=1, momMin=.4))
print("— 10 lignes")
report('9 🎯 + 1 📣', 10, dict(reserve=1))
report('8 🎯 + 2 📣', 10, dict(reserve=2))
report('seuil +40 %', 10, dict(momMin=.4))
