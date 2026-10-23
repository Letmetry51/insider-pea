"""Débuts de hausse et essoufflement, d'après les indicateurs de la bibliothèque ProRealCode (étapes de Weinstein, MACD-V,
divergences RSI, squeeze, séquence d'épuisement) : cours hebdomadaires 1997-2026 (long.npz, ≈ 1 000 sociétés européennes).

Mesure commune aux études : écart de rendement à 6 mois (26 semaines) avec la moyenne des sociétés de la même semaine, valeurs
extrêmes écrêtées à 2 % et 98 %, part des chutes (−25 % ou pire), par période, et contrôle hors échantillon (réglage regardé
sur 1997-2012, mesuré sur 2013-2026). t : cohortes de 6 mois sans chevauchement.

    python _depart.py            (dans le dossier qui contient long.npz)
"""
import numpy as np

z = np.load('long.npz', allow_pickle=True)
P = z['P'].astype(float); VO = z['V'].astype(float); dates = z['dates']; N, T = P.shape
P = np.where(P > 0, P, np.nan); VO = np.where(VO > 0, VO, np.nan)
fin = np.isfinite
yr = np.array([int(d[:4]) for d in dates])


def sma(A, k):
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(fin(A), 1)
    o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
    cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan
    return o


def ema(A, k):
    o = np.full_like(A, np.nan); a = 2 / (k + 1); cur = np.full(N, np.nan)
    for t in range(T):
        x = A[:, t]
        cur = np.where(fin(cur), np.where(fin(x), a * x + (1 - a) * cur, cur), x)
        o[:, t] = cur
    return o


def roll(A, k, f):
    o = np.full_like(A, np.nan)
    for t in range(k - 1, T):
        w = A[:, t-k+1:t+1]
        ok = fin(w).sum(1) >= k * .8
        with np.errstate(all='ignore'):
            o[ok, t] = f(w[ok], 1)
    return o


def shift(A, k):
    o = np.full_like(A, np.nan)
    if k > 0:
        o[:, k:] = A[:, :-k]
    return o


def bshift(B, k):  # booléen d'il y a k semaines (faux avant le début)
    o = np.zeros_like(B, dtype=bool)
    o[:, k:] = B[:, :-k]
    return o


def blead(B, k):  # booléen dans k semaines (faux après la fin)
    o = np.zeros_like(B, dtype=bool)
    o[:, :-k] = B[:, k:]
    return o


def ago_any(B, k):  # vrai si B a été vrai au moins une fois sur les k dernières semaines (semaine en cours comprise)
    c = np.cumsum(B.astype(int), 1); o = c.copy(); o[:, k:] = c[:, k:] - c[:, :-k]
    return o > 0


r1 = P / shift(P, 1) - 1
ret = np.clip(r1, -.5, 1)
m10, m30, m40 = sma(P, 10), sma(P, 30), sma(P, 40)
trend = (m10 > m40) & (P > m40)
mom = shift(P, 4) / shift(P, 52) - 1
L = np.log(P)


def slope(W):
    x = np.arange(W) - (W - 1) / 2; s = np.full_like(P, np.nan)
    for t in range(W - 1, T):
        y = L[:, t-W+1:t+1]; ok = fin(y).all(1)
        ym = y[ok].mean(1, keepdims=True); s[ok, t] = np.exp(((y[ok] - ym) * x).sum(1) / (x * x).sum() * 26) - 1
    return s


s26, s13 = slope(26), slope(13)
H = 26
fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
fut52 = np.full_like(P, np.nan); fut52[:, :-52] = P[:, 52:] / P[:, :-52] - 1
valid = fin(mom) & fin(fut) & fin(s26)
mp = np.full_like(P, np.nan)
for t in range(T):
    ok = valid[:, t]
    if ok.sum() > 30:
        mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
v52 = roll(ret, 52, np.nanstd) * np.sqrt(52)
vx = sma(VO, 10) / sma(VO, 52)
hi52, lo52 = roll(P, 52, np.nanmax), roll(P, 52, np.nanmin)
dd52 = P / hi52 - 1
# 🎯 tel qu'aujourd'hui (sans les comptes) : tiers fort sur 12 mois, tendance, pente forte, +60 à +200 %, pas de ⚡, au-dessus de la
# moyenne 10 semaines (⏸️)
Q = valid & (mp >= 2/3) & trend & (s26 >= .41) & (mom >= .6) & (mom <= 2) & ~(v52 >= .8) & (P >= m10)

