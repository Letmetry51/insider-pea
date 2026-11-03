"""Figures de la bibliothèque ProRealCode sur les clôtures hebdomadaires 1997-2026 (03/11/2026) : figures harmoniques (Gartley,
Chauve-souris, Papillon, Crabe, ABCD : rapports de Fibonacci entre points bas et hauts successifs, tolérance ±0,05), vagues de Wolfe,
cassure du nuage d'Ichimoku (calculé sur les clôtures). Points bas et hauts : extrêmes sur 3 semaines de part et d'autre, connus 3
semaines plus tard : l'achat se fait à cette date (sans regarder l'avenir) ; variante « zone de retournement » : achat dès que le
cours entre dans la zone du point D, une fois X, A, B et C connus. Mesure commune (_longue_base2.py)."""
import numpy as np
exec(open('_figures.py').read().split("\nif __name__ == '__main__':")[0].split("\nDB = np.zeros_like")[0])

TOL = .05
HARM = {  # AB/XA, BC/AB, AD/XA (retracement du point D), CD/BC
    'Gartley': ((.618 - TOL, .618 + TOL), (.382, .886), (.786 - TOL, .786 + TOL), (1.13, 1.618)),
    'Chauve-souris': ((.382, .50), (.382, .886), (.886 - TOL, .886 + TOL), (1.618, 2.618)),
    'Papillon': ((.786 - TOL, .786 + TOL), (.382, .886), (1.27, 1.618), (1.618, 2.24)),
    'Crabe': ((.382, .618), (.382, .886), (1.618 - TOL, 1.618 + TOL), (2.24, 3.618)),
}


def zigzag(p):
    """points bas et hauts alternés : [(t, prix, +1 haut / -1 bas)], deux du même type de suite : le plus extrême gardé"""
    lo, hi = pivots(p)
    ev = sorted([(t, p[t], -1) for t in lo] + [(t, p[t], 1) for t in hi])
    out = []
    for e in ev:
        if out and out[-1][2] == e[2]:
            if (e[2] == 1 and e[1] > out[-1][1]) or (e[2] == -1 and e[1] < out[-1][1]):
                out[-1] = e
            continue
        out.append(e)
    return out


def inr(x, r):
    return r[0] <= x <= r[1]


M_H = {k: np.zeros_like(P, dtype=bool) for k in list(HARM) + ['ABCD', 'tout point bas après X-A-B-C (contrôle)']}
M_PRZ = np.zeros_like(P, dtype=bool)
WOLFE = np.zeros_like(P, dtype=bool)
for i in range(N):
    p = P[i]
    z = zigzag(p)
    for j in range(4, len(z)):
        X, A, B, Cc, Dd = z[j - 4:j + 1]
        if Dd[2] != -1:
            continue
        t_conf = Dd[0] + K
        if t_conf >= T:
            continue
        xa = A[1] - X[1]
        ab = A[1] - B[1]
        bc = Cc[1] - B[1]
        cd = Cc[1] - Dd[1]
        if xa <= 0 or ab <= 0 or bc <= 0 or cd <= 0:
            continue
        M_H['tout point bas après X-A-B-C (contrôle)'][i, t_conf] = True
        r_ab, r_bc, r_ad, r_cd = ab / xa, bc / ab, (A[1] - Dd[1]) / xa, cd / bc
        for k, (a, b, c, d) in HARM.items():
            if inr(r_ab, a) and inr(r_bc, b) and inr(r_ad, c) and inr(r_cd, d):
                M_H[k][i, t_conf] = True
        if inr(r_bc, (.618, .786)) and inr(r_cd, (1.27, 1.618)) and abs(cd - ab) <= .1 * ab:   # ABCD sur A-B-C-D
            M_H['ABCD'][i, t_conf] = True
    # zone de retournement : X, A, B, C connus (C confirmé), achat à la première clôture dans la zone D d'une des 4 figures
    for j in range(3, len(z)):
        X, A, B, Cc = z[j - 3:j + 1]
        if not (X[2] == -1 and Cc[2] == 1):
            continue
        xa, ab, bc = A[1] - X[1], A[1] - B[1], Cc[1] - B[1]
        if xa <= 0 or ab <= 0 or bc <= 0:
            continue
        r_ab, r_bc = ab / xa, bc / ab
        zones = []
        for k, (a, b, c, d) in HARM.items():
            if inr(r_ab, a) and inr(r_bc, b):
                lo_d, hi_d = A[1] - c[1] * xa, A[1] - c[0] * xa       # niveaux du point D (retracement de XA)
                lo_e, hi_e = Cc[1] - d[1] * bc, Cc[1] - d[0] * bc     # et extension de BC
                zl, zh = max(lo_d, lo_e), min(hi_d, hi_e)
                if zl < zh:
                    zones.append((zl, zh))
        if not zones:
            continue
        nxt = z[j + 1][0] if j + 1 < len(z) else T
        for t in range(Cc[0] + K, min(T, Cc[0] + K + 26)):
            if not np.isfinite(p[t]) or p[t] > Cc[1]:
                break
            if any(zl <= p[t] <= zh for zl, zh in zones):
                M_PRZ[i, t] = True
                break
    # vagues de Wolfe (haussières) : 1 bas, 2 haut, 3 bas sous 1, 4 haut sous 2 et au-dessus de 1, 5 bas sous 3 et sous la droite 1-3
    for j in range(4, len(z)):
        w1, w2, w3, w4, w5 = z[j - 4:j + 1]
        if w1[2] != -1:
            continue
        if not (w3[1] < w1[1] and w4[1] < w2[1] and w4[1] > w1[1] and w5[1] < w3[1]):
            continue
        slope = (w3[1] - w1[1]) / (w3[0] - w1[0])
        if w5[1] <= w3[1] + slope * (w5[0] - w3[0]) and w5[0] + K < T:
            WOLFE[i, w5[0] + K] = True

