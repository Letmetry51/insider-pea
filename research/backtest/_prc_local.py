"""Masque des figures ProRealCode (figures_prorealcode.py) aligné sur l'historique long : à 6 mois, ce qu'elles ajoutent à ce que
l'outil voit déjà (📣 bond, 🎯, tendance)."""
import numpy as np
exec(open('_longue_base2.py').read().split("\nif __name__ == '__main__':")[0])
zb = np.load('prc_mask.npz', allow_pickle=True)
bits, bc, bd = zb['bits'], [str(c) for c in zb['cols']], [str(d) for d in zb['dates']]
names = [str(x) for x in zb['dnames']] + [str(x) for x in zb['wnames']]
cols = [str(c) for c in z['cols']]
ci = {c: i for i, c in enumerate(bc)}; di = {d: j for j, d in enumerate(bd)}
B = np.zeros(P.shape, dtype=np.uint64)
rows = [(i, ci[c]) for i, c in enumerate(cols) if c in ci]
cj = [(t, di[str(d)]) for t, d in enumerate(dates) if str(d) in di]
ti = np.array([a for a, _ in cj]); tj = np.array([b for _, b in cj])
for i, k in rows:
    B[i, ti] = bits[k, tj]
F = {n: ((B >> np.uint64(b)) & np.uint64(1)).astype(bool) for b, n in enumerate(names)}
print(f"Masque : {len(rows)} sociétés sur {N}, {len(cj)} semaines ; figures : {len(names)}")
R0 = (r1 >= .08) & (vy >= 3); R1_ = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
BOND = (R0 | R1_)
bond4 = ago_any(BOND, 4)
okb = valid & ~(v52 >= .8) & (yr >= 2000)
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
m10x = m10 / m40 - 1
strongT = trend & (m10x > .10) & (P > m10)

if __name__ == '__main__':
    print("\n=== grande barre sur volume (semaine) face au 📣 (en tendance, hors 🎯)")
    W2 = F['grande barre sur volume ×2 (sem.)']
    ev('grande barre sur volume, semaine', okb & W2 & trend & ~Q, 26)
    ev('  … qui n\'est pas un 📣', okb & W2 & trend & ~Q & ~BOND, 26)
    ev('📣 qui est aussi une grande barre', okb & BOND & W2 & trend & ~Q, 26)
    ev('📣 sans grande barre', okb & BOND & ~W2 & trend & ~Q, 26)
    D2 = F['grande barre sur volume ×2']
    ev('grande barre sur volume, un jour de la semaine, sans 📣', okb & D2 & trend & ~Q & ~bond4, 26)
    print("\n=== 3 semaines serrées et base plate (O'Neil) : hors 🎯 face à la tendance, et dans le 🎯")
    for n in ('3 semaines serrées (sem.)', '3 semaines serrées puis cassure (sem.)', 'base plate (sem.)', 'base plate puis cassure (sem.)'):
        ev(f'{n} en tendance, hors 🎯', okb & F[n] & trend & ~Q, 26)
    ev('contrôle : en tendance, hors 🎯', okb & trend & ~Q, 26)
    ev('contrôle : forte tendance (MM10 > MM40 de 10 %, cours > MM10), hors 🎯', okb & strongT & ~Q, 26)
    ev('base plate puis cassure, forte tendance, hors 🎯', okb & F['base plate puis cassure (sem.)'] & strongT & ~Q, 26)
    for n in ('3 semaines serrées (sem.)', '3 semaines serrées puis cassure (sem.)', 'base plate (sem.)', 'base plate puis cassure (sem.)'):
        compare(f'🎯 avec {n}', Q & F[n] & okb, Q & ~F[n] & okb)
    print("\n=== méthode ascendante")
    for n in ('méthode ascendante', 'méthode ascendante (sem.)'):
        ev(f'{n}, hors 🎯', okb & F[n] & ~Q, 26)
        ev(f'{n} en tendance, hors 🎯', okb & F[n] & trend & ~Q, 26)
    print("\n=== autres figures hebdomadaires, en tendance hors 🎯 (rappel du contrôle : +0,6)")
    for n in names:
        if n.endswith('(sem.)') and not n.startswith(('grande barre sur', '3 semaines', 'base plate', 'méthode ascendante')):
            ev(f'{n}', okb & F[n] & trend & ~Q, 26)