t0 = int(np.argmax(valid.sum(0) > 30)); t13 = int(np.searchsorted(yr, 2013))
E3 = [('97-08', t0, int(np.searchsorted(yr, 2009))), ('09-17', int(np.searchsorted(yr, 2009)), int(np.searchsorted(yr, 2018))),
      ('18-26', int(np.searchsorted(yr, 2018)), T)]
A_, B_ = (t0, t13 - 26), (t13, T)


def st(M, a=t0, b=T, F=None):
    F = fut if F is None else F; h = 52 if F is fut52 else 26
    ex, n, cr, bg = [], 0, 0, 0
    for t in range(a, min(b, T - h)):
        ok = valid[:, t] & fin(F[:, t]); m = M[:, t] & ok
        if ok.sum() < 30 or not m.any():
            continue
        f = np.clip(F[:, t], *np.nanpercentile(F[ok, t], [2, 98]))
        ex.append(np.nanmean(f[m]) - np.nanmean(f[ok])); n += m.sum(); cr += (F[m, t] <= -.25).sum(); bg += (F[m, t] >= .5).sum()
    if not ex:
        return np.nan, np.nan, np.nan, 0
    return np.mean(ex) * 100, cr / n * 100, bg / n * 100, n


def wk_ex(M, t, F=None):
    F = fut if F is None else F
    ok = valid[:, t] & fin(F[:, t]); m = M[:, t] & ok
    if ok.sum() < 30 or not m.any():
        return np.nan
    f = np.clip(F[:, t], *np.nanpercentile(F[ok, t], [2, 98]))
    return np.nanmean(f[m]) - np.nanmean(f[ok])


def tstat(M1, M0=None, a=t0, b=T - 26):
    """écart d'excès (M1 − M0, ou M1 seul face au marché), une cohorte tous les 6 mois, deux séries décalées (n/2 indépendantes)"""
    bl = []
    for s0 in (0, 13):
        for t in range(a + s0, b, 26):
            e1 = wk_ex(M1, t); e0 = wk_ex(M0, t) if M0 is not None else 0.0
            if fin(e1) and fin(e0):
                bl.append(e1 - e0)
    bl = np.array(bl)
    return bl.mean() / (bl.std(ddof=1) / np.sqrt(len(bl) / 2)) if len(bl) > 5 else np.nan


def line(lab, M, ref=None):
    e, cr, bg, n = st(M)
    if n < 200:
        print(f"  {lab:58s} trop peu ({n})"); return
    per = '  '.join(f"{l} {st(M, x, y)[0]:+5.1f}" for l, x, y in E3)
    oa, ob = st(M, *A_)[0], st(M, *B_)[0]
    tt = tstat(M) if ref is None else tstat(M, ref)
    print(f"  {lab:58s} {e:+5.1f} pts · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n:6d} cas | {per} | 97-12 {oa:+5.1f} → 13-26 {ob:+5.1f} | t {tt:4.1f}")


def compare(lab, M1, M0):
    """deux groupes d'une même population : écart d'excès, par période, hors échantillon, t de l'écart"""
    a, b = st(M1), st(M0)
    if a[3] < 200 or b[3] < 200:
        print(f"  {lab:58s} trop peu ({a[3]} / {b[3]})"); return
    per = '  '.join(f"{l} {st(M1, x, y)[0] - st(M0, x, y)[0]:+5.1f}" for l, x, y in E3)
    oa = st(M1, *A_)[0] - st(M0, *A_)[0]; ob = st(M1, *B_)[0] - st(M0, *B_)[0]
    print(f"  {lab:58s} {a[0]:+5.1f} contre {b[0]:+5.1f} (écart {a[0]-b[0]:+5.1f}) · chutes {a[1]:4.1f} contre {b[1]:4.1f} % · part {a[3]/(a[3]+b[3])*100:3.0f} % | {per} | 97-12 {oa:+5.1f} → 13-26 {ob:+5.1f} | t {tstat(M1, M0):4.1f}")


# ---------------------------------------------------------------- indicateurs (hebdomadaires)
# RSI 14 semaines
g = np.where(r1 > 0, r1, 0.0); l_ = np.where(r1 < 0, -r1, 0.0); g[~fin(r1)] = np.nan; l_[~fin(r1)] = np.nan
ag, al = sma(g, 14), sma(l_, 14)
with np.errstate(all='ignore'):
    rsi = 100 - 100 / (1 + ag / np.where(al > 0, al, np.nan))
