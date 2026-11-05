"""Volumes des 5 dernières séances (05/11/2026, question de François) : le volume de la semaine face à la moyenne de l'année, et sa
tendance (semaine face aux 4 précédentes), selon que la semaine monte ou baisse, disent-ils quelque chose de la suite ? Clôtures et
volumes hebdomadaires 1998-2026 ; sociétés en tendance (hors tiers faible sur 12 mois) et lignes de la sélection simulée ; écart à 1 et
6 mois avec le marché équipondéré."""
import numpy as np
exec(open('_gestion_sim.py').read().split("\nif __name__ == '__main__':")[0])
vyr = VO / shift(sma(VO, 52), 1)                       # volume de la semaine / moyenne de l'année précédente
v4 = VO / shift(sma(VO, 4), 1)                         # semaine / moyenne des 4 semaines précédentes (tendance)
F4 = np.full((N, T), np.nan)
F4[:, :T - 4] = np.exp(L[:, 4:] - L[:, :T - 4]) - 1
mk4 = np.full(T, np.nan)
mk4[:T - 4] = np.exp(LM[4:] - LM[:T - 4]) - 1
base = okn & trend & (mpn >= 1 / 3) & np.isfinite(vyr) & np.isfinite(r1)
bond = (r1 >= .08) & (vyr >= 3)


def cell(lab, M, a=t1997, b=T - H):
    out = []
    for F, mk, h in ((F4, mk4, 4), (fut, mk26, 26)):
        ex = []
        for t in range(a, b):
            m = M[:, t] & np.isfinite(F[:, t])
            if m.sum():
                ex.append(np.nanmean(F[m, t]) - mk[t])
        ex = np.array(ex)
        tt = ex.mean() / (ex.std(ddof=1) / np.sqrt(len(ex))) / np.sqrt(h) if len(ex) > 10 else np.nan
        out.append(f"{ex.mean() * 100:+5.1f} (t {tt:4.1f})")
    n = int(M[:, a:b].sum())
    per = []
    for el, a2, b2 in ERAS[:3]:
        ex = [np.nanmean(fut[M[:, t] & np.isfinite(fut[:, t]), t]) - mk26[t] for t in range(max(a, a2), min(b, b2)) if (M[:, t] & np.isfinite(fut[:, t])).any()]
        per.append(f"{el} {np.mean(ex) * 100:+5.1f}" if len(ex) > 10 else f"{el}   ·")
    print(f"  {lab:52s} 1 mois {out[0]} · 6 mois {out[1]} · n={n:6d} · " + " · ".join(per))


print("Sociétés en tendance (hors tiers faible), semaine sans bond 📣, selon le volume de la semaine face à la moyenne de l'année")
cell("toutes (référence)", base & ~bond)
for lo, hi, nm in ((0, .7, '< 0,7 (semaine calme)'), (.7, 1.3, '0,7-1,3 (habituel)'), (1.3, 2, '1,3-2'), (2, 3, '2-3'), (3, 99, '≥ 3')):
    for up, s in ((True, 'en hausse'), (False, 'en baisse')):
        cell(f"volume {nm}, semaine {s}", base & ~bond & (vyr >= lo) & (vyr < hi) & ((r1 > 0) if up else (r1 <= 0)))
print("\nTendance des volumes : semaine face aux 4 précédentes (sans bond)")
for lo, hi, nm in ((0, .7, 'en net recul (< 0,7)'), (.7, 1.3, 'stable'), (1.3, 2, 'en hausse (1,3-2)'), (2, 99, 'en forte hausse (≥ 2)')):
    for up, s in ((True, 'cours en hausse'), (False, 'cours en baisse')):
        cell(f"volumes {nm}, {s}", base & ~bond & (v4 >= lo) & (v4 < hi) & ((r1 > 0) if up else (r1 <= 0)))
print("\nLignes de la sélection simulée (4 🎯 + 1 📣) le jour de l'achat, selon le volume de la semaine")
SM = np.zeros((N, T), bool)
for t, s in BASE_SEL.items():
    SM[np.array(s, dtype=int), t] = True
cell("toutes les lignes", SM)
for lo, hi, nm in ((0, .7, '< 0,7'), (.7, 1.3, '0,7-1,3'), (1.3, 2, '1,3-2'), (2, 99, '≥ 2')):
    cell(f"volume de la semaine {nm}", SM & (vyr >= lo) & (vyr < hi))
for up, s in ((True, 'volumes en hausse sur 4 semaines (≥ 1,3), cours en baisse'), (False, '')):
    if s:
        cell(s, SM & (v4 >= 1.3) & (r1 <= 0))
cell("volumes en recul (< 0,7 des 4 semaines), cours en baisse", SM & (v4 < .7) & (r1 <= 0))
