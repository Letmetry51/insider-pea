"""Dans le 🎯 : prioriser le 2e à 4e nouveau plus haut de l'année ? croisement avec les volumes ; écart à la moyenne 40 semaines (surextension)."""
import numpy as np
src = open('_highs.py').read(); exec(src.split("near = valid")[0])
z = np.load('long.npz', allow_pickle=True); VO = z['V'].astype(float)
def sma2(A, k):
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(np.isfinite(A), 1)
    o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
    cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan; return o
vx = sma2(VO, 10) / sma2(VO, 52)
v52 = np.load('v52.npy').astype(float)
B = valid & (mp >= 2/3) & trend & (s26 >= .41); Q = B & (mom >= .6) & (mom <= 2) & ~(v52 >= .8)
good = (ep >= 2) & (ep <= 4); hot = vx >= 1.5
def row(lab, M):
    r = st(M)
    per = '  '.join(f"{l} {st(M, x, y)[0]:+5.1f}" for l, x, y in E3)
    print(f"  {lab:46s} {r[0]:+6.1f} pts  chutes {r[1]:4.1f} %  part {M.sum()/Q.sum()*100:4.0f} % | {per}")
print('== 🎯 (sans ⚡), quelle que soit la distance au plus haut')
row('tous', Q); row('2e à 4e plus haut de l\'année', Q & good); row('1er seulement', Q & (ep <= 1)); row('5e ou plus', Q & (ep >= 5))
print('== croisement avec les volumes (priorité actuelle)')
row('🔊 ≥ ×1,5 et 2e-4e', Q & hot & good); row('🔊 ≥ ×1,5, autres', Q & hot & ~good); row('sans 🔊, 2e-4e', Q & ~hot & good); row('sans 🔊, autres', Q & ~hot & ~good)
ext = P / m40 - 1
print('== surextension : cours au-dessus de sa moyenne 40 semaines')
for lo, hi_ in [(0, .15), (.15, .3), (.3, .5), (.5, 9)]:
    row(f'+{int(lo*100)} à +{int(hi_*100)} %' if hi_ < 9 else f'plus de +{int(lo*100)} %', Q & (ext >= lo) & (ext < hi_))
np.save('ep.npy', ep.astype('int16'))