rsi = np.where(fin(ag) & (al == 0), 100.0, rsi)
# MACD-V (Spiroglou) : (EMA12 − EMA26) / ATR26 × 100 ; ATR approché par la variation absolue hebdomadaire moyenne (pas de plus haut
# ni de plus bas dans l'historique hebdomadaire)
atr = sma(np.abs(P - shift(P, 1)), 26)
macdv = (ema(P, 12) - ema(P, 26)) / atr * 100
macdv_sig = ema(macdv, 9)
# étapes de Weinstein (moyenne 30 semaines, marge 5 %, version ProRealCode sur la clôture)
up30 = m30 > shift(m30, 1)
st2 = (P > m30 * 1.05) & up30
st4 = (P < m30 * .95) & (m30 < shift(m30, 1))
# force relative de Mansfield : cours / indice équipondéré, rapporté à sa moyenne 52 semaines
mk = np.array([np.nanmean(ret[:, t]) if fin(ret[:, t]).sum() > 30 else 0.0 for t in range(T)])
idx = np.cumprod(1 + np.nan_to_num(mk))
RS = P / idx[None, :]
mans = RS / sma(RS, 52) - 1
# divergences RSI (détecteur ProRealCode, fenêtres 5 et 25, rebond de 1 %)
llx, llz = roll(P, 5, np.nanmin), roll(P, 25, np.nanmin)
hhx, hhz = roll(P, 5, np.nanmax), roll(P, 25, np.nanmax)
rlx, rlz = roll(rsi, 5, np.nanmin), roll(rsi, 25, np.nanmin)
rhx, rhz = roll(rsi, 5, np.nanmax), roll(rsi, 25, np.nanmax)
bull_div = (P > llx * 1.01) & (llx < shift(llz, 5)) & (rsi > rlx) & (rlx > shift(rlz, 5)) & (rlx < 35)
bear_div = (P < hhx * .99) & (hhx > shift(hhz, 5)) & (rsi < rhx) & (rhx < shift(rhz, 5)) & (rhx > 70)
# squeeze : volatilité sur 20 semaines au plus bas de son année, puis sortie par le haut (plus haut 26 semaines)
sd20 = roll(r1, 20, np.nanstd)
sq_rank = sd20 / roll(sd20, 52, np.nanmax)
squeeze = sq_rank <= roll(sq_rank, 52, lambda w, a: np.nanpercentile(w, 20, axis=a))
hi26p = shift(roll(P, 26, np.nanmax), 1)
sq_release = ago_any(squeeze, 8) & (P > hi26p)
# séquence d'épuisement (TD) : semaines d'affilée en clôture au-dessus de celle d'il y a 4 semaines
td = np.zeros_like(P)
cond = P > shift(P, 4)
for t in range(1, T):
    td[:, t] = np.where(cond[:, t], td[:, t-1] + 1, 0)
# efficacité de Kaufman sur 26 semaines (chemin net / chemin parcouru)
path = sma(np.abs(P - shift(P, 1)), 26) * 26
er = np.abs(P - shift(P, 26)) / path
ext40 = P / m40 - 1
r4 = P / shift(P, 4) - 1
cross1040 = (m10 > m40) & (shift(m10, 1) <= shift(m40, 1))
deep26 = roll(dd52, 26, np.nanmin) <= -.30   # creux : au moins 30 % sous le plus haut de l'année dans les 6 derniers mois

print(f"Données : {N} sociétés, {dates[t0]} → {dates[-1]} ; 🎯 : {int(Q.sum())} sociétés-semaines")
print("\n=== Référence")
line('🎯 (règles actuelles, sans les comptes)', Q)
line('toutes les sociétés en tendance (moyennes 10 > 40, cours au-dessus)', valid & trend)

print("\n=== 1. Repérer les débuts de hausse (toutes les sociétés, écart avec le marché à 6 mois)")
S = {
    'creux (−30 %) puis croisement des moyennes 10/40 sem. (≤ 4 sem.)': valid & deep26 & ago_any(cross1040, 4),
    'croisement des moyennes 10/40 sem. (≤ 4 sem.), sans creux': valid & ~deep26 & ago_any(cross1040, 4),
    'Weinstein : entrée en étape 2 après une étape 4 (≤ 4 sem.)': valid & ago_any(st2 & ~bshift(ago_any(st2, 26), 1) & bshift(ago_any(st4, 52), 1), 4),
    'Weinstein : étape 2 (cours > moy. 30 sem. + 5 %, moyenne montante)': valid & st2,
    'MACD-V repasse au-dessus de 0 après < −50 (≤ 4 sem.)': valid & ago_any((macdv > 0) & (shift(macdv, 1) <= 0) & bshift(ago_any(macdv < -50, 26), 1), 4),
    'Mansfield : force relative repasse au-dessus de 0 après < −10 %': valid & ago_any((mans > 0) & (shift(mans, 1) <= 0) & bshift(ago_any(mans < -.1, 26), 1), 4),
    'divergence haussière RSI (≤ 4 sem.)': valid & ago_any(bull_div, 4),
    'squeeze puis plus haut de 26 semaines (≤ 4 sem.)': valid & ago_any(sq_release, 4),
    'creux + croisement + force relative positive': valid & deep26 & ago_any(cross1040, 4) & (mans > 0),
}
for k, M in S.items():
    line(k, M)
