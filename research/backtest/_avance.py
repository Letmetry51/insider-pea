"""Signaux qui précèdent le prix (27/10/2026) : force relative au plus haut de l'année avant le cours, meneuses pendant une baisse
du marché, accumulation (volumes des semaines de hausse / de baisse), volume cumulé (OBV) au plus haut avant le cours.
Mesure par événement (une société au plus une fois par semestre, écart avec la moyenne des sociétés), et avance sur 📣 et 🎯."""
import numpy as np
exec(open('_longue_base2.py').read().split("if __name__ == '__main__':")[0])

hi52p = shift(hi52, 1)
gap52 = P / hi52p - 1
RSp = shift(roll(RS, 52, np.nanmax), 1)
rs_new = RS >= RSp                                        # force relative (cours / indice des sociétés) au plus haut de l'année
midx = idx / np.maximum.accumulate(idx)                   # recul de l'indice depuis son plus haut
mdd = np.array([idx[t] / idx[max(0, t - 51):t + 1].max() - 1 for t in range(T)])[None, :] * np.ones((N, 1))
up_w = np.where(r1 > 0, VO, 0.0); dn_w = np.where(r1 < 0, VO, 0.0)
up_w[~fin(VO) | ~fin(r1)] = np.nan; dn_w[~fin(VO) | ~fin(r1)] = np.nan
ud13 = roll(up_w, 13, np.nansum) / roll(dn_w, 13, np.nansum)
obv = np.nancumsum(np.where(fin(r1) & fin(VO), np.sign(r1) * VO, 0.0), 1)
obv_new = obv >= shift(roll(obv, 52, np.nanmax), 1)
R0 = (r1 >= .08) & (vy >= 3); R1 = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
bond = ago_any(R0 | R1, 4)
base = valid & ~(mp < 1/3) & ~(v52 >= .8)
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
S = {
    'force relative au plus haut, cours 3 à 25 % sous le sien': base & rs_new & (gap52 < -.03) & (gap52 >= -.25),
    '  … en tendance, hors 🎯': base & rs_new & (gap52 < -.03) & (gap52 >= -.25) & trend & ~Q,
    'meneuse : marché ≥ 10 % sous son plus haut, cours à moins de 5 % du sien': base & (mdd <= -.10) & (gap52 >= -.05),
    '  … hors 🎯': base & (mdd <= -.10) & (gap52 >= -.05) & ~Q,
    '  … force relative au plus haut pendant la baisse': base & (mdd <= -.10) & rs_new,
    'accumulation : volumes hausse/baisse ≥ 2 sur 13 sem., à moins de 15 % du plus haut, hors 🎯': base & (ud13 >= 2) & (gap52 >= -.15) & ~Q,
    '  … ≥ 1,5': base & (ud13 >= 1.5) & (gap52 >= -.15) & ~Q,
    'OBV au plus haut de l\'année, cours ≥ 5 % sous le sien, hors 🎯': base & obv_new & (gap52 < -.05) & ~Q,
    '  … en tendance': base & obv_new & (gap52 < -.05) & ~Q & trend,
}
if __name__ == '__main__':
    print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]}")
    for h in (26, 52):
        print(f"\n=== à {h // 4.33:.0f} mois (une entrée par société et par semestre)")
        ev('🎯 entrée (référence)', Qentry, h)
        ev('📣 démarrage (référence)', base & (R0 | R1) & trend & ~Q, h)
        for k, M in S.items():
            ev(k, M, h)
    print("\n=== avance : part des signaux suivis d'un 📣 ou d'une entrée 🎯 dans les 6 mois, et hausse faite d'ici là (médiane)")
    led_q = np.zeros_like(Q); led_b = np.zeros_like(Q)
    for k2 in range(1, 27):
        led_q |= blead(Qentry, k2); led_b |= blead(R0 | R1, k2)
    for k, M in S.items():
        F = dedup(M, 26)
        n = F.sum()
        gains = []
        for i, t in zip(*np.where(F)):
            q = np.where(Qentry[i, t + 1:t + 27])[0]
            if len(q):
                gains.append(P[i, t + 1 + q[0]] / P[i, t] - 1)
        print(f"  {k:62s} {n:5d} signaux · 📣 ensuite {(F & led_b).sum() / max(n, 1) * 100:3.0f} % · 🎯 ensuite {(F & led_q).sum() / max(n, 1) * 100:3.0f} %"
              f" · hausse avant l'entrée 🎯 {np.median(gains) * 100 if gains else float('nan'):+4.0f} %")
