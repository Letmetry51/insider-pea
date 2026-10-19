import numpy as np, sys
d = np.load(sys.argv[1]); P = d['P'].astype(float); VO = d['V'].astype(float); dates = list(d['dates']); sec = d['sec']
P = np.where(P > 0, P, np.nan); VO = np.where(VO > 0, VO, np.nan); N, T = P.shape; L = np.log(P)
yr = np.array([int(x[:4]) for x in dates])
def sma(A, k):
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(np.isfinite(A), 1)
    o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
    cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan; return o
m10, m40 = sma(P, 10), sma(P, 40); trend = (m10 > m40) & (P > m40)
mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)
for t in range(25, T):
    y = L[:, t-25:t+1]; ym = y.mean(1, keepdims=True); s26[:, t] = np.exp(((y-ym)*x).sum(1)/(x*x).sum()*26)-1
H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
valid = np.isfinite(mom) & np.isfinite(fut) & np.isfinite(s26)
mp = np.full_like(P, np.nan)
for t in range(T):
    ok = valid[:, t]
    if ok.sum() > 30: mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
nval = valid.sum(0); t0 = int(np.argmax(nval > 30))
ret = np.full_like(P, np.nan); ret[:, 1:] = P[:, 1:] / P[:, :-1] - 1
mk = np.array([np.nanmean(ret[valid[:, t-1], t]) if t and nval[t-1] > 30 else 0 for t in range(T)]); mc = np.cumprod(1 + np.nan_to_num(mk))
m52 = np.full(T, np.nan); m52[52:] = mc[52:] / mc[:-52] - 1; m104 = np.full(T, np.nan); m104[104:] = mc[104:] / mc[:-104] - 1; m13 = np.full(T, np.nan); m13[13:] = mc[13:] / mc[:-13] - 1
r4 = np.full_like(P, np.nan); r4[:, 4:] = P[:, 4:] / P[:, :-4] - 1
RANK = valid & (mp >= 2/3) & trend
mid1, mid2 = int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))
def st(M, a=t0, b=T):
    ex = []; win = n = hit = cr = 0
    for t in range(a, min(b, T-H)):
        ok = valid[:, t]; m = M[:, t] & ok
        if ok.sum() < 30 or not m.any(): continue
        f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98])); ex.append(np.nanmean(f[m]) - np.nanmean(f[ok]))
        win += (fut[m, t] > 0).sum(); hit += (fut[m, t] >= .4).sum(); cr += (fut[m, t] <= -.25).sum(); n += m.sum()
    if len(ex) < 5: return '   n.d.'
    e = np.array(ex); return f"{e.mean()*100:+6.1f} pt (t {e.mean()/e.std()*np.sqrt(len(e))/np.sqrt(H):4.1f}) gagne {win/n*100:3.0f} % ≥+40 {hit/n*100:4.1f} % ≤−25 {cr/n*100:4.1f} % [{len(e)} sem, {n/len(e):.0f}/sem]"
def eras(lab, M):
    print(f"{lab:56s} tout {st(M)}\n{'':56s} ≤2008 {st(M, t0, mid1)}\n{'':56s} 09-17 {st(M, mid1, mid2)}\n{'':56s} 18-26 {st(M, mid2, T)}")
print('=== VOLUMES ===')
for w, k in ((4, 2), (10, 1.5), (10, 2), (10, 3), (20, 2)):
    vw, v52 = sma(VO, w), sma(VO, 52); surge = (vw > k * v52) & (r4 > 0)
    eras(f'classement + volume {w} sem ×{k} avec hausse', RANK & surge)
vw, v52 = sma(VO, 10), sma(VO, 52)
eras('classement + volume 10 sem ×2 SANS condition de hausse', RANK & (vw > 2 * v52))
eras('classement + volume 10 sem ×2 avec BAISSE sur 4 sem', RANK & (vw > 2 * v52) & (r4 < 0))
eras('classement SANS volume en hausse (contrôle)', RANK & ~(vw > 1.2 * v52))
eras('pente forte + volume ×2 + hausse', valid & trend & (s26 >= .41) & (vw > 2 * v52) & (r4 > 0))
print('\n=== KRACH DU MOMENTUM (Daniel & Moskowitz) : le classement selon l\'état du marché ===')
for lab, cond in (('marché en hausse sur 2 ans', m104 > 0), ('marché en baisse sur 2 ans', m104 <= 0), ('marché en baisse sur 1 an', m52 <= 0),
                  ('rebond : baisse sur 1 an mais +10 % sur 3 mois', (m52 <= 0) & (m13 > .10)), ('marché −20 % sur 1 an', m52 <= -.2)):
    c = np.zeros_like(valid); c[:, cond] = True
    print(f"{lab:45s} semaines {cond.sum():4d} | classement {st(RANK & c)}")
for lab, cond in (('rebond : baisse sur 1 an mais +10 % sur 3 mois', (m52 <= 0) & (m13 > .10)),):
    ws = [dates[t] for t in range(T) if cond[t] and t >= t0]; print('  semaines concernées :', ws[:3], '…', ws[-3:], 'années', sorted(set(w[:4] for w in ws)))
