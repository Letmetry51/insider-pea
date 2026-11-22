"""Contrôle du « 📣 Bond du jour » sans biais du survivant (22/11/2026, suite de survivant_portefeuille.py, François : « Faire ce qui
est pertinent »). Sur les mêmes cours journaliers EODHD, l'écart à 6 mois des alertes selon l'univers :
  A. sociétés encore cotées et liquides aujourd'hui (au moins 1 M€, puis 3 M€ par jour), sans filtre à la date : comme l'étude
     Yahoo du 14/11/2026 (bond_jour_seuil.py), les données EODHD retrouvent-elles ses chiffres ?
  B. sociétés encore cotées, au moins 3 M€ par jour à la date de l'alerte ;
  C. toutes les sociétés, disparues comprises, au moins 3 M€ par jour à la date : la condition de l'email, le chiffre honnête.
Règle du 14/11/2026, fixée avant le calcul et rejouée telle quelle : le seuil de 4 fois tient si les alertes ajoutées (4 à 5 fois)
font mieux que le 🎯 au feu vert dans chaque période (2000-2008, 2009-2017, 2018-2026).
Les cours restent en mémoire (rien dans research/out) ; la clé n'est jamais affichée. Lancé par « Recherche (à la demande) »
(script survivant_bond.py), environ 15 minutes, 8 300 appels EODHD.
"""
import gc
import time

import numpy as np

import survivant_eodhd as SE
import survivant_portefeuille as PF

log = SE.log


def main():
    D = SE.prepare()
    if D is None:
        return
    liq, cols, dates, T, t00, gone, dl = (D[k] for k in ('liq', 'cols', 'dates', 'T', 't00', 'gone', 'dl'))
    del D
    gc.collect()
    log(f"\nUnivers : {len(cols)} sociétés, {int(dl.sum())} retirées de la cote, dont {int(gone.sum())} disparues avant la fin")
    Z = PF.daily(cols, liq, dates, T, gone)
    LQ, today = Z['LQ'], np.nan_to_num(liq[:, -1])
    U = [('A. cotées et liquides aujourd\'hui (≥ 1 M€), sans filtre à la date', np.broadcast_to(((~dl) & (today >= 1e6))[:, None], LQ.shape)),
         ('A. cotées et liquides aujourd\'hui (≥ 3 M€), sans filtre à la date', np.broadcast_to(((~dl) & (today >= 3e6))[:, None], LQ.shape)),
         ('B. cotées, ≥ 3 M€ à la date', (~dl)[:, None] & (LQ >= 3e6)),
         ('C. toutes, disparues comprises, ≥ 3 M€ à la date (condition de l\'email)', LQ >= 3e6)]
    res = {}
    for lab, lq in U:
        res[lab] = PF.measure(Z, f"{lab}, {int(lq.any(1).sum())} sociétés", lq)
    log(PF.EMAILS)
    log("\nRègle du 14/11/2026 rejouée (alertes ajoutées entre 4 et 5 fois face au 🎯 au feu vert, chaque période) :")
    for lab, r in res.items():
        a4, feu = r['bond entre 4 et 5 fois'], r['🎯 au feu vert, chaque vendredi']
        win = [np.isfinite(x) and np.isfinite(y) and x > y for x, y in zip(a4[1], feu[1])]
        cell = ' / '.join(f"{x * 100:+.1f} contre {y * 100:+.1f}" if np.isfinite(x) and np.isfinite(y) else '·' for x, y in zip(a4[1], feu[1]))
        log(f"  {lab:72s} {cell} → {'tient' if all(win) else 'ne tient pas'} ({sum(win)} période(s) sur 3 ; {a4[2]} cas)")
    u, err = SE.get('user')
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
