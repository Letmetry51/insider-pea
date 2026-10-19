import numpy as np
src = open('_timing2.py').read(); exec(src.split("print('référence')")[0])
hot = vx >= 1.5
print('croisement saut sur gros volume × volumes en hausse (priorité actuelle)')
for l, m in [('🔊 et saut', hot & recent), ('🔊 sans saut', hot & ~recent), ('saut sans 🔊', ~hot & recent), ('ni l\'un ni l\'autre', ~hot & ~recent)]: row(l, Q & m)
print('\nsaut ≥ +5 %% et ×2 (seuils plus larges)')
j2 = (r1 >= .05) & (VO2 >= 2 * v52); rc2 = np.zeros_like(j2)
for t in range(8, T): rc2[:, t] = np.any(j2[:, t-7:t+1], 1)
row('oui', Q & rc2); row('non', Q & ~rc2)
