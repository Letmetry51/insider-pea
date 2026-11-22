"""Alerte « krach du momentum » sur 40 ans d'indices EODHD (22/11/2026, François : « Comment exploiter davantage les données
disponibles avec l'abonnement ? … Oui faire ce qui est pertinent »), pour préparer le choix « pause des achats pendant l'alerte
krach » de la revue du 31/01/2027 (mesuré sans biais du survivant sur 2001-2026 : environ 2 points de moins par an, pire baisse
−33 % au lieu de −47 %, research/survivant_pratique.py).

Règle de l'outil (ES.MOM_CRASH_M52 / ES.MOM_CRASH_OFF) : alerte allumée quand le marché a perdu 20 % ou plus en 52 semaines,
éteinte au-dessus de −15 %. L'outil la calcule sur la moyenne équipondérée de ses sociétés ; ici, faute de cours de sociétés avant
1998, sur les indices : CAC 40 (depuis 1987), DAX (dividendes compris, depuis 1980), STOXX Europe 600 et Euro STOXX 50 (depuis
1986), hors dividendes sauf le DAX. Mesures : épisodes d'alerte (dates, durée, baisse encore subie, marché 6 et 12 mois après), et
« pause des achats » réduite à sa part de marché : 26 tranches achetées chaque semaine et gardées 26 semaines, sans achat pendant
l'alerte (la place libérée reste en liquidités à 0 %), face aux achats continus, par période (avant 1998 : période jamais utilisée
pour régler l'outil). Le second effet de la pause, éviter les sociétés en forte hausse quand le marché rebondit (krach du momentum,
Daniel et Moskowitz), demande les cours des sociétés : il n'est pas mesuré ici.
Une dizaine d'appels ; rien n'est écrit dans out/ ; la clé n'est jamais affichée. Lancé par « Recherche (à la demande) »
(script krach_indices.py).
"""
import numpy as np
import pandas as pd

import survivant_eodhd as SE

log = SE.log
IDX = (('CAC 40', 'FCHI.INDX'), ('DAX (dividendes compris)', 'GDAXI.INDX'), ('STOXX Europe 600', 'SXXP.INDX'),
       ('Euro STOXX 50', 'STOXX50E.INDX'))
ON, OFF = -20.0, -15.0


def weekly(code):
    x, err = SE.get(f"eod/{code}", period='w', **{'from': '1970-01-01'})
    if not x:
        return None, err
    s = pd.Series({SE.friday(b['date']): float(b.get('adjusted_close') or b.get('close') or 'nan') for b in x if b.get('date')})
    s = s[~s.index.duplicated()].sort_index()
    s = s[s > 0]
    idx = pd.date_range(s.index[0], s.index[-1], freq='W-FRI')
    return s.reindex(idx).ffill(), None


def alert(m52):
    """allumée à −20 % sur 52 semaines, éteinte au-dessus de −15 % (pas de va-et-vient)"""
    on, st = np.zeros(len(m52), bool), False
    for t, v in enumerate(m52):
        if np.isfinite(v):
            st = (v <= OFF) if st else (v <= ON)
        on[t] = st
    return on


def ann(r):
    r = r[np.isfinite(r)]
    return (np.prod(1 + r) ** (52 / len(r)) - 1) * 100 if len(r) > 26 else np.nan


def mdd(r):
    r = np.nan_to_num(r)
    eq = np.cumprod(1 + r)
    return (eq / np.maximum.accumulate(eq) - 1).min() * 100


def main():
    if not SE.KEY:
        log("Secret EODHD_API_KEY absent.")
        return
    for lab, code in IDX:
        s, err = weekly(code)
        if s is None:
            log(f"\n{lab} : {err}")
            continue
        p = s.values
        dates = s.index
        m52 = np.full(len(p), np.nan)
        m52[52:] = (p[52:] / p[:-52] - 1) * 100
        on = alert(m52)
        r = np.full(len(p), np.nan)
        r[:-1] = p[1:] / p[:-1] - 1          # rendement de la semaine t à t+1
        log(f"\n{lab} : {dates[0].date()} → {dates[-1].date()}, alerte allumée {on[52:].mean() * 100:.0f} % des semaines")
        # épisodes
        ep, t = [], 52
        while t < len(p):
            if on[t] and not on[t - 1]:
                u = t
                while u + 1 < len(p) and on[u + 1]:
                    u += 1
                ep.append((t, u))
                t = u + 1
            else:
                t += 1
        for a, b in ep:
            low = p[a:b + 1].min() / p[a] - 1
            f26 = p[a + 26] / p[a] - 1 if a + 26 < len(p) else np.nan
            f52 = p[a + 52] / p[a] - 1 if a + 52 < len(p) else np.nan
            fin = p[min(b + 1, len(p) - 1)] / p[a] - 1
            log(f"  {dates[a].date()} → {dates[min(b + 1, len(p) - 1)].date()} ({b - a + 1} sem.) : baisse sur 52 sem. {m52[a]:.0f} % à "
                f"l'allumage ; ensuite pire {low * 100:+.0f} %, à l'extinction {fin * 100:+.0f} % ; 6 mois après l'allumage "
                f"{f26 * 100:+.0f} %, 12 mois {f52 * 100:+.0f} %")
        # pause des achats : part investie = tranches achetées hors alerte sur les 26 dernières semaines
        buy = (~on).astype(float)
        frac = pd.Series(buy).rolling(26, min_periods=26).mean().values
        rp = frac * r
        rf = r.copy()
        y = np.array(dates.year)
        per = [('avant 1998', y[0] + 1, 1997), ('1998-2008', 1998, 2008), ('2009-2017', 2009, 2017), ('2018-2026', 2018, 2026),
               ('tout', y[0] + 1, 2026)]
        cells = []
        for pl, a_, b_ in per:
            m = (y >= a_) & (y <= b_) & np.isfinite(frac) & np.isfinite(r)
            if m.sum() < 52:
                continue
            on_r = r[m & on]
            cells.append(f"{pl} : achats continus {ann(rf[m]):+.1f} %/an (pire baisse {mdd(rf[m]):.0f} %), avec pause {ann(rp[m]):+.1f} "
                         f"({mdd(rp[m]):.0f} %) ; marché pendant l'alerte {ann(on_r) if len(on_r) > 26 else float('nan'):+.0f} %/an sur "
                         f"{int((m & on).sum())} sem.")
        log("  pause des achats (part de marché seulement) :\n    " + '\n    '.join(cells))
    u, err = SE.get('user')
    log(f"\n{SE.calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
