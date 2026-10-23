"""Suite : le 🎯 quand 10 à 20 % des sociétés sont au plus bas de l'année (« marché agité ») ; solidité par période, hors alerte
krach, réglages voisins ; et la protection −30 % déclenchée pendant une panique générale."""
import numpy as np
exec(open('_panique.py').read().split('lo4 = ')[0])
fut_c = np.clip(fut, -.6, 1.5)
f13 = np.full_like(P, np.nan); f13[:, :-13] = np.clip(P[:, 13:] / P[:, :-13] - 1, -.6, 1.5)
m52i = np.full(T, np.nan); m52i[52:] = idx[52:] / idx[:-52] - 1
W = lambda cond: np.broadcast_to(np.array([bool(ok_t[t] and cond(t)) for t in range(T)]), P.shape)
CALM = W(lambda t: lo_sh[t] < .10)
print("=== 🎯 selon la part des sociétés au plus bas de l'année (écart avec la moyenne à 6 mois)")
for lab, a, b in [('< 5 %', 0, .05), ('5 à 10 %', .05, .10), ('10 à 15 %', .10, .15), ('15 à 20 %', .15, .20), ('10 à 20 %', .10, .20), ('≥ 20 %', .20, 1.01)]:
    M = Q & W(lambda t, a=a, b=b: a <= lo_sh[t] < b)
    line(f'🎯, {lab} au plus bas', M)
print("\n=== 10 à 20 % au plus bas : avec ou sans alerte krach (marché −20 % sur un an), marché en hausse ou en baisse sur un an")
AG = W(lambda t: .10 <= lo_sh[t] < .20)
for lab, M in [('agité, sans alerte krach', Q & AG & W(lambda t: not (m52i[t] <= -.2))), ('agité, avec alerte krach', Q & AG & W(lambda t: m52i[t] <= -.2)),
               ('agité, marché en hausse sur un an', Q & AG & W(lambda t: m52i[t] > 0)), ('agité, marché en baisse sur un an', Q & AG & W(lambda t: m52i[t] <= 0)),
               ('calme (< 10 %), marché en baisse sur un an', Q & CALM & W(lambda t: m52i[t] <= 0))]:
    line(lab, M)
compare('🎯 : agité (10-20 %) / calme (< 10 %)', Q & AG, Q & CALM)
print("\n=== Protection −30 % : positions à −30 % ou pire depuis l'entrée dans le 🎯 (6 derniers mois), suite si on garde")
entry = np.full_like(P, np.nan)          # cours d'entrée : 1re semaine 🎯 de la série en cours (dans les 26 dernières semaines)
start = Q & ~bshift(Q, 1)
last_px = np.full(N, np.nan); last_t = np.full(N, -999)
for t in range(T):
    s = start[:, t]; last_px[s] = P[s, t]; last_t[s] = t
    ok = (t - last_t) <= 26
    entry[ok, t] = last_px[ok]
held = valid & fin(entry)
d30 = held & (P <= entry * .70) & ~bshift(held & (P <= entry * .70), 1)   # 1re semaine sous −30 %
PAN = W(lambda t: lo_sh[t] >= .20)
for lab, M in [('marché calme', d30 & CALM), ('marché agité', d30 & AG), ('panique générale', d30 & PAN)]:
    m = M; n = int(m.sum())
    print(f"  {lab:18s} {n:5d} cas | si on garde : 3 mois {np.nanmean(f13[m])*100:+5.1f} % (en hausse {np.nanmean(f13[m][fin(f13[m])] > 0)*100:3.0f} %), "
          f"6 mois {np.nanmean(fut_c[m])*100:+5.1f} % · encore −25 % ou pire en 6 mois : {np.nanmean(fut[m][fin(fut[m])] <= -.25)*100:3.0f} %")
