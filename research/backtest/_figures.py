"""Figures classiques de l'analyse technique, détectées sur les clôtures hebdomadaires (sans regarder l'avenir) : croisements des
moyennes 10 et 40 semaines (golden cross / death cross, ≈ 50 et 200 séances), double creux, tête-épaules inversée, tasse avec anse,
triangle ascendant, drapeau (et « high tight flag ») ; côté baissier : double sommet et tête-épaules. Mesure commune (une société au
plus une fois par semestre, écart avec la moyenne des sociétés, t regroupé par semestre), par période ; apport face aux contrôles
(cassure d'un plus haut de 26 semaines sans figure, 📣, entrée 🎯) ; part qui mène au 🎯 et avec quelle avance."""
import numpy as np
exec(open('_longue_base2.py').read().split("\nif __name__ == '__main__':")[0])

K = 3  # point bas / haut : extrême sur 3 semaines de part et d'autre (connu 3 semaines plus tard)


def pivots(p):
    n = len(p); lo, hi = [], []
    for t in range(K, n - K):
        w = p[t - K:t + K + 1]
        if not np.isfinite(w).all():
            continue
        if p[t] == w.min() and p[t] < p[t - 1]:
            lo.append(t)
        if p[t] == w.max() and p[t] > p[t - 1]:
            hi.append(t)
    return lo, hi


def first_break(p, start, end, level, floor=None):
    """première semaine dans [start, end] où la clôture passe au-dessus de level (la précédente en dessous) ; None si cassure
    du plancher (clôture sous floor) avant"""
    for t in range(start, min(end, len(p) - 1) + 1):
        if not np.isfinite(p[t]):
            return None
        if floor is not None and p[t] < floor:
            return None
        if p[t] > level and p[t - 1] <= level:
            return t
        if p[t] > level:          # déjà au-dessus : pas une cassure
            return None
    return None


def first_down(p, start, end, level, ceil=None):
    for t in range(start, min(end, len(p) - 1) + 1):
        if not np.isfinite(p[t]):
            return None
        if ceil is not None and p[t] > ceil:
            return None
        if p[t] < level and p[t - 1] >= level:
            return t
        if p[t] < level:
            return None
    return None


