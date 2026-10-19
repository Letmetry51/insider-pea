"""Contrôle hors échantillon : réglages choisis sur 1997-2012 seulement, mesurés sur 2013-2026 ; apport de chaque règle par période."""
import numpy as np, itertools
src = open('_timing4.py').read(); exec(src.split("print('référence')")[0])
D = np.array([str(d) for d in dates]); t13 = int(np.searchsorted(D, '2013-01-01'))
A = (t0, t13 - 26); Bp = (t13, T)   # 6 mois de marge : aucun rendement de la période d'apprentissage ne déborde sur 2013
def S2(M, p): return st(M, p[0], p[1])
base = valid & (mp >= 2/3) & trend
V52 = np.nan_to_num(v52, nan=0.0); above = ~(ext10 < 0)
res = []
for lo, hi, sl, vc, ma in itertools.product([.3, .45, .6, .8], [1.5, 2, 3, 99], [.14, .25, .41, .6], [.6, .8, 1.0, 99], [0, 1]):
    M = base & (mom >= lo) & (mom <= hi) & (s26 >= sl) & (V52 < vc)
    if ma: M = M & above
    if M[:, A[0]:A[1]].sum() < 2000: continue
    a = S2(M, A); res.append((a[0], lo, hi, sl, vc, ma, M))
res.sort(key=lambda x: -x[0])
cur = base & (mom >= .6) & (mom <= 2) & (s26 >= .41) & (V52 < .8) & above
naive = valid & (mp >= 2/3)
print('== 1. Réglage choisi sur 1997-2012, mesuré sur 2013-2026 (écart à 6 mois contre la moyenne du marché)')
for lab, M in [('règles actuelles', cur), ('simple : tiers le plus fort sur 12 mois', naive)]:
    a, b = S2(M, A), S2(M, Bp); print(f"  {lab:46s} 1997-2012 {a[0]:+5.1f} (chutes {a[1]:4.1f} %) | 2013-2026 {b[0]:+5.1f} (chutes {b[1]:4.1f} %)")
for k, (sc, lo, hi, sl, vc, ma, M) in enumerate(res[:5]):
    b = S2(M, Bp); print(f"  meilleur n°{k+1} sur 1997-2012 : +{int(lo*100)} à +{int(hi*100) if hi < 9 else '∞'} %, pente ≥ {sl}, vol < {vc if vc < 9 else '∞'}, moy.10 {'oui' if ma else 'non'} | 1997-2012 {sc:+5.1f} → 2013-2026 {b[0]:+5.1f} (chutes {b[1]:4.1f} %)")
late = sorted([(S2(M, Bp)[0], lo, hi, sl, vc, ma) for sc, lo, hi, sl, vc, ma, M in res[:60]], key=lambda x: -x[0])
print(f"  pour mémoire, meilleur réglage possible sur 2013-2026 parmi les 60 premiers : {late[0][0]:+5.1f} ; rang des règles actuelles sur 1997-2012 :", next((k + 1 for k, r in enumerate(res) if (r[1], r[2], r[3], r[4], r[5]) == (.6, 2, .41, .8, 1)), None), 'sur', len(res))
print('\n== 2. Apport de chaque règle (on la retire, le reste identique)')
parts = {'hausse 12 mois +60 à +200 %': base & (s26 >= .41) & (V52 < .8) & above, 'pente forte': base & (mom >= .6) & (mom <= 2) & (V52 < .8) & above,
         '⚡ volatilité < 80 %': base & (mom >= .6) & (mom <= 2) & (s26 >= .41) & above, '⏸️ au-dessus moyenne 10 sem.': base & (mom >= .6) & (mom <= 2) & (s26 >= .41) & (V52 < .8)}
c1, c2 = S2(cur, A), S2(cur, Bp)
for lab, M in parts.items():
    a, b = S2(M, A), S2(M, Bp); print(f"  {lab:34s} apport 1997-2012 {c1[0]-a[0]:+5.1f} pts (chutes {c1[1]-a[1]:+5.1f}) | 2013-2026 {c2[0]-b[0]:+5.1f} pts (chutes {c2[1]-b[1]:+5.1f})")
print('\n== 3. Priorités, par période (dans les règles actuelles)')
hot = vx >= 1.5
for lab, m1, m0 in [('🔊 volumes ×1,5', hot, ~hot), ('📣 bond sur gros volume', rec, ~rec)]:
    a1, a0, b1, b0 = S2(cur & m1, A), S2(cur & m0, A), S2(cur & m1, Bp), S2(cur & m0, Bp)
    print(f"  {lab:26s} 1997-2012 avec {a1[0]:+5.1f} / sans {a0[0]:+5.1f} | 2013-2026 avec {b1[0]:+5.1f} / sans {b0[0]:+5.1f}")
