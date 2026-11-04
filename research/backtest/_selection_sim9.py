"""Place 📣 de la sélection et bond du jour (04/11/2026) : la place 📣 (4 🎯 + 1 📣) prend-elle de meilleures sociétés si l'on compte
aussi le bond d'une séance (+8 % sur 5 fois le volume de 50 séances, en tendance), ou s'il passe en premier ? Portefeuille simulé
1998-2026 de _selection_sim.py (achat le lundi : l'avance du jour n'est pas comptée ici). Masque : research/hausse_tot4.py."""
import numpy as np
exec(open('_selection_sim7.py').read().split("\nif __name__ == '__main__':")[0])
zj = np.load('jour_mask.npz', allow_pickle=True)
bits, bc, bd = zj['bits'], [str(c) for c in zj['cols']], [str(d) for d in zj['dates']]
cols = [str(c) for c in z['cols']]
ci = {c: i for i, c in enumerate(bc)}; di = {d: j for j, d in enumerate(bd)}
J = np.zeros(P.shape, dtype=np.uint32)
rows = [(i, ci[c]) for i, c in enumerate(cols) if c in ci]
cj = [(t, di[str(d)]) for t, d in enumerate(dates) if str(d) in di]
ti = np.array([a for a, _ in cj]); tj = np.array([b for _, b in cj])
for i, k in rows:
    J[i, ti] = bits[k, tj]
A5, A3, AHI, A67 = (((J >> np.uint32(b)) & np.uint32(1)).astype(bool) for b in range(4))
okd = trend & okn & (mpn >= 1/3) & ~(v52 >= .8)
base_dem = dem.copy()


def run_with(dmask=None, first=None):
    globals()['dem'] = base_dem if dmask is None else dmask
    if first is None:
        return weekly(lambda t: pick(t, n=5, reserve=1, bondCap=2), t1997, T)
    globals()['FB8'] = first
    return weekly(lambda t: pick2(t, fb_slot=True), t1997, T)


if __name__ == '__main__':
    print(f"Masque : {len(rows)} sociétés sur {N} ; bonds du jour (+8 % ×5) : {int(A5.sum())} semaines")
    okb = valid & ~(v52 >= .8)
    ev('bond du jour +8 % ×5 en tendance, hors 🎯 (semaine)', okb & A5 & ~Q, 26)
    ev('📣 de la semaine en tendance, hors 🎯', okb & (R0 | R1) & trend & ~Q, 26)
    A0 = run_with()
    print(f"Règle actuelle : {A0.mean() * 52 * 100:+.1f} % par an")
    for lab, kw in (('📣 ou bond du jour (+8 % ×5) dans les 3 semaines', dict(dmask=base_dem | (ago_any(A5, 4) & okd))),
                    ('📣 ou bond du jour au plus haut (+8 % ×5)', dict(dmask=base_dem | (ago_any(AHI, 4) & okd))),
                    ('bond du jour d\'abord dans la place 📣', dict(first=ago_any(A5, 4) & okd)),
                    ('bond du jour au plus haut d\'abord', dict(first=ago_any(AHI, 4) & okd)),
                    ('bond du jour seul dans la place 📣', dict(dmask=ago_any(A5, 4) & okd))):
        B = run_with(**kw)
        print(f"  {lab:52s} {blocks(B - A0)}")
    globals()['dem'] = base_dem
