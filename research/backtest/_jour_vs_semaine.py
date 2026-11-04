"""📣 de la semaine avec ou sans bond du jour dans la même semaine (04/11/2026) : que perdrait-on à ne garder que l'alerte du jour ?"""
import numpy as np
exec(open('_selection_sim9.py').read().split("\nif __name__ == '__main__':")[0])
okb = valid & ~(v52 >= .8) & (yr >= 2000)
BT = okb & (R0 | R1) & trend & ~Q
A5w = A5 | bshift(A5, 1)          # bond du jour cette semaine ou la précédente (le 📣 de la semaine peut venir juste après)
print(f"📣 de la semaine (2000-2026, en tendance, hors 🎯) : {int(BT.sum())} semaines ; avec un bond du jour la même semaine ou la précédente : "
      f"{(BT & A5w).sum() / BT.sum() * 100:.0f} %")
for h in (26, 52):
    ev(f'📣 de la semaine, tous (à {h} sem.)', BT, h)
    ev(f'  … avec un bond du jour (+8 % ×5) la même semaine ou la précédente', BT & A5w, h)
    ev(f'  … sans bond du jour : ce que l\'alerte du jour seule raterait', BT & ~A5w, h)
F = dedup(BT, 26); G = dedup(BT & ~A5w, 26)
print('📣 par an (une fois par semestre et par société) :', round(F.sum() / 27), '; sans bond du jour :', round(G.sum() / 27))