DB = np.zeros_like(P, dtype=bool); IHS = DB.copy(); CUP = DB.copy(); TRI = DB.copy(); FLAG = DB.copy(); HTF = DB.copy()
DT = DB.copy(); HS = DB.copy()
for i in range(N):
    p = P[i]
    lo, hi = pivots(p)
    hiA = np.array(hi); loA = np.array(lo)
    # double creux : deux points bas à ±5 %, 4 à 39 semaines d'écart, sommet intermédiaire ≥ 10 % au-dessus, baisse d'au moins 20 %
    # avant le premier creux ; achat à la clôture au-dessus du sommet intermédiaire (au plus 26 semaines après le 2e creux)
    for a in range(1, len(lo)):
        t1, t2 = lo[a - 1], lo[a]
        if not (4 <= t2 - t1 <= 39):
            continue
        L1, L2 = p[t1], p[t2]
        if abs(L2 / L1 - 1) > .05:
            continue
        mid = p[t1:t2 + 1]; tp = t1 + int(np.nanargmax(mid)); Hn = p[tp]
        if Hn / max(L1, L2) - 1 < .10:
            continue
        pre = p[max(0, t1 - 26):t1 + 1]
        if not (np.nanmax(pre) / L1 - 1 >= .20):
            continue
        tb = first_break(p, t2 + K, t2 + 26, Hn, floor=min(L1, L2) * .97)
        if tb is not None:
            DB[i, tb] = True
        # double sommet (miroir) traité plus bas avec les points hauts
    # tête-épaules inversée : épaules à ±10 %, tête ≥ 5 % plus basse, ligne de cou = plus haut entre les épaules
    for a in range(2, len(lo)):
        t1, t2, t3 = lo[a - 2], lo[a - 1], lo[a]
        if not (t2 - t1 >= 3 and t3 - t2 >= 3 and t3 - t1 <= 52):
            continue
        S1, Hd, S2 = p[t1], p[t2], p[t3]
        if not (Hd <= min(S1, S2) * .95 and abs(S2 / S1 - 1) <= .10):
            continue
        neck = np.nanmax(p[t1:t3 + 1])
        if neck / Hd - 1 < .15:
            continue
        pre = p[max(0, t1 - 26):t1 + 1]
        if not (np.nanmax(pre) / S1 - 1 >= .15):
            continue
        tb = first_break(p, t3 + K, t3 + 26, neck, floor=Hd)
        if tb is not None:
            IHS[i, tb] = True
    # tasse avec anse (O'Neil) : hausse ≥ 30 % dans l'année avant le bord gauche, creux de 12 à 40 %, 6 à 65 semaines, bord droit à
    # 5 % du gauche au plus, anse : repli de 3 à 15 % dans la moitié haute de la tasse, 1 à 8 semaines ; achat au-dessus du bord droit
    for a in range(len(hi)):
        tl = hi[a]; HL = p[tl]
        if tl < 52 or not np.isfinite(HL):
            continue
        prior = p[tl - 52:tl + 1]
        if not (HL / np.nanmin(prior) - 1 >= .30):
            continue
        for b in range(a + 1, len(hi)):
            tr = hi[b]
            if tr - tl > 65:
                break
            if tr - tl < 6:
                continue
            HR = p[tr]
            cup = p[tl:tr + 1]; low = np.nanmin(cup)
            depth = 1 - low / HL
            if not (.12 <= depth <= .40):
                continue
            if HR < HL * .95 or HR > HL * 1.05:
                continue
            if np.nanmax(p[tl + 1:tr]) > max(HL, HR):   # pas de plus haut au milieu
                continue
            tb = None
            for t in range(tr + 2, min(tr + 9, T - 1) + 1):
                hd = np.nanmin(p[tr + 1:t])
                if hd < HR * .85 or hd < low + .5 * (HR - low):
                    break
                if p[t] > HR and p[t - 1] <= HR:
                    if HR / hd - 1 >= .03:
                        tb = t
                    break
            if tb is not None:
                CUP[i, tb] = True
            break
    # triangle ascendant : deux points hauts à 3 % l'un de l'autre (résistance), points bas montants (+3 %) entre et avant ; 8 à 52
    # semaines ; achat au-dessus de la résistance
    for a in range(1, len(hi)):
        ta, tb_ = hi[a - 1], hi[a]
        if not (4 <= tb_ - ta <= 39):
            continue
        R = max(p[ta], p[tb_])
        if min(p[ta], p[tb_]) < R * .97:
            continue
        lows = [t for t in lo if ta - 26 <= t <= tb_]
        if len(lows) < 2:
            continue
        l_a, l_b = lows[-2], lows[-1]
        if not (p[l_b] >= p[l_a] * 1.03 and l_a < tb_ and p[l_a] <= R * .90):
            continue
        tb = first_break(p, tb_ + K, tb_ + 26, R, floor=p[l_b])
        if tb is not None:
            TRI[i, tb] = True
    # double sommet (baissier) : deux points hauts à ±5 %, creux intermédiaire ≥ 10 % en dessous, hausse ≥ 20 % avant ; vente à la
    # clôture sous le creux intermédiaire
    for a in range(1, len(hi)):
        t1, t2 = hi[a - 1], hi[a]
        if not (4 <= t2 - t1 <= 39):
            continue
        H1, H2 = p[t1], p[t2]
        if abs(H2 / H1 - 1) > .05:
            continue
        Lm = np.nanmin(p[t1:t2 + 1])
        if 1 - Lm / min(H1, H2) < .10:
            continue
        pre = p[max(0, t1 - 26):t1 + 1]
        if not (H1 / np.nanmin(pre) - 1 >= .20):
            continue
        td = first_down(p, t2 + K, t2 + 26, Lm, ceil=max(H1, H2) * 1.03)
        if td is not None:
            DT[i, td] = True
    # tête-épaules (baissier)
    for a in range(2, len(hi)):
        t1, t2, t3 = hi[a - 2], hi[a - 1], hi[a]
        if not (t2 - t1 >= 3 and t3 - t2 >= 3 and t3 - t1 <= 52):
            continue
        S1, Hd, S2 = p[t1], p[t2], p[t3]
        if not (Hd >= max(S1, S2) * 1.05 and abs(S2 / S1 - 1) <= .10):
            continue
        neck = np.nanmin(p[t1:t3 + 1])
        if 1 - neck / Hd < .15:
            continue
        td = first_down(p, t3 + K, t3 + 26, neck, ceil=Hd)
        if td is not None:
            HS[i, td] = True
# drapeaux : mât ≥ +30 % (drapeau) ou ≥ +90 % (high tight flag) en 8 semaines au plus, puis 2 à 6 semaines de repos (repli ≤ 15 % ou
# ≤ 25 %), achat à la clôture au-dessus du haut du mât
for i in range(N):
    p = P[i]
    for t in range(60, T):
        if not (np.isfinite(p[t]) and np.isfinite(p[t - 1])):
            continue
        for w in range(2, 7):                       # durée du repos
            tp = t - w - 1                          # haut du mât
            top = p[tp]
            if not np.isfinite(top) or p[t] <= top or p[t - 1] > top:
                continue
            rest = p[tp + 1:t]
            if not np.isfinite(rest).all() or rest.max() > top:
                continue
            dd = 1 - rest.min() / top
            base = np.nanmin(p[tp - 8:tp])
            pole = top / base - 1
            if pole >= .90 and dd <= .25:
                HTF[i, t] = True
            if pole >= .30 and dd <= .15:
                FLAG[i, t] = True
            break

