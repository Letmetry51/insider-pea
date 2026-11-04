"""Masque hebdomadaire des bonds du jour (04/11/2026), pour le portefeuille simulé local (_selection_sim9.py) : par société et par
semaine (vendredi), une séance au moins dans la semaine avec un bond du jour (bit 0 : +8 % sur 5 fois le volume moyen de 50 séances, en
tendance ; bit 1 : +8 % sur 3 fois ; bit 2 : +8 % sur 5 fois au plus haut de l'année ; bit 3 : +6 % sur 7 fois). Imprimé en base64 entre
FIGURES-DEBUT et FIGURES-FIN (python backtest/_bougies_masque.py journal.log jour_mask.npz). Lancé par « Recherche (à la demande) »
(script hausse_tot4.py), environ 3 minutes."""
import base64
import io
import time

import numpy as np
import pandas as pd

import figures_bougies as FB
import hausse_tot as HT

log, shift, roll = FB.log, FB.shift, HT.roll


def main():
    t0 = time.time()
    D = FB.download(list(FB.universe()))
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates, cols = D['Close'].index, list(D['Close'].columns)
    with np.errstate(all='ignore'):
        ok = np.isfinite(C) & (np.nan_to_num(V) > 0)
        ret1 = C / shift(C, 1) - 1
        vx = V / shift(roll(np.where(V > 0, V, np.nan).astype(np.float32), 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        hi252 = shift(roll(C, 252, 'max', 200), 1)
        M = [ok & (ret1 >= .08) & (vx >= 5) & trend, ok & (ret1 >= .08) & (vx >= 3) & trend,
             ok & (ret1 >= .08) & (vx >= 5) & trend & (C >= hi252), ok & (ret1 >= .06) & (vx >= 7) & trend]
    wdates = D['Close'].resample('W-FRI').last().index
    bits = np.zeros((len(cols), len(wdates)), dtype=np.uint32)
    for b, m in enumerate(M):
        w = pd.DataFrame(m.T, index=dates, columns=cols).resample('W-FRI').max().reindex(wdates).fillna(False).values.T.astype(bool)
        bits |= w.astype(np.uint32) << np.uint32(b)
        log(f"bit {b} : {int(m.sum())} séances, {int(w.sum())} semaines")
    buf = io.BytesIO()
    np.savez_compressed(buf, bits=bits, cols=np.array(cols), dates=np.array([str(d.date()) for d in wdates]),
                        names=np.array(['+8 % ×5 tendance', '+8 % ×3 tendance', '+8 % ×5 plus haut', '+6 % ×7 tendance']))
    s = base64.b64encode(buf.getvalue()).decode()
    log(f"masque : {bits.shape}, {len(s)} caractères en base64")
    print("FIGURES-DEBUT", flush=True)
    for i in range(0, len(s), 8000):
        print("B64:" + s[i:i + 8000], flush=True)
    print("FIGURES-FIN", flush=True)
    log(f"terminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
