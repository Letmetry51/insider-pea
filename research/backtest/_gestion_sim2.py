"""Compléments : même risque obtenu en gardant des liquidités ; écart momentum relatif au secteur fort − faible (semaines appariées)."""
import numpy as np
exec(open('_gestion_sim.py').read().split("\nif __name__ == '__main__':")[0])
B30 = sim_pm(stop30=True)
C = sim_pm(stop30=True, be=.10, third=.20)
k = C.std() / B30.std()
stats(B30, "règle actuelle (6 mois, protection −30 %)")
stats(C, "Comité : stop à l'entrée après +10 %, tiers à +20 % en 3 mois", B30)
stats(B30 * k, f"règle actuelle investie à {k * 100:.0f} % (même volatilité que le Comité)", None)
print(f"      écart Comité − règle actuelle à {k * 100:.0f} % : {blocks2(C - B30 * k)}")
LN = lines_of(BASE_SEL)
t_, i_ = LN[:, 0], LN[:, 1]
smed, srank = sec_strength()
rel = mom[i_, t_] - smed[i_, t_]
okr = np.isfinite(rel)
q1, q2 = np.nanpercentile(rel[okr], [100 / 3, 200 / 3])
ex = fut[i_, t_] - mk26[t_]
d = []
for t in np.unique(t_):
    m = t_ == t
    hi = ex[m & okr & (rel > q2)]
    lo = ex[m & okr & (rel <= q1)]
    if len(hi) and len(lo):
        d.append((t, hi.mean() - lo.mean()))
d = np.array(d)
for el, a, b in ERAS:
    x = d[(d[:, 0] >= a) & (d[:, 0] < b), 1]
    print(f"  fort − faible face au secteur {el} : {x.mean() * 100:+5.1f} pts (t {x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) / np.sqrt(26):4.1f}, {len(x)} semaines)")