GC = (m10 > m40) & (shift(m10, 1) <= shift(m40, 1))
DC = (m10 < m40) & (shift(m10, 1) >= shift(m40, 1))
up40 = m40 > shift(m40, 4)
hi26p = shift(roll(P, 26, np.nanmax), 1)
BRK = (P > hi26p) & ~bshift(ago_any(P > hi26p, 13), 1)       # cassure d'un plus haut de 26 semaines, première en 3 mois
R0 = (r1 >= .08) & (vy >= 3); R1_ = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
BOND = (R0 | R1_) & trend & ~Q
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
held = ago_any(Q, 26)                                        # 🎯 dans les 6 derniers mois (ligne en portefeuille)
okb = valid & ~(v52 >= .8)
lead = np.zeros_like(Q)
for k2 in range(1, 27):
    lead |= blead(Qentry, k2)


def suite(lab, M):
    F = dedup(M, 26); n = F.sum()
    if n < 40:
        return
    ws = []
    for i, t in zip(*np.where(F)):
        nx = np.where(Qentry[i, t + 1:t + 27])[0]
        if len(nx):
            ws.append(nx[0] + 1)
    print(f"  {lab:62s} {n:6d} cas · mène au 🎯 dans les 6 mois : {len(ws) / n * 100:3.0f} % (médiane {np.median(ws) if ws else np.nan:.0f} semaines)")


if __name__ == '__main__':
    print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]}")
    pats = [('golden cross (MM10 passe au-dessus de MM40)', okb & GC),
            ('  … MM40 montante', okb & GC & up40),
            ('  … cours au-dessus des deux moyennes', okb & GC & (P > m10) & (P > m40)),
            ('double creux (cassure de la ligne de cou)', okb & DB),
            ('tête-épaules inversée (cassure)', okb & IHS),
            ('tasse avec anse (cassure du bord droit)', okb & CUP),
            ('  … volume ≥ 1,4× (O\'Neil)', okb & CUP & (vy >= 1.4)),
            ('triangle ascendant (cassure de la résistance)', okb & TRI),
            ('drapeau (mât ≥ +30 %, repos ≤ 15 %)', okb & FLAG),
            ('high tight flag (mât ≥ +90 %, repos ≤ 25 %)', okb & HTF)]
    ctrl = [('contrôle : cassure d\'un plus haut de 26 semaines (toutes)', okb & BRK),
            ('contrôle : 📣 bond en tendance hors 🎯', okb & BOND),
            ('contrôle : entrée 🎯', Qentry)]
    for h in (13, 26, 52):
        print(f"\n=== haussières, à {h // 4.33:.0f} mois")
        for lab, M in pats + ctrl:
            ev(lab, M, h)
    print("\n=== haussières : apport face à une cassure de plus haut sans figure (même semaine, à 6 mois)")
    for lab, M in pats[3:]:
        ev(lab + ' — avec cassure de plus haut 26 sem.', M & BRK, 26)
    ev('cassure de plus haut 26 sem. sans aucune figure', okb & BRK & ~(DB | IHS | CUP | TRI | FLAG | HTF), 26)
    print("\n=== haussières hors 🎯 / dans le 🎯 (à 6 mois)")
    for lab, M in pats:
        ev(lab + ' — hors 🎯', M & ~Q, 26)
        ev(lab + ' — dans le 🎯', M & Q, 26)
    print("\n=== suite : part qui mène au 🎯")
    for lab, M in pats + ctrl[:2]:
        suite(lab, M & ~Q)
    print("\n=== baissières, à 3 et 6 mois (toutes, puis lignes 🎯 des 6 derniers mois)")
    for h in (13, 26):
        print(f"  — à {h // 4.33:.0f} mois")
        ev('death cross (MM10 passe sous MM40)', okb & DC, h)
        ev('double sommet (cassure)', okb & DT, h)
        ev('tête-épaules (cassure)', okb & HS, h)
        ev('death cross, ligne 🎯 des 6 derniers mois', DC & held, h)
        ev('double sommet, ligne 🎯 des 6 derniers mois', DT & held, h)
        ev('tête-épaules, ligne 🎯 des 6 derniers mois', HS & held, h)
        ev('contrôle : ligne 🎯 des 6 derniers mois, hors 🎯 aujourd\'hui', held & ~Q & valid, h)
    np.savez_compressed('figures.npz', DB=DB, IHS=IHS, CUP=CUP, TRI=TRI, FLAG=FLAG, HTF=HTF, DT=DT, HS=HS)
