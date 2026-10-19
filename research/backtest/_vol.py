import numpy as np
src = open('_detect.py').read(); exec(src.split("# 3. momentum résiduel")[0])
yr = np.array([int(d[:4]) for d in dates]); t0 = int(np.argmax(valid.sum(0) > 30))
E3 = [('97-08', t0, int(np.searchsorted(yr, 2009))), ('09-17', int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))), ('18-26', int(np.searchsorted(yr, 2018)), T)]
exec(src[src.index("def st("):src.index("B = valid")])
B = valid & (mp >= 2/3) & trend & (s26 >= .41); Q = B & (mom >= .6) & (mom <= 2)
# volatilité annuelle sur les 52 dernières semaines (version simple, celle de l'outil)
v52 = np.full_like(P, np.nan)
for t in range(52, T): v52[:, t] = np.nanstd(ret[:, t-51:t+1], 1) * np.sqrt(52)
print('🎯 volatilité : médiane %.0f %%, 90e centile %.0f %%, 97e %.0f %%' % tuple(np.nanpercentile(v52[Q], [50, 90, 97]) * 100))
for th in (.5, .6, .7, .8):
    hi_, lo_ = Q & (v52 >= th), Q & (v52 < th)
    a, b = st(lo_), st(hi_)
    print(f"seuil {th*100:.0f} % : gardées {a[0]:+5.1f} ({a[1]:.1f} % chutes) | écartées {b[0]:+5.1f} ({b[1]:.1f} % chutes), part écartée {hi_.sum()/Q.sum()*100:.1f} % | écart par période " +
          '  '.join(f"{l} {st(lo_, x, y)[0]-st(hi_, x, y)[0]:+5.1f}" for l, x, y in E3))
np.save('v52.npy', v52.astype('float32'))
