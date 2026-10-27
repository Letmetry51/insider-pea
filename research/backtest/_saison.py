"""Saison propre à chaque société (Heston et Sadka 2008, 2010) : une action qui a monté le même mois les années passées monte-t-elle
encore ce mois-là ? Rendement moyen du même mois sur les 5 à 10 années précédentes ; écart avec la moyenne des sociétés le mois
suivant (et à 6 mois), par quintile, dans tout l'univers et parmi les sociétés du 🎯 (règles sans les comptes). Fins de mois
approchées par la dernière clôture hebdomadaire du mois."""
import numpy as np
exec(open('_depart.py').read().split('print(f"Données')[0])
ym = np.array([d[:7] for d in dates])
months = sorted(set(ym))
ends = np.array([np.where(ym == m)[0][-1] for m in months])        # dernière semaine de chaque mois
PM = P[:, ends]
RM = PM[:, 1:] / PM[:, :-1] - 1                                    # rendement du mois k (k = 1…)
RM = np.clip(RM, -.6, 1.5)
K = RM.shape[1]
mo = np.array([int(m[5:7]) for m in months[1:]])
yr_m = np.array([int(m[:4]) for m in months[1:]])
SEAS = np.full_like(RM, np.nan)
for k in range(K):
    past = [k - 12 * y for y in range(1, 11) if k - 12 * y >= 0]
    if len(past) >= 5:
        X = RM[:, past]
        n = np.isfinite(X).sum(1)
        with np.errstate(all='ignore'):
            SEAS[:, k] = np.where(n >= 5, np.nanmean(X, 1), np.nan)
QM = Q[:, ends[:-1]]                                               # 🎯 à la fin du mois précédent (k−1)


def test(lab, cond=None, h=1):
    rows = []
    for k in range(K - h + 1):
        s = SEAS[:, k]
        fw = np.prod(1 + np.nan_to_num(RM[:, k:k + h]), 1) - 1 if h > 1 else RM[:, k]
        ok = np.isfinite(s) & np.isfinite(RM[:, k])
        if cond is not None:
            ok &= cond[:, k]
        if ok.sum() < 30:
            continue
        mk_ = np.mean(fw[np.isfinite(RM[:, k])])
        qs = np.nanpercentile(s[ok], [20, 80])
        top = ok & (s >= qs[1]); bot = ok & (s <= qs[0])
        rows.append((yr_m[k], fw[top].mean() - mk_, fw[bot].mean() - mk_))
    a = np.array(rows)
    if not len(a):
        print(f"  {lab}: trop peu"); return
    per = []
    for l, y0, y1 in (('97-08', 1990, 2009), ('09-17', 2009, 2018), ('18-26', 2018, 2027)):
        m = (a[:, 0] >= y0) & (a[:, 0] < y1)
        if m.sum() > 5:
            per.append(f"{l} {a[m, 1].mean()*100:+5.2f}/{a[m, 2].mean()*100:+5.2f}")
    d = a[:, 1] - a[:, 2]
    t_ = d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) * (1 if h == 1 else 1 / np.sqrt(h))
    print(f"  {lab:46s} meilleur quintile {a[:, 1].mean()*100:+5.2f} % · pire {a[:, 2].mean()*100:+5.2f} % (écart {d.mean()*100:+5.2f}, t {t_:4.1f}) · {len(a)} mois | {'  '.join(per)}")


print(f"{N} sociétés, {K} mois")
print("=== mois suivant (écart avec la moyenne des sociétés)")
test('toutes les sociétés')
test('sociétés 🎯 (fin du mois précédent)', QM)
print("=== 6 mois suivants")
test('toutes les sociétés', h=6)
test('sociétés 🎯', QM, h=6)
