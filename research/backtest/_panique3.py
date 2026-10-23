"""La part des sociétés au plus bas de l'année (« thermomètre de panique ») : à quoi sert-elle ?
A. ce que fait le marché après une semaine de panique, comparé à une semaine quelconque (y compris la baisse supplémentaire) ;
B. le 🎯 pendant une panique ; C. les positions achetées dans les 6 derniers mois : garder ou vendre pendant la panique ;
D. une société à son plus bas de l'année pendant une panique générale, ou seule à son plus bas (marché calme)."""
import numpy as np
exec(open('_panique.py').read().split('lo4 = ')[0])
fut_c = np.clip(fut, -.6, 1.5)
f13 = np.full_like(P, np.nan); f13[:, :-13] = np.clip(P[:, 13:] / P[:, :-13] - 1, -.6, 1.5)
allw = [t for t in range(t1, T - 26) if ok_t[t]]
for lab, cond in [('toutes les semaines', lambda t: True), ('calme (< 10 % au plus bas)', lambda t: lo_sh[t] < .10),
                  ('agité (10 à 20 %)', lambda t: .10 <= lo_sh[t] < .20), ('panique (≥ 20 %)', lambda t: lo_sh[t] >= .20)]:
    ws = [t for t in allw if cond(t)]
    dd = np.array([idx[t:t + 27].min() / idx[t] - 1 for t in ws])
    m13 = np.nanmean([mkt(t, 13) for t in ws]); m26 = np.nanmean([mkt(t, 26) for t in ws])
    nq = np.mean([Q[:, t].sum() for t in ws])
    print(f"A. {lab:28s} {len(ws):4d} sem. | marché 3 mois {m13*100:+5.1f} %, 6 mois {m26*100:+5.1f} % | baisse de plus dans les 6 mois : "
          f"médiane {np.median(dd)*100:+5.1f} %, 1 fois sur 10 pire que {np.percentile(dd, 10)*100:+5.1f} %, ≥ 10 % de plus : {np.mean(dd <= -.10)*100:3.0f} % | 🎯 par semaine {nq:5.1f}")
W = lambda cond: np.broadcast_to(np.array([ok_t[t] and cond(t) for t in range(T)]), P.shape)
PAN, CALM, MID = W(lambda t: lo_sh[t] >= .20), W(lambda t: lo_sh[t] < .10), W(lambda t: .10 <= lo_sh[t] < .20)
print("\nB. 🎯 (écart avec la société moyenne, 6 mois)")
for lab, M in [('calme', CALM), ('agité', MID), ('panique', PAN)]:
    e, cr, bg, n = st(Q & M); print(f"   {lab:8s} {e:+5.1f} pts · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n} cas")
held = valid & ago_any(Q, 26)          # positions : sociétés passées par le 🎯 dans les 6 derniers mois
print("\nC. Positions (🎯 dans les 6 derniers mois) : rendement des 3 et 6 mois suivants (garder) ; vendre = 0")
for lab, M in [('calme', CALM), ('agité', MID), ('panique', PAN)]:
    m = held & M
    a13 = np.nanmean(f13[m]); a26 = np.nanmean(fut_c[m]); pos13 = np.nanmean(f13[m][fin(f13[m])] > 0)
    e, cr, bg, n = st(m)
    print(f"   {lab:8s} 3 mois {a13*100:+5.1f} % (en hausse {pos13*100:3.0f} %), 6 mois {a26*100:+5.1f} % · écart avec la moyenne {e:+5.1f} pts · chutes {cr:4.1f} % · {n} cas")
# positions déjà en baisse de 15 % ou plus par rapport à 4 semaines plus tôt (la panique les a touchées)
hit = held & (P / shift(P, 4) - 1 <= -.15)
print("   … positions qui viennent de perdre 15 % ou plus en 4 semaines :")
for lab, M in [('calme', CALM), ('panique', PAN)]:
    m = hit & M; e, cr, bg, n = st(m)
    print(f"   {lab:8s} 3 mois {np.nanmean(f13[m])*100:+5.1f} %, 6 mois {np.nanmean(fut_c[m])*100:+5.1f} % · écart {e:+5.1f} pts · chutes {cr:4.1f} % · {n} cas")
atlo = valid & (P <= lo52 * 1.02)
lead0 = shift(mp, 13) >= 2/3            # meneuse avant la baisse (tiers fort sur 12 mois il y a 3 mois)
print("\nD. Société à son plus bas de l'année : pendant une panique générale, ou seule (marché calme)")
for lab, M in [('à son plus bas, marché calme', atlo & CALM), ('à son plus bas, marché agité', atlo & MID), ('à son plus bas, panique générale', atlo & PAN),
               ('… meneuse avant la baisse, marché calme', atlo & lead0 & CALM), ('… meneuse avant la baisse, panique', atlo & lead0 & PAN)]:
    e, cr, bg, n = st(M); e2 = st(M, F=fut52)[0]
    per = '  '.join(f"{l} {st(M, x, y)[0]:+5.1f}" for l, x, y in E3)
    print(f"   {lab:42s} {e:+5.1f} pts à 6 mois · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n:6d} cas | 12 mois {e2:+5.1f} | {per} | t {tstat(M):4.1f}")
