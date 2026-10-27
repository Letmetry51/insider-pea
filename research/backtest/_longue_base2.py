"""Suite de _longue_base.py : mesure par événement (une ligne par société et par bond, t regroupé par semestre), grille des bonds,
ce qui distingue les gagnantes, et moment d'entrée (le jour du bond ou quelques semaines après)."""
import numpy as np
exec(open('_longue_base.py').read().split('# ---------------------------------------------------------------- les événements')[0])
hi52p = shift(hi52, 1)
gap52 = P / hi52p - 1                 # au-dessus de 0 : nouveau plus haut de l'année
mkt_up = np.array([np.nanmean((P[:, t] > m40[:, t])[fin(m40[:, t])]) if fin(m40[:, t]).sum() > 30 else np.nan for t in range(T)])
FUT = {13: fut13, 26: fut, 52: fut52}


def dedup(M, k=26):
    """garde la première semaine d'une série : pas d'autre événement de la même société dans les k semaines précédentes"""
    M = M.copy()
    for i in np.where(M.any(1))[0]:
        last = -10**9
        for t in np.where(M[i])[0]:
            if t - last <= k:
                M[i, t] = False
            else:
                last = t
    return M


def evs(M, h=26):
    """excès de chaque événement (rendement écrêté − moyenne des sociétés, comme st()), avec la semaine"""
    F = FUT[h]; out = []
    for t in np.where(M.any(0))[0]:
        ok = valid[:, t] & fin(F[:, t])
        if ok.sum() < 30:
            continue
        lo_, hi_ = np.nanpercentile(F[ok, t], [2, 98]); f = np.clip(F[:, t], lo_, hi_); mm = f[ok].mean()
        for i in np.where(M[:, t] & fin(F[:, t]))[0]:
            out.append((t, i, f[i] - mm, F[i, t]))
    return out


def tcl(ex, tt):
    """t de la moyenne, écarts regroupés par semestre (les événements d'un même semestre ne sont pas indépendants)"""
    b = {}
    for e, t in zip(ex, tt):
        b.setdefault(t // 26, []).append(e)
    s = np.array([np.sum(v) for v in b.values()]); n = len(ex)
    if len(s) < 8:
        return np.nan
    m = np.mean(ex)
    res = np.array([np.sum(np.array(v) - m) for v in b.values()])
    se = np.sqrt((res ** 2).sum() * len(s) / (len(s) - 1)) / n
    return m / se


def ev(lab, M, h=26, k=26, show=True):
    M = dedup(M, k)
    E = evs(M, h)
    if len(E) < 40:
        if show:
            print(f"  {lab:62s} trop peu ({len(E)})")
        return None
    tt = np.array([e[0] for e in E]); ex = np.array([e[2] for e in E]); raw = np.array([e[3] for e in E])
    per = []
    for l, a, b in E3:
        m = (tt >= a) & (tt < b)
        per.append(f"{l} {ex[m].mean()*100:+5.1f}" if m.sum() >= 15 else f"{l}   ·  ")
    oa = ex[tt < t13 - 26].mean() * 100 if (tt < t13 - 26).sum() >= 15 else np.nan
    ob = ex[tt >= t13].mean() * 100 if (tt >= t13).sum() >= 15 else np.nan
    r = dict(n=len(E), ex=ex.mean() * 100, med=np.median(ex) * 100, win=(raw > 0).mean() * 100, beat=(ex > 0).mean() * 100,
             crash=(raw <= -.25).mean() * 100, big=(raw >= .5).mean() * 100, t=tcl(ex, tt), firms=len(set(e[1] for e in E)))
    if show:
        print(f"  {lab:62s} {r['ex']:+5.1f} pts (médiane {r['med']:+5.1f}) · en hausse {r['win']:3.0f} % · bat la moyenne {r['beat']:3.0f} % · "
              f"chutes {r['crash']:4.1f} % · ≥ +50 % {r['big']:4.1f} % · {r['n']:5d} cas | {'  '.join(per)} | 97-12 {oa:+5.1f} → 13-26 {ob:+5.1f} | t {r['t']:4.1f}")
    return r


if __name__ == '__main__':
    print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]} (mesure par événement, une société au plus une fois par semestre)")
    first_near = longbase & near & ~(shift(gap5, 1) >= -.05)
    jump10 = r1 >= .10
    base = valid & (np.arange(T)[None, :] >= W5)
    print("\n=== 1. Le tracé de Bravida (plus haut de 5 ans vieux de 2 ans ou plus, creux ≥ 35 %, retour à moins de 5 % du plus haut)")
    for h in (26, 52):
        print(f"  — à {h // 4.33:.0f} mois")
        ev('🎯 entrée (première semaine)', Q & ~bshift(ago_any(Q, 26), 1), h)
        ev('retour près du plus haut après une longue base (tous)', base & first_near, h)
        ev('  … par un bond (semaine ≥ +10 %)', base & first_near & jump10, h)
        ev('  … par un bond, volume ≥ 2×', base & first_near & jump10 & (vy >= 2), h)
        ev('  … progressif (semaine < +5 %)', base & first_near & ~(r1 >= .05), h)
    print("\n=== 2. Le bond compte-t-il plus que la base ? (bonds ≥ +10 % sur volume ≥ 2×, selon la position)")
    B = valid & jump10 & (vy >= 2)
    for h in (26, 52):
        print(f"  — à {h // 4.33:.0f} mois")
        ev('bond qui amène à moins de 5 % du plus haut de 5 ans, longue base', B & (gap5 >= -.05) & longbase, h)
        ev('bond qui amène à moins de 5 % du plus haut de 5 ans, sans longue base', B & (gap5 >= -.05) & ~longbase & (np.arange(T)[None, :] >= W5), h)
        ev('bond au plus haut de l\'année (nouveau plus haut 52 sem.)', B & (gap52 >= 0), h)
        ev('bond entre 5 et 20 % sous le plus haut de l\'année', B & (gap52 < -.05) & (gap52 >= -.2), h)
        ev('bond à plus de 20 % sous le plus haut de l\'année', B & (gap52 < -.2), h)
        ev('bond en tendance (MM10 > MM40), hors 🎯', B & trend & ~Q, h)
        ev('bond sans tendance', B & ~trend, h)
