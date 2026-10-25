"""📣 hors 🎯 : entrer la semaine du bond, ou 1 à 3, 4 à 7 semaines après (fenêtre de 8 semaines du calcul du soir) ?"""
import numpy as np
exec(open('_bond.py').read().split('cases = [')[0])
for lab, a, b in [('la semaine du bond', 0, 0), ('1 à 3 semaines après', 1, 3), ('4 à 7 semaines après', 4, 7), ('dans les 4 semaines (0 à 3)', 0, 3)]:
    M = np.zeros_like(Q)
    for k in range(a, b + 1):
        M |= bshift(bumpY, k) if k else bumpY
    line(f'📣 hors 🎯, en tendance, {lab}', valid & trend & ~Q & M)
