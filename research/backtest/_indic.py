"""Les indicateurs du plan d'entrée (RSI, MACD, canal, support/résistance) croisés avec le 🎯 : aident-ils à choisir le moment ?
Cours hebdomadaires 1997-2026, écart à 6 mois avec la société moyenne de la même semaine (même cadre que _timing.py)."""
import numpy as np, pandas as pd
src = open('_timing.py').read(); exec(src.split("print('référence 🎯 (sans ⚡)')")[0])
above10 = ~(ext10 < 0)
F = Q & above10   # 🎯 avec feu vert (au-dessus de la moyenne 10 semaines) : ce que l'outil propose d'acheter
# MACD hebdomadaire 12/26/9
df = pd.DataFrame(P.T)
e12 = df.ewm(span=12, adjust=False, min_periods=26).mean(); e26 = df.ewm(span=26, adjust=False, min_periods=26).mean()
macd = e12 - e26; sig = macd.ewm(span=9, adjust=False, min_periods=9).mean()
hist = (macd - sig).values.T
mup = hist > 0
cross = np.zeros_like(mup)
cross[:, 2:] = mup[:, 2:] & ~(hist[:, :-2] > 0)  # passé au-dessus du signal dans les 2 dernières semaines
# position dans le canal de régression sur 26 semaines (±2 écarts-types)
L = np.log(np.where(P > 0, P, np.nan)); cpos = np.full_like(P, np.nan)
x = np.arange(26) - 12.5; sxx = (x ** 2).sum()
for t in range(25, T):
    Y = L[:, t-25:t+1]; ok = np.isfinite(Y).all(1)
    yb = Y.mean(1); b = ((Y - yb[:, None]) * x).sum(1) / sxx
    res = Y - (yb[:, None] + b[:, None] * x); s = res.std(1)
    fit = yb + b * x[-1]
    cpos[:, t] = np.where(ok & (s > 0), (L[:, t] - (fit - 2 * s)) / (4 * s), np.nan)
# position entre le plus bas de 13 semaines (support) et le plus haut de 52 semaines (résistance)
lo13 = pd.DataFrame(P.T).rolling(13, min_periods=13).min().values.T
hi52 = pd.DataFrame(P.T).rolling(52, min_periods=40).max().values.T
rpos = (P - lo13) / np.where(hi52 > lo13, hi52 - lo13, np.nan)
def rowF(lab, M):
    r = st(M)
    if r is None or M.sum() < 300: print(f"  {lab:46s} trop peu ({int(M.sum())})"); return
    per = '  '.join(f"{l} {st(M, a, b)[0]:+5.1f}" for l, a, b in E3)
    print(f"  {lab:46s} {r[0]:+6.1f} pts  chutes {r[1]:4.1f} %  part {M.sum()/F.sum()*100:4.0f} % | {per}")
print('référence : 🎯 avec feu vert (au-dessus de la moyenne 10 semaines)'); rowF('tous', F)
print('\n1. RSI hebdomadaire 14 (« suracheté » au-dessus de 70)')
for l, a, b in [('< 60', 0, 60), ('60 à 70', 60, 70), ('70 à 80 (« suracheté »)', 70, 80), ('80 ou plus', 80, 101)]: rowF(l, F & (rsi >= a) & (rsi < b))
print('\n2. MACD hebdomadaire')
rowF('au-dessus de son signal (haussier)', F & mup); rowF('sous son signal (baissier)', F & ~mup & np.isfinite(hist)); rowF('vient de croiser à la hausse (2 sem.)', F & cross)
print('\n3. position dans le canal de 6 mois')
for l, a, b in [('bas du canal (< 30 %)', -9, .3), ('milieu (30 à 70 %)', .3, .7), ('haut du canal (70 à 100 %)', .7, 1), ('au-dessus du canal', 1, 9)]: rowF(l, F & (cpos >= a) & (cpos < b))
print('\n4. entre support (plus bas 13 sem.) et résistance (plus haut 52 sem.)')
for l, a, b in [('près du support (< 30 %)', -9, .3), ('entre les deux (30 à 80 %)', .3, .8), ('sous la résistance (80 à 99 %)', .8, .99), ('au plus haut (≥ 99 %)', .99, 9)]: rowF(l, F & (rpos >= a) & (rpos < b))
print('\n5. tous les voyants « classiques » au vert (RSI < 70, MACD haussier, bas ou milieu du canal, pas collé à la résistance)')
G = (rsi < 70) & mup & (cpos < .7) & (rpos < .8)
rowF('les 4 au vert', F & G); rowF('les autres', F & ~G)
print('\n6. pour comparaison, toutes les sociétés (hors 🎯) avec les 4 voyants au vert')
A = valid & np.isfinite(rsi) & np.isfinite(cpos) & np.isfinite(rpos)
def rowA(lab, M):
    r = st(M); per = '  '.join(f"{l} {st(M, a, b)[0]:+5.1f}" for l, a, b in E3)
    print(f"  {lab:46s} {r[0]:+6.1f} pts  chutes {r[1]:4.1f} %  n {int(M.sum()):7d} | {per}")
rowA('toutes, 4 voyants au vert', A & G); rowA('toutes, référence', A)