print("\n  Même chose à 12 mois (excès, tous) :")
for k, M in list(S.items())[:4] + [('🎯 (référence)', Q)]:
    e, cr, bg, n = st(M, F=fut52)
    print(f"  {k:58s} {e:+5.1f} pts à 12 mois · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} %")

print("\n=== 2. Précocité : ces signaux annoncent-ils le 🎯 ?")
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
led_any = np.zeros_like(Q)
for k2 in range(1, 27):
    led_any |= blead(Qentry, k2)
for k in ['creux (−30 %) puis croisement des moyennes 10/40 sem. (≤ 4 sem.)', 'Weinstein : entrée en étape 2 après une étape 4 (≤ 4 sem.)',
          'MACD-V repasse au-dessus de 0 après < −50 (≤ 4 sem.)', 'Mansfield : force relative repasse au-dessus de 0 après < −10 %']:
    M = S[k]; first = M & ~bshift(ago_any(M, 13), 1)
    pre = np.zeros_like(Q)
    for k2 in range(1, 27):
        pre |= bshift(first, k2)
    a = first.sum(); b = (first & led_any).sum(); c = Qentry.sum(); d = (Qentry & pre).sum()
    print(f"  {k:58s} suivi d'une entrée 🎯 dans les 6 mois : {b/a*100:4.1f} % des signaux · entrées 🎯 annoncées : {d/c*100:4.1f} %")

print("\n=== 3. Essoufflement : parmi les sociétés 🎯, quels repères annoncent une moins bonne suite ?")
compare('MACD-V au-dessus de 150 (excès selon Spiroglou) / 50 à 150', Q & (macdv > 150), Q & (macdv >= 50) & (macdv <= 150))
compare('MACD-V sous sa ligne de signal (élan qui faiblit) / au-dessus', Q & (macdv < macdv_sig), Q & (macdv >= macdv_sig))
compare('divergence baissière RSI récente (≤ 8 sem.) / sans', Q & ago_any(bear_div, 8), Q & ~ago_any(bear_div, 8))
compare('pente 13 sem. < moitié de la pente 26 sem. / sinon', Q & (s13 < s26 / 2), Q & ~(s13 < s26 / 2))
compare('cours à plus de +60 % de la moyenne 40 sem. / moins de +30 %', Q & (ext40 > .6), Q & (ext40 < .3))
compare('près du plus haut (≤ 5 %) avec volumes en baisse (< ×0,8) / volumes ≥ ×1', Q & (dd52 >= -.05) & (vx < .8), Q & (dd52 >= -.05) & (vx >= 1))
compare('séquence d\'épuisement : 9 semaines d\'affilée ou plus / moins', Q & (td >= 9), Q & (td < 9))
compare('efficacité de Kaufman faible (< 0,2) / forte (≥ 0,4)', Q & (er < .2), Q & (er >= .4))
compare('emballement : +30 % en 4 sem. sur volumes ×2 / sinon', Q & (r4 > .3) & (vx >= 2), Q & ~((r4 > .3) & (vx >= 2)))
compare('Weinstein : plus en étape 2 (retour vers la moyenne 30) / étape 2', Q & ~st2, Q & st2)
compare('RSI hebdomadaire ≥ 80 / < 70', Q & (rsi >= 80), Q & (rsi < 70))
compare('force relative de Mansfield en baisse sur 8 sem. / en hausse', Q & (mans < shift(mans, 8)), Q & (mans >= shift(mans, 8)))

print("\n=== 4. Force du signal : MACD-V par quintile parmi les sociétés 🎯 (le plus faible d'abord)")
qs = np.nanpercentile(macdv[Q], [20, 40, 60, 80])
edges = [-np.inf] + list(qs) + [np.inf]
for k in range(5):
    line(f'quintile {k+1} (MACD-V {edges[k]:.0f} à {edges[k+1]:.0f})', Q & (macdv >= edges[k]) & (macdv < edges[k+1]))
