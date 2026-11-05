"""CAPE de Shiller (S&P 500) comme filtre d'achat de la sélection (05/11/2026, badge « CAPE > 30 = marché cher » de l'ancien outil
Rotation PEA). Portefeuille simulé 1998-2023 (données de R. Shiller jusqu'à septembre 2023, research/macro_regime.py)."""
import numpy as np
exec(open('_volatilite_sim.py').read().split("\nif __name__ == '__main__':")[0])
zm = np.load('macro.npz', allow_pickle=True)
md = {str(d): j for j, d in enumerate(zm['dates'])}
CAPE = np.array([zm['cape'][md[str(d)]] if str(d) in md else np.nan for d in dates])
CAPE[np.array([str(d) for d in dates]) > '2023-09-30'] = np.nan
if __name__ == '__main__':
    by_regime("CAPE de Shiller (S&P 500) la semaine d'achat", CAPE, [(0, 20), (20, 25), (25, 30), (30, 35), (35, 99)],
              ['< 20', '20-25', '25-30', '30-35', '≥ 35'])
    tE = int(np.searchsorted(dates, '2023-10-01')) - t1997
    B = sim_w(lambda t: 1.0)
    for lab, f in (("pas d'achat quand le CAPE > 30 (marché cher)", lambda t: 0.0 if CAPE[t] > 30 else 1.0),
                   ("pas d'achat quand le CAPE > 35", lambda t: 0.0 if CAPE[t] > 35 else 1.0)):
        R = sim_w(f)
        print(f"  {lab:46s} écart 1998-2023 : {blocks2(R[:tE] - B[:tE])}")