# nuage d'Ichimoku sur les clôtures hebdomadaires (9, 26, 52 semaines, nuage décalé de 26)
mx = {k: roll(P, k, np.nanmax) for k in (9, 26, 52)}
mn = {k: roll(P, k, np.nanmin) for k in (9, 26, 52)}
tenkan, kijun = (mx[9] + mn[9]) / 2, (mx[26] + mn[26]) / 2
SA, SB = shift((tenkan + kijun) / 2, 26), shift((mx[52] + mn[52]) / 2, 26)
top = np.fmax(SA, SB)
KUMO = (P > top) & (shift(P, 1) <= shift(top, 1))
KUMO_F = KUMO & (tenkan > kijun) & (P > shift(P, 26))                # avec Tenkan au-dessus de Kijun et Chikou au-dessus du cours
okb = valid & ~(v52 >= .8)

if __name__ == '__main__':
    print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]} ; écart avec la moyenne des sociétés, une entrée par société et par semestre")
    for h in (26, 52):
        print(f"\n=== à {h // 4.33:.0f} mois")
        for k, M in M_H.items():
            ev(f'{k} (point D confirmé)', okb & M, h)
        ev('harmonique : achat dans la zone D (avant confirmation)', okb & M_PRZ, h)
        ev('vague de Wolfe haussière (point 5 confirmé)', okb & WOLFE, h)
        ev('Ichimoku : cours qui passe au-dessus du nuage', okb & KUMO, h)
        ev('  … avec Tenkan > Kijun et Chikou au-dessus', okb & KUMO_F, h)
        ev('contrôle : en tendance, hors 🎯', okb & trend & ~Q, h)
    print("\n=== en tendance, hors 🎯 (à 6 mois)")
    for k, M in M_H.items():
        ev(f'{k} en tendance', okb & M & trend & ~Q, 26)
    ev('zone D en tendance', okb & M_PRZ & trend & ~Q, 26)
    ev('Wolfe en tendance', okb & WOLFE & trend & ~Q, 26)
    ev('Ichimoku (complet) hors 🎯', okb & KUMO_F & ~Q, 26)
    np.savez_compressed('figures_prc.npz', gartley=M_H['Gartley'], bat=M_H['Chauve-souris'], butterfly=M_H['Papillon'],
                        crab=M_H['Crabe'], abcd=M_H['ABCD'], ctl=M_H['tout point bas après X-A-B-C (contrôle)'], prz=M_PRZ, wolfe=WOLFE,
                        kumo=KUMO, kumo_f=KUMO_F)
