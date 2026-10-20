"""Dosage selon l'agitation de la stratégie (Barroso et Santa-Clara 2015, Daniel et Moskowitz 2016), en version PEA :
pas d'effet de levier, la part non investie reste en liquidités. Séries mensuelles de nos gagnants (tiers haut sur 12 mois,
hors dernier mois, cours hebdomadaires 1997-2026, biais du survivant). Comparaison à exposition moyenne égale."""
import csv, numpy as np
R = list(csv.DictReader(open('our_wml.csv')))
mo = [r['month'] for r in R]
win = np.array([float(r['market_ew']) + float(r['w_minus_all']) for r in R])  # gagnants, achetés seuls
mkt = np.array([float(r['market_ew']) for r in R])
def stats(r, lab):
    v = np.cumprod(1 + r); peak = np.maximum.accumulate(v); dd = (v / peak - 1).min()
    yrs = len(r) / 12; cagr = v[-1] ** (1 / yrs) - 1; vol = r.std() * np.sqrt(12)
    w12 = min(np.prod(1 + r[k:k+12]) - 1 for k in range(len(r) - 11))
    print(f"  {lab:46s} {cagr*100:+6.1f} %/an  volatilité {vol*100:5.1f} %  pire baisse {dd*100:6.1f} %  pire année {w12*100:6.1f} %  rendement/risque {cagr/vol:4.2f}")
for k0, lab in [(6, '6 mois'), (3, '3 mois')]:
    sig = np.array([win[max(0, t-k0):t].std() * np.sqrt(12) if t >= k0 else np.nan for t in range(len(win))])
    # cible : médiane des agitations connues jusque-là (pas de regard vers le futur)
    tgt = np.array([np.nanmedian(sig[:t]) if t > 24 else np.nan for t in range(len(win))])
    w = np.clip(tgt / sig, 0, 1)
    ok = np.isfinite(w); w = np.where(ok, w, 1)
    s = slice(25, len(win))
    print(f"\n== agitation mesurée sur {lab} ({mo[25]} à {mo[-1]}), exposition moyenne {w[s].mean()*100:.0f} %")
    stats(win[s], 'gagnants, toujours investis')
    stats(w[s] * win[s], 'gagnants, dosés selon l\'agitation')
    stats(w[s].mean() * win[s], f'gagnants, {w[s].mean()*100:.0f} % investis en permanence')
    stats(mkt[s], 'marché (moyenne des sociétés)')
