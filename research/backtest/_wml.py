"""Nos séries mensuelles (cours actuels, avec biais du survivant) : gagnants − perdants (tiers haut − tiers bas, 12 mois hors dernier mois), gagnants − tous, marché."""
import numpy as np, csv
z = np.load('long.npz', allow_pickle=True); P = z['P'].astype(float); dates = list(z['dates'])
P = np.where(P > 0, P, np.nan); N, T = P.shape
months = {}
for t, d in enumerate(dates): months[d[:7]] = t  # dernière semaine de chaque mois
ks = sorted(months); idx = [months[k] for k in ks]
M = P[:, idx]  # cours de fin de mois
rows = []
for j in range(13, len(ks) - 1):
    mom = M[:, j - 1] / M[:, j - 12] - 1  # 12 mois hors dernier mois
    r = M[:, j + 1] / M[:, j] - 1
    ok = np.isfinite(mom) & np.isfinite(r) & np.isfinite(M[:, j])
    if ok.sum() < 30: continue
    r = np.clip(r, -.9, 3)
    lo, hi = np.percentile(mom[ok], [30, 70])
    W = ok & (mom >= hi); L = ok & (mom <= lo)
    rows.append((ks[j + 1], r[W].mean() - r[L].mean(), r[W].mean() - r[ok].mean(), r[ok].mean(), int(ok.sum())))
with open('our_wml.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['month', 'wml', 'w_minus_all', 'market_ew', 'n']); w.writerows(rows)
print(len(rows), rows[0], rows[-1])
