"""Momentum résiduel (15/11/2026, audit demandé par François : « Améliorer, autre stratégie ou méthode ? »).

Piste jamais testée ici : le momentum « résiduel » (Blitz, Huij et Martens, 2011 ; Blitz, Hanauer et Vidojevic, 2020, Europe
comprise) classe les sociétés sur leur hausse propre, une fois retirée la part qui vient du marché. Il a donné, dans ces études,
un rendement ajusté du risque plus élevé que le momentum brut et des krachs de retournement plus faibles (2009).

Calcul (cours hebdomadaires de l'étude longue) : rendement de chaque semaine moins bêta × rendement moyen des sociétés (bêta sur
156 semaines, 104 connues au moins), puis somme de ces résidus sur 48 semaines en sautant les 4 dernières, divisée par leur écart
type ; rang en pourcentage parmi les sociétés de la semaine.

Règle fixée avant le calcul :
- règle actuelle : portefeuille simulé 1998-2026 de backtest/_selection_sim.py (4 🎯 + 1 📣, 2 par secteur, gardés 26 semaines,
  frais 0,3 % par sens), ordre des candidats par la note (50 × rang du momentum 12 mois + plus haut de l'année + tendance) ;
- variante principale : même sélection, mêmes filtres d'entrée, mais la note prend le rang du momentum résiduel à la place du
  rang du momentum brut ;
- adoptée seulement si elle bat la règle actuelle sur chacune des périodes 1998-2008, 2009-2017 et 2018-2026, avec t ≥ 3 sur
  l'ensemble (seuil de research/README.md pour une piste parmi beaucoup) ; sinon documentée.
Variantes pour information : la note prend la moyenne des deux rangs ; tiers le plus faible en momentum résiduel écarté.

Étapes : cours hebdomadaires Yahoo de backtest/_long.py (long.npz), puis la chaîne _selection_sim7.py. Lancé par « Recherche (à la
demande) » (script momentum_residuel.py), environ 12 minutes.
"""
import os
import runpy
import time

import numpy as np
import pandas as pd

import figures_bougies as FB

log = FB.log


def residual_momentum(r, mkt, okn, beta_w=156, beta_min=104, form=48, skip=4):
    """Rang (0 à 1) du momentum résiduel par semaine : résidus du rendement face au marché (bêta glissant), somme sur `form`
    semaines en sautant les `skip` dernières, divisée par leur écart type. r : rendements hebdomadaires (N × T, NaN si absent)."""
    R = pd.DataFrame(np.where(okn, r, np.nan).T)
    M = pd.Series(mkt)
    mR = R.rolling(beta_w, min_periods=beta_min).mean()
    mM = M.rolling(beta_w, min_periods=beta_min).mean()
    cov = R.mul(M, axis=0).rolling(beta_w, min_periods=beta_min).mean() - mR.mul(mM, axis=0)
    var = M.rolling(beta_w, min_periods=beta_min).var(ddof=0)
    beta = cov.div(var, axis=0)
    E = R - beta.mul(M, axis=0)
    S = E.rolling(form, min_periods=int(form * .8)).sum().shift(skip)
    SD = E.rolling(form, min_periods=int(form * .8)).std().shift(skip)
    score = (S / SD.replace(0, np.nan)).where(pd.DataFrame(okn.T).values)
    return score.rank(axis=1, pct=True).values.T, beta.values.T


