"""Candidats de la recherche pour mieux départager les sociétés 🎯 : momentum résiduel, « grenouille dans la casserole », momentum ajusté du risque, régularité."""
import numpy as np
exec(open('_vix.py').read().split("def expq")[0])  # mêmes données et variables (P, mom, mp, trend, s26, fut, valid, ret, mk)
fin = np.isfinite
# 1. grenouille dans la casserole (Da, Gurun, Warachka 2014) : hausse faite de petits pas réguliers plutôt que de quelques sauts
pos = (ret > 0).astype(float); neg = (ret < 0).astype(float); pos[~fin(ret)] = np.nan; neg[~fin(ret)] = np.nan
def roll(A, a, b):  # moyenne de A sur [t-a, t-b]
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(fin(A), 1)
    for t in range(a, T):
        s = c[:, t-b] - c[:, t-a-1] if t-a-1 >= 0 else c[:, t-b]; k = n[:, t-b] - (n[:, t-a-1] if t-a-1 >= 0 else 0)
        o[:, t] = np.where(k >= (a-b)*.8, s / np.maximum(k, 1), np.nan)
    return o
fp, fn_ = roll(pos, 52, 4), roll(neg, 52, 4)
ID = np.sign(mom) * (fn_ - fp)            # bas = régulier (meilleur selon l'étude)
# 2. momentum ajusté du risque : hausse / volatilité
r2 = ret ** 2; vol = np.sqrt(roll(r2, 52, 4) - roll(ret, 52, 4) ** 2) * np.sqrt(52)
RA = mom / vol
# 3. momentum résiduel (Blitz, Huij, Martens 2011) : hausse propre à la société, une fois retiré l'effet marché (bêta sur 2 ans)
RES = np.full_like(P, np.nan)
for t in range(104, T):
    R = ret[:, t-103:t+1]; M = mk[t-103:t+1]
    ok = fin(R) & fin(M)[None, :]
    Rm = np.where(ok, R, 0); Mm = np.where(ok, M[None, :], 0); n = ok.sum(1)
    mr = Rm.sum(1) / np.maximum(n, 1); mm = Mm.sum(1) / np.maximum(n, 1)
    cov = ((Rm - mr[:, None]) * (Mm - mm[:, None]) * ok).sum(1); var = (((Mm - mm[:, None]) ** 2) * ok).sum(1)
    beta = cov / np.where(var > 0, var, np.nan); e = np.where(ok, R - beta[:, None] * M[None, :], np.nan)
    w = e[:, -52:-4]; RES[:, t] = np.where(n >= 80, np.nansum(w, 1) / (np.nanstd(e, 1) + 1e-9), np.nan)
# 4. régularité : part des périodes de 4 semaines en hausse sur l'année
r4 = np.full_like(P, np.nan); r4[:, 4:] = P[:, 4:] / P[:, :-4] - 1
CON = np.full_like(P, np.nan)
for t in range(52, T): CON[:, t] = np.nanmean(np.stack([r4[:, t-4*k] > 0 for k in range(1, 13)]), 0)
def xrank(A):
    o = np.full_like(A, np.nan)
    for t in range(T):
        ok = valid[:, t] & fin(A[:, t])
        if ok.sum() > 30: o[ok, t] = A[ok, t].argsort().argsort() / (ok.sum() - 1)
    return o
yr = np.array([int(d[:4]) for d in dates]); t0 = int(np.argmax(valid.sum(0) > 30))
E3 = [('97-08', t0, int(np.searchsorted(yr, 2009))), ('09-17', int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))), ('18-26', int(np.searchsorted(yr, 2018)), T)]
def st(M, a=t0, b=T):
    ex = []; n = 0; cr = 0
    for t in range(a, min(b, T - H)):
        ok = valid[:, t]; m = M[:, t] & ok
        if ok.sum() < 30 or not m.any(): continue
        f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
        ex.append(np.nanmean(f[m]) - np.nanmean(f[ok])); n += m.sum(); cr += (fut[m, t] <= -.25).sum()
    ex = np.array(ex); return ex.mean() * 100, cr / max(n, 1) * 100
B = valid & (mp >= 2/3) & trend & (s26 >= .41)
Q = B & (mom >= .6) & (mom <= 2)
print('Référence : classement+pente forte', '%+.1f' % st(B)[0], '| 🎯', '%+.1f' % st(Q)[0])
for name, A, good_high in [('grenouille (régularité des petits pas)', ID, False), ('momentum ajusté du risque', RA, True), ('momentum résiduel (hors effet marché)', RES, True), ('part des mois en hausse', CON, True)]:
    rk = xrank(A if good_high else -A)
    print('\n==', name, ': moitié favorable vs défavorable (excès 6 m, chutes ≤ −25 %), puis par période')
    for g, M in [('classement+pente forte', B), ('🎯', Q)]:
        hi_, lo_ = M & (rk >= .5), M & (rk < .5)
        a, b = st(hi_), st(lo_)
        per = '  '.join(f"{lab} {st(hi_, x, y)[0]-st(lo_, x, y)[0]:+5.1f}" for lab, x, y in E3)
        print(f"   {g:24s} favorable {a[0]:+5.1f} ({a[1]:.1f} %)  défavorable {b[0]:+5.1f} ({b[1]:.1f} %)  écart {a[0]-b[0]:+5.1f} | {per}")
    print('   seul, à la place du classement 12 mois (tiers haut + tendance + pente forte) :', '%+.1f' % st(valid & (rk >= 2/3) & trend & (s26 >= .41))[0])
