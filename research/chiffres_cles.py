"""Les chiffres clés d'Euro Signal en un seul script, du plus flatteur au plus prudent.

Une seule source : long.npz (cours hebdomadaires Yahoo ajustés des divisions ET des dividendes, 1985-2026, voir
backtest/_long.py). Mesure commune à toutes les études : pour chaque semaine, rendement à 6 mois (26 semaines) des
sociétés retenues moins celui de la société moyenne de la même semaine, valeurs extrêmes écrêtées à 2 % et 98 %.

Règle 🎯 (cœur de ES.pickThree) : tiers le plus fort sur 12 mois, tendance (moyenne 10 sem. > 40 sem. et cours > 40 sem.),
hausse de +60 à +200 %, pente forte, volatilité < 80 %/an (⚡), cours au-dessus de sa moyenne 10 semaines (⏸️).

  cd research/backtest && python ../chiffres_cles.py long.npz

Chaque correction est une hypothèse chiffrée, affichée : frais, faillites manquantes (biais du survivant), hasard des
essais (seuil t ≥ 3 de Harvey, Liu et Zhu, 2016, pour une règle choisie parmi beaucoup d'essais).
"""
import sys
import numpy as np

z = np.load(sys.argv[1] if len(sys.argv) > 1 else 'long.npz', allow_pickle=True)
P = z['P'].astype(float); VO = z['V'].astype(float); dates = [str(d) for d in z['dates']]
P = np.where(P > 0, P, np.nan); VO = np.where(VO > 0, VO, np.nan); N, T = P.shape; H = 26


def sma(A, k):
    o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(np.isfinite(A), 1)
    o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
    cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan
    return o


m10, m40 = sma(P, 10), sma(P, 40); trend = (m10 > m40) & (P > m40)
mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1          # 12 mois, dernier mois exclu
L = np.log(P); x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)               # pente sur 26 semaines
for t in range(25, T):
    y = L[:, t-25:t+1]; s26[:, t] = np.exp(((y - y.mean(1, keepdims=True)) * x).sum(1) / (x * x).sum() * 26) - 1
fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
valid = np.isfinite(mom) & np.isfinite(fut) & np.isfinite(s26)
mp = np.full_like(P, np.nan)
for t in range(T):
    ok = valid[:, t]
    if ok.sum() > 30:
        mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
ret = np.full_like(P, np.nan); ret[:, 1:] = np.clip(P[:, 1:] / P[:, :-1] - 1, -.5, 1)
v52 = np.full_like(P, np.nan)
for t in range(52, T):
    v52[:, t] = np.nanstd(ret[:, t-51:t+1], 1) * np.sqrt(52)
ext10 = P / m10 - 1
vx = sma(VO, 10) / sma(VO, 52)

D = np.array(dates); t0 = int(np.argmax(valid.sum(0) > 30)); t13 = int(np.searchsorted(D, '2013-01-01'))
RULE = valid & (mp >= 2/3) & trend & (mom >= .6) & (mom <= 2) & (s26 >= .41) & ~(v52 >= .8) & ~(ext10 < 0)
NAIVE = valid & (mp >= 2/3)


def st(M, a=t0, b=T):
    """Écart moyen (points), t corrigé du chevauchement des périodes de 6 mois, part battant la moyenne, chutes ≤ −25 %,
    rendement brut moyen des sociétés retenues."""
    ex, n, win, cr, raw = [], 0, 0, 0, []
    for t in range(a, min(b, T - H)):
        ok = valid[:, t]; m = M[:, t] & ok
        if ok.sum() < 30 or not m.any():
            continue
        f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98])); base = np.nanmean(f[ok])
        ex.append(np.nanmean(f[m]) - base); n += m.sum(); win += (fut[m, t] > base).sum(); cr += (fut[m, t] <= -.25).sum()
        raw.append(np.nanmean(fut[m, t]))
    e = np.array(ex)
    return {'pts': e.mean() * 100, 't': e.mean() / e.std() * np.sqrt(len(e)) / np.sqrt(H), 'win': win / n * 100,
            'crash': cr / n * 100, 'raw': np.mean(raw) * 100, 'weeks': len(e)}


full, ins, oos = st(RULE), st(RULE, t0, t13 - H), st(RULE, t13, T)
nv, al = st(NAIVE, t13, T), st(valid, t13, T)
print(f"{N} sociétés, {dates[t0]} → {dates[-1]} (cours ajustés des dividendes : dividendes inclus)\n")
print('1. Résultat brut, écart à 6 mois avec la société moyenne de la même semaine')
for lab, r in [('1997-2026, tout l\'historique', full), ('1997-2012, années de réglage', ins), ('2013-2026, jamais vues au réglage', oos),
               ('   pour comparer : simple tiers le plus fort sur 12 mois, 2013-2026', nv), ('   toutes les sociétés, 2013-2026', al)]:
    print(f"   {lab:62s} {r['pts']:+5.1f} pts  t {r['t']:4.1f}  battent la moyenne {r['win']:3.0f} %  chutes ≤ −25 % {r['crash']:4.1f} %")
print('\n2. Hasard des essais (512 réglages essayés pour le contrôle hors échantillon)')
print(f"   t sur 2013-2026 seul : {oos['t']:.1f} (seuil exigeant pour une règle choisie parmi beaucoup d'essais : 3) → "
      + ('passe' if oos['t'] >= 3 else 'ne passe pas') + ' ; chiffre retenu : celui des années jamais vues')
print('\n3. Frais : un achat et une vente par sélection (gardée 6 mois)')
for c in (.5, 1, 2):
    print(f"   {c:3.1f} % par aller-retour → {oos['pts'] - c:+5.1f} pts")
print('\n4. Biais du survivant : faillites absentes des données. Hypothèse sévère : une part des sociétés retenues perd tout en 6 mois')
for q in (1, 2):
    print(f"   {q} % des sélections à −100 % → −{q / 100 * (100 + oos['raw']):.1f} pt "
          f"(rendement brut moyen des sélections : {oos['raw']:+.1f} %)")
prudent = oos['pts'] - 1 - 2 / 100 * (100 + oos['raw'])
print(f"\n5. Chiffre prudent (2013-2026, 1 % de frais, 2 % de faillites) : {prudent:+.1f} pts à 6 mois, environ {2 * prudent:+.0f} par an")