def main():
    t0 = time.time()
    os.chdir('backtest')
    Lg = runpy.run_path('_long.py', run_name='long_build')
    sec = Lg['universe']()
    W, V = Lg['download'](list(sec))
    W = W.loc['1985':]
    V = V.reindex(index=W.index, columns=W.columns)
    wdates = [str(d.date()) for d in W.index]
    wcols = list(W.columns)
    P, cut = Lg['clean'](W.values.T.astype(float))
    np.savez_compressed('long.npz', P=P.astype('float32'), V=V.values.T.astype('float32'), dates=np.array(wdates),
                        cols=np.array(wcols), sec=np.array([sec.get(c, '?') for c in wcols]))
    log(f"cours hebdomadaires : {len(wcols)} sociétés, {len(wdates)} semaines ({wdates[0]} → {wdates[-1]}), {cut} séries coupées, "
        f"en {time.time() - t0:.0f} s")
    G = {'__name__': 'selection_sim'}
    code = open('_selection_sim7.py').read().split("\nif __name__ == '__main__':")[0]
    exec(compile(code, '_selection_sim7.py', 'exec'), G)
    okn, mpn, ratio, trend, r1, mkw = (G[k] for k in ('okn', 'mpn', 'ratio', 'trend', 'r1', 'mkw'))
    weekly, pick, blocks, t1997, gT = G['weekly'], G['pick'], G['blocks'], G['t1997'], G['P'].shape[1]
    r = np.clip(r1, -.6, 1.5)
    rmp, beta = residual_momentum(r, mkw, okn)
    both = np.isfinite(rmp) & np.isfinite(mpn) & okn
    corr = [np.corrcoef(rmp[both[:, t], t], mpn[both[:, t], t])[0, 1] for t in range(t1997, gT, 26) if both[:, t].sum() > 50]
    log(f"momentum résiduel calculé en {time.time() - t0:.0f} s : {int(np.isfinite(rmp).sum())} valeurs ; corrélation des rangs "
        f"avec le momentum brut {np.nanmedian(corr):.2f} (médiane) ; bêta médian {np.nanmedian(beta):.2f}")
    base_note = G['note'].copy()
    clipr = 10 * np.clip((ratio - .6) / .4, 0, 1) + np.where(trend, 15, 0)

    def run(note=None, extra=None):
        G['note'] = base_note if note is None else np.where(np.isfinite(note), note, base_note)
        if extra is None:
            return weekly(lambda t: pick(t, n=5, reserve=1, bondCap=2), t1997, gT)
        okn0 = G['okn']
        G['okn'] = okn0 & extra
        try:
            return weekly(lambda t: pick(t, n=5, reserve=1, bondCap=2), t1997, gT)
        finally:
            G['okn'] = okn0

    A0 = run()
    log(f"\nRègle actuelle (4 🎯 + 1 📣) : {A0.mean() * 52 * 100:+.1f} % par an avant marché")
    note_res = 50 * rmp + clipr
    note_mix = 50 * (rmp + mpn) / 2 + clipr
    variants = [
        ('note sur le rang du momentum résiduel — principale', dict(note=note_res)),
        ('note sur la moyenne des deux rangs', dict(note=note_mix)),
        ('note résiduelle et tiers le plus faible en résiduel écarté', dict(note=note_res, extra=~(rmp < 1 / 3))),
    ]
    log("Écart avec la règle actuelle (rendement hebdomadaire annualisé, t sur blocs de 6 mois) :")
    res = {}
    for lab, kw in variants:
        B = run(**kw)
        res[lab] = B - A0
        log(f"  {lab:62s} {blocks(B - A0)}")
    d = res[variants[0][0]]
    ERAS = G['ERAS']
    per = []
    for el, a, b in ERAS:
        if el not in ('1998-2008', '2009-2017', '2018-2026'):
            continue
        a0, b0 = a - t1997, min(b, gT - 1) - t1997
        per.append(d[a0:b0].mean())
    blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
    tt = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
    verdict = 'BAT LA RÈGLE (à proposer à François)' if all(x > 0 for x in per) and tt >= 3 else \
        ('positive partout mais t < 3 : fragile' if all(x > 0 for x in per) else 'REJETÉE')
    log(f"\nDÉCISION (règle fixée avant le calcul) : variante principale {' / '.join(f'{x * 52 * 100:+.1f}' for x in per)} "
        f"points par an selon la période, t {tt:.1f} → {verdict}")
    # pires semestres : la piste est censée réduire les krachs de retournement du momentum
    for lab, a, b in (('mars-déc. 2009', '2009-03-01', '2009-12-31'), ('2020 (covid et rebond)', '2020-02-01', '2020-12-31'),
                      ('2022', '2022-01-01', '2022-12-31')):
        ia, ib = (int(np.searchsorted(G['dates'], x)) - t1997 for x in (a, b))
        if 0 <= ia < ib <= len(A0):
            log(f"  {lab:24s} règle actuelle {np.prod(1 + A0[ia:ib]) * 100 - 100:+6.1f} % ; variante principale "
                f"{np.prod(1 + A0[ia:ib] + d[ia:ib]) * 100 - 100:+6.1f} %")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
