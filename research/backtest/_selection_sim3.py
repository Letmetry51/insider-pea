import numpy as np
exec(open('_selection_sim2.py').read().split('print("Écart avec')[0])
print("Note minimale pour la place 📣 (note du site ≈ note simulée + 20 points de comptes solides)")
report('4 🎯 + 1 📣 sans note minimale', 5, dict(reserve=1))
report('4 🎯 + 1 📣, note ≥ 70 (simulée ≥ 50)', 5, dict(reserve=1, demNote=50))
report('4 🎯 + 1 📣, note ≥ 60 (simulée ≥ 40)', 5, dict(reserve=1, demNote=40))
report('8 🎯 + 2 📣 sans note minimale', 10, dict(reserve=2))
report('8 🎯 + 2 📣, note ≥ 70', 10, dict(reserve=2, demNote=50))
# part des semaines où la place 📣 est occupée, et note simulée des 📣 choisies
occ, notes = [], []
for t in range(t1997, T - 1, 4):
    a = pick(t, n=5); b = pick(t, n=5, reserve=1)
    extra = [i for i in b if i not in a]
    occ.append(len(extra) > 0); notes += [note[i, t] for i in extra]
print(f"place 📣 occupée {np.mean(occ)*100:.0f} % des semaines ; note simulée des 📣 choisies : médiane {np.nanmedian(notes):.0f} (≈ {np.nanmedian(notes)+20:.0f} sur le site avec des comptes solides)")
