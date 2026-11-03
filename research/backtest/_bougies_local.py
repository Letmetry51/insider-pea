"""Masque des chandeliers (figures_bougies.py, lancé sur GitHub) aligné sur l'historique long : à 6 mois, mesure commune ; les
bougies changent-elles la valeur d'un 📣 ou d'une entrée 🎯 ? (clôture de la semaine du bond près du plus haut ou non, mèche haute)"""
import numpy as np
exec(open('_longue_base2.py').read().split("\nif __name__ == '__main__':")[0])
zb = np.load('bougies_mask.npz', allow_pickle=True)
bits, bc, bd = zb['bits'], [str(c) for c in zb['cols']], [str(d) for d in zb['dates']]
names, dnames = [str(x) for x in zb['names']], [str(x) for x in zb['dnames']]
cols = [str(c) for c in z['cols']]
ci = {c: i for i, c in enumerate(bc)}; di = {d: j for j, d in enumerate(bd)}
B = np.zeros(P.shape, dtype=np.uint32)
rows = [(i, ci[c]) for i, c in enumerate(cols) if c in ci]
cj = [(t, di[str(d)]) for t, d in enumerate(dates) if str(d) in di]
ti = np.array([a for a, _ in cj]); tj = np.array([b for _, b in cj])
for i, k in rows:
    B[i, ti] = bits[k, tj]
print(f"Masque : {len(rows)} sociétés sur {N} retrouvées, {len(cj)} semaines communes")


def bit(b):
    return ((B >> np.uint32(b)) & np.uint32(1)).astype(bool)


W = {n: bit(b) for b, n in enumerate(names)}            # bougies de la semaine
Dd = {n: bit(16 + b) for b, n in enumerate(dnames)}     # bougie journalière dans la semaine
okw = bit(30)
clvq = ((B >> np.uint32(28)) & np.uint32(3)).astype(int)
R0 = (r1 >= .08) & (vy >= 3); R1_ = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
BOND = (R0 | R1_) & trend & ~Q
okb = valid & ~(v52 >= .8)
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
yr0 = yr >= 2000

if __name__ == '__main__':
    print("\n=== 📣 bond en tendance hors 🎯 (2000-2026), selon la bougie de la semaine du bond")
    ev('📣 tous', okb & BOND & yr0, 26)
    for q in range(4):
        ev(f'📣 clôture dans le {q + 1}e quart de la fourchette de la semaine', okb & BOND & okw & (clvq == q) & yr0, 26)
    ev('📣 avec étoile filante (mèche haute) dans la semaine', okb & BOND & (Dd['étoile filante'] | W['étoile filante']) & yr0, 26)
    ev('📣 avec avalement baissier dans la semaine', okb & BOND & Dd['avalement baissier'] & yr0, 26)
    print("\n=== entrée 🎯 selon la bougie de la semaine")
    ev('entrée 🎯 tous', Qentry & yr0, 26)
    for q in range(4):
        ev(f'entrée 🎯, clôture dans le {q + 1}e quart', Qentry & okw & (clvq == q) & yr0, 26)
    print("\n=== bougies haussières en tendance (hors 🎯), à 6 mois")
    for n in ('marteau', 'avalement haussier', 'étoile du matin', 'trois soldats blancs'):
        ev(f'{n} (semaine) en tendance, hors 🎯', okb & W[n] & trend & ~Q & yr0, 26)
        ev(f'{n} (jour) en tendance, hors 🎯', okb & Dd[n] & trend & ~Q & yr0, 26)
    ev('contrôle : en tendance, hors 🎯', okb & trend & ~Q & yr0, 26)
    print("\n=== dans le 🎯 : semaine avec une bougie baissière contre les autres 🎯")
    for n in ('étoile filante', 'avalement baissier', 'étoile du soir', 'trois corbeaux noirs'):
        compare(f'🎯 avec {n} (jour) cette semaine', Q & Dd[n] & yr0, Q & ~Dd[n] & yr0)
