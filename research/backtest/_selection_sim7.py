"""Sélection simulée 1998-2026 (règles de _selection_sim.py, 4 🎯 + 1 📣, 2 par secteur) : priorité au 📣 qui casse un drapeau
(mât ≥ +30 % en 8 semaines, repos de 2 à 6 semaines sans repli de plus de 15 %, cassure du haut du mât la semaine du bond).
Écart de rendement hebdomadaire avec la règle actuelle, t sur blocs de 6 mois ; et achat différé de 1 à 4 semaines (par événement)."""
import numpy as np
exec(open('_selection_sim6.py').read().split("\nif __name__ == '__main__':")[0])
P1 = shift(P, 1)
RM = {w: shift(roll(P, w, np.nanmax), 1) for w in range(1, 11)}
Rm = {w: shift(roll(P, w, np.nanmin), 1) for w in range(1, 11)}
LO8 = roll(P, 8, np.nanmin)


def flag(pole=.30, wmin=2, wmax=6, dd=.15):
    out = np.zeros_like(P, dtype=bool); taken = np.zeros_like(P, dtype=bool)
    for w in range(1, wmax + 1):
        top = shift(P, w + 1)
        c = (P > top) & (P1 <= top) & (RM[w] <= top) & ~taken
        if w >= wmin:
            base = shift(LO8, w + 2)
            out |= c & (top / base - 1 >= pole) & (Rm[w] >= top * (1 - dd))
            taken |= c
    return out


FB = (R0 | R1) & trend & flag()                 # 📣 de la semaine qui casse un drapeau
FB3 = ago_any(FB, 4)                            # dans les 3 dernières semaines (fenêtre du 📣)
FB8 = ago_any(FB, 8)


def pick2(t, n=5, reserve=1, perSec=2, bondCap=2, fb_slot=True, fb_order=False, fb_door=False):
    ok = okn[:, t] & ~(mpn[:, t] < 1/3) & ~(v52[:, t] >= .8) & (mom[:, t] <= 2)
    strong = trend[:, t] & (s26[:, t] >= .41)
    mid = trend[:, t] & (s26[:, t] >= .14)
    bump = bp8[:, t]
    t0 = ok & strong & (mom[:, t] >= .6)
    t1 = ok & mid & (mom[:, t] >= .3) & ~t0
    promo = t1 & bump & ~wait[:, t]
    tier0 = t0 | promo
    tier1 = t1 & ~promo
    pri = 2 * hot[:, t] + bump + (4 * FB3[:, t] if fb_order else 0)

    def order(M, fb=False):
        idx = np.where(M)[0]
        keys = (-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t]), wait[idx, t], -pri[idx])
        if fb:
            keys = keys + (-FB8[idx, t].astype(int),)
        return idx[np.lexsort(keys)]
    out, seen = [], {}
    q = order(tier0).tolist() + order(tier1).tolist()
    for cap in (perSec, perSec + 1):
        for i in q:
            if len(out) >= n - reserve:
                break
            if i in out or seen.get(secs[i], 0) >= cap:
                continue
            seen[secs[i]] = seen.get(secs[i], 0) + 1
            out.append(i)
    dmask = dem[:, t] | (FB8[:, t] & trend[:, t] & (mpn[:, t] >= 1/3) & ~(v52[:, t] >= .8) & okn[:, t] if fb_door else False)
    dm = ok & dmask & ~np.isin(np.arange(N), out)
    for i in order(dm, fb=fb_slot):
        if len(out) >= n:
            break
        if seen.get(secs[i], 0) >= bondCap:
            continue
        seen[secs[i]] = seen.get(secs[i], 0) + 1
        out.append(i)
    for i in q:
        if len(out) >= n:
            break
        if i not in out and seen.get(secs[i], 0) < perSec + 1:
            seen[secs[i]] = seen.get(secs[i], 0) + 1
            out.append(i)
    return out


if __name__ == '__main__':
    okb = valid & ~(v52 >= .8)
    print("Par événement (📣 en tendance hors 🎯 qui casse un drapeau), achat différé, à 6 mois :")
    BT = FB & ~Q & okb
    ev('la semaine du bond', BT, 26)
    for k in (1, 2, 3, 4):
        ev(f'{k} semaine(s) plus tard', bshift(BT, k) & valid, 26)
    A = weekly(lambda t: pick(t, n=5, reserve=1, bondCap=2), t1997, T)
    A2 = weekly(lambda t: pick2(t, fb_slot=False), t1997, T)
    print(f"\nRègle actuelle : {A.mean() * 52 * 100:+.1f} % par an ; copie de la règle : {A2.mean() * 52 * 100:+.1f} % (contrôle)")
    for lab, kw in (('place 📣 : drapeau d\'abord', dict(fb_slot=True)),
                    ('place 📣 : drapeau d\'abord, admis jusqu\'à 7 semaines', dict(fb_slot=True, fb_door=True)),
                    ('et priorité dans l\'ordre du 🎯', dict(fb_slot=True, fb_order=True)),
                    ('tout : place, 7 semaines, ordre du 🎯', dict(fb_slot=True, fb_door=True, fb_order=True))):
        B = weekly(lambda t: pick2(t, **kw), t1997, T)
        print(f"  {lab:56s} {blocks(B - A2)}")
    n_fb = int(dedup(FB & okb, 26).sum())
    print(f"📣 qui cassent un drapeau (une fois par semestre) : {n_fb} sur la période")
