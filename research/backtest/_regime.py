"""Les conseils liés à l'humeur du marché (😟 / 😐 / 😃, tiers de la part des sociétés en tendance) tiennent-ils sur 26 ans ?
Mesurés sur 2019-2026 par la page ; ici 2000-2026, 2000-2012, 2013-2026 et 2019-2026 (tiers calculés sur chaque période).
- société moyenne 6 mois plus tard ; 🎯 : rendement et écart avec la société moyenne ; 🚀 sortie de base + pente forte : part à +40 %."""
import numpy as np
exec(open('_panique.py').read().split('lo4 = ')[0])
fut_c = np.clip(fut, -.6, 1.5)
# 🚀 comme euro_signal/core.js : plus haut 52 sem. touché dans les 4 dernières semaines, cours d'il y a 26 sem. à plus de 25 % sous son
# plus haut d'alors (52 sem.)
hi52w = roll(P, 52, np.nanmax)
newhi = P >= hi52w * .999
base_ = shift(P, 26) / shift(hi52w, 26) < .75
brk = np.zeros_like(newhi)
for k in range(4):
    brk |= bshift(newhi & base_, k) if k else (newhi & base_)
strong = trend & (s26 >= .40)
B = valid & brk & strong
for a, b in [('2000-01', '2027'), ('2000-01', '2013'), ('2013', '2027'), ('2019-10-25', '2027')]:
    ta, tb = max(int(np.searchsorted(dates, a)), t1), min(int(np.searchsorted(dates, b)), T - 26)
    w = [t for t in range(ta, tb) if ok_t[t]]
    c1, c2 = np.percentile(up_sh[w], [100/3, 200/3])
    print(f"\n=== {a[:4]}-{b[:4] if b != '2027' else '2026'} (seuils : {c1*100:.0f} % / {c2*100:.0f} % des sociétés en tendance)")
    for lab, sel in [('😟 pessimiste', lambda t: up_sh[t] < c1), ('😐 neutre', lambda t: c1 <= up_sh[t] <= c2), ('😃 euphorique', lambda t: up_sh[t] > c2)]:
        ws = [t for t in w if sel(t)]
        m = np.zeros(T, bool); m[ws] = True; WM = np.broadcast_to(m, P.shape)
        mk6 = np.nanmean([mkt(t, 26) for t in ws])
        # 🎯 : rendement moyen (écrêté) et écart avec la société moyenne de la même semaine
        rq = [np.nanmean(fut_c[Q[:, t] & fin(fut_c[:, t]), t]) for t in ws if (Q[:, t] & fin(fut_c[:, t])).any()]
        e, cr, bg, n = st(Q & WM, ta, tb)
        nb = (B & WM).sum(); b40 = ((B & WM) & (fut >= .4)).sum() / max(nb, 1)
        all40 = ((valid & WM) & (fut >= .4)).sum() / max((valid & WM).sum(), 1)
        print(f"  {lab:14s} société moyenne {mk6*100:+5.1f} % · 🎯 {np.mean(rq)*100:+5.1f} % (écart {e:+5.1f} pts, chutes {cr:4.1f} %, {n} cas) · "
              f"🚀+⬆⬆ à +40 % : {b40*100:4.1f} % des {nb} cas (toutes : {all40*100:4.1f} %)")
