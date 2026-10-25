"""Le 🎯 perd les sociétés en consolidation : la pente sur 6 mois (≥ +41 %) retombe pendant la base, et la société revient seulement
quand la hausse a repris depuis longtemps (Wallenius : sortie en mai à 124, retour en septembre à 171 ; Repsol : sortie en juillet à
23, retour fin septembre à 31). Test : reprendre une ancienne 🎯 à la sortie de sa base, sans attendre que la pente se refasse."""
import numpy as np
exec(open('_sortie_base.py').read().split('print("=== 1.')[0])
ret1 = P / shift(P, 1) - 1
bump = (ret1 >= .08) & (volw >= 3)
hi13p = shift(roll(P, 13, np.nanmax), 1)
strong = valid & (mp >= 2/3) & trend & (mom >= .6) & (mom <= 2) & ~(v52 >= .8)    # 🎯 sans la pente ni ⏸️
was = bshift(ago_any(Q, 26), 1)                                                 # 🎯 dans les 6 derniers mois
flat = strong & (s26 < .41) & was                                               # ancienne 🎯 écartée par la pente seule
B13 = SB[(13, .25)] & up
B8 = SB[(8, .25)] & up
print("=== Anciennes 🎯 écartées par la pente (consolidation), écart avec la société moyenne à 6 mois")
line('🎯 (référence, toutes les semaines)', Q)
line('🎯 : semaines d\'entrée (1re semaine en 6 mois)', Q & ~bshift(ago_any(Q, 26), 1))
line('ancienne 🎯 écartée par la pente, toutes les semaines', flat)
line('  … au-dessus de la moyenne 10 semaines', flat & (P >= m10))
line('  … sortie de base 13 sem. (📦)', flat & B13)
line('  … sortie de base 8 sem. (📦)', flat & B8)
line('  … 📦 13 sem. + volume ×1,5', flat & B13 & (volw >= 1.5))
line('  … nouveau plus haut de 13 semaines', flat & (P > hi13p))
line('  … 📦 et pente encore ≥ +20 %', flat & B13 & (s26 >= .2))
print("\n  À 12 mois :")
for k, M in [('🎯 (référence)', Q), ('ancienne 🎯 écartée par la pente', flat), ('  … sortie de base 13 sem.', flat & B13), ('  … sortie de base 8 sem.', flat & B8)]:
    e, cr, bg, n = st(M, F=fut52)
    print(f"  {k:58s} {e:+5.1f} pts à 12 mois · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n} cas")
print("\n=== Sociétés pas encore 🎯 : sortie de base sur un bond (📣 semaine ≥ +8 % sur 3 fois le volume), comme Bravida en mai")
line('sortie de base 13 sem. + 📣 bond la même semaine', valid & B13 & bump)
line('  … 12 mois dans la moitié haute', valid & B13 & bump & (mp >= .5))
line('  … hors 🎯', valid & B13 & bump & ~Q)
line('📣 bond seul (toutes les sociétés en tendance)', valid & bump & trend)
print("\n=== Combien de semaines et de hausse le 🎯 perd-il à attendre la pente ?")
reQ = Q & ~bshift(Q, 1) & bshift(ago_any(Q, 26), 1)   # retour dans le 🎯 après une absence
lag_w, lag_r = [], []
for i in range(N):
    fb = np.where(flat[i] & B13[i])[0]; rq = np.where(reQ[i])[0]
    for t in fb:
        nx = rq[(rq > t) & (rq <= t + 26)]
        if len(nx):
            lag_w.append(nx[0] - t); lag_r.append(P[i, nx[0]] / P[i, t] - 1)
print(f"  sorties de base d'anciennes 🎯 suivies d'un retour dans le 🎯 en 6 mois : {len(lag_w)} ; attente médiane {np.median(lag_w):.0f} semaines ; "
      f"hausse faite pendant l'attente : médiane {np.median(lag_r)*100:+.0f} %, moyenne {np.mean(lag_r)*100:+.0f} %")
