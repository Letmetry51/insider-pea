"""Solidité de « panique puis reprise » : réglages voisins, deux moitiés de l'historique, rebond déjà fait au signal, alerte krach ;
et contrôle du repère 😟 de la page sur ses propres années (2019-2026) puis sur 2000-2026."""
import numpy as np
exec(open('_panique.py').read().split('lo4 = ')[0])
m52i = np.full(T, np.nan); m52i[52:] = idx[52:] / idx[:-52] - 1
f26 = np.array([mkt(t, 26) for t in range(T)]); f52 = np.array([mkt(t, 52) for t in range(T)])
f13 = np.array([mkt(t, 13) for t in range(T)])
print("=== Repère 😟 de la page : tiers de la part des sociétés en tendance, marché 6 mois plus tard")
for a, b in [('2019-10-25', '2026-12'), ('2000-01', '2026-12'), ('2000-01', '2013-01'), ('2013-01', '2026-12')]:
    ta, tb = int(np.searchsorted(dates, a)), int(np.searchsorted(dates, b))
    w = [t for t in range(max(ta, t1), min(tb, T)) if ok_t[t]]
    u = up_sh[w]; c1, c2 = np.percentile(u, [100/3, 200/3])
    lo_ = [f26[t] for t in w if up_sh[t] < c1 and fin(f26[t])]; mi_ = [f26[t] for t in w if c1 <= up_sh[t] <= c2 and fin(f26[t])]
    hi_ = [f26[t] for t in w if up_sh[t] > c2 and fin(f26[t])]
    print(f"  {a[:4]}-{b[:4]} : 😟 {np.mean(lo_)*100:+5.1f} % · 😐 {np.mean(mi_)*100:+5.1f} % · 😃 {np.mean(hi_)*100:+5.1f} % (semaines {len(lo_)}/{len(mi_)}/{len(hi_)})")

normal26, normal52 = np.nanmean(f26[t1:][ok_t[t1:]]), np.nanmean(f52[t1:][ok_t[t1:]])
print(f"\n=== Panique puis reprise : réglages voisins (marché, 1re semaine de chaque épisode ; normal 6 mois {normal26*100:+.1f} %, 12 mois {normal52*100:+.1f} %)")
print("  pic au plus bas · aujourd'hui · fenêtre | épisodes | 6 mois (en hausse) | 12 mois | t (6 mois vs normal) | 2000-12 / 2013-26 | rebond déjà fait (médiane)")
for pk in (.15, .20, .25):
    for nw in (.03, .05, .08):
        for W in (4, 8, 13):
            lw = np.array([lo_sh[max(0, t-W+1):t+1].max() for t in range(T)])
            eps = episodes((lw >= pk) & (lo_sh <= nw))
            e6 = np.array([f26[t] for t in eps if fin(f26[t])]); e12 = np.array([f52[t] for t in eps if fin(f52[t])])
            if len(e6) < 5:
                continue
            tt = (e6.mean() - normal26) / (e6.std(ddof=1) / np.sqrt(len(e6)))
            a1 = [f26[t] for t in eps if fin(f26[t]) and dates[t] < '2013']; a2 = [f26[t] for t in eps if fin(f26[t]) and dates[t] >= '2013']
            rb = np.median([idx[t] / idx[max(0, t-W):t+1].min() - 1 for t in eps])
            print(f"  {pk*100:3.0f} % · ≤ {nw*100:1.0f} % · {W:2d} sem. | {len(eps):2d} | {e6.mean()*100:+5.1f} % ({(e6 > 0).mean()*100:3.0f} %) | {e12.mean()*100:+5.1f} % | t {tt:4.1f} | "
                  f"{np.mean(a1)*100 if a1 else np.nan:+5.1f} ({len(a1)}) / {np.mean(a2)*100 if a2 else np.nan:+5.1f} ({len(a2)}) | {rb*100:+4.1f} %")

lo8 = np.array([lo_sh[max(0, t-7):t+1].max() for t in range(T)])
sig = (lo8 >= .20) & (lo_sh <= .05)
eps = episodes(sig)
print("\n=== Détail des 15 épisodes (réglage 20 % · ≤ 5 % · 8 sem.)")
for t in eps:
    tl = max(0, t-8) + int(np.argmin(idx[max(0, t-8):t+1]))
    print(f"  signal {dates[t]} (plus bas du marché {dates[tl]}, déjà +{(idx[t]/idx[tl]-1)*100:4.1f} %) · marché 3 mois {f13[t]*100:+5.1f} %, 6 mois {f26[t]*100:+5.1f} %, 12 mois "
          f"{f52[t]*100 if fin(f52[t]) else np.nan:+5.1f} % · un an avant {m52i[t]*100:+5.1f} %{' · alerte krach' if m52i[t] <= -.2 else ''}")

print("\n=== 🎯 à la reprise, selon l'alerte krach (marché −20 % sur un an)")
W_ = np.zeros(T, bool); W_[[t for t in range(T) if sig[t] and ok_t[t]]] = True
for lab, cond in [('sans alerte krach', ~(m52i <= -.2)), ('avec alerte krach', m52i <= -.2)]:
    M = Q & np.broadcast_to(W_ & cond, P.shape)
    e, cr, bg, n = st(M); e2 = st(M, F=fut52)
    print(f"  {lab:20s} 🎯 {e:+5.1f} pts · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n} cas · 12 mois {e2[0]:+5.1f}")
