"""Cycle économique et bourse : les pistes de la littérature pas encore testées dans l'outil (22/11/2026, François : « Vérifier
toute la littérature économique et boursière qui existe sur le sujet (mathématique...etc) et améliorer l'outil »).

Chaque piste dit qu'un « état » du marché ou de l'économie annonce un momentum plus faible ; on la mesure sur la sélection actuelle
(4 🎯 + 1 📣 chaque semaine, règles de backtest/_selection_sim.py) :
1. État du marché (Cooper, Gutierrez et Hameed, 2004) : le momentum ne paierait qu'après 3 ans de hausse du marché.
2. Panique (Daniel et Moskowitz, 2016) : marché en baisse sur 2 ans et très agité ; le momentum s'effondre au rebond.
3. Dispersion des cours (Stivers et Sun, 2010) : quand les sociétés divergent beaucoup, la prime du momentum baisse.
4. Courbe des taux (Estrella et Mishkin, 1998) : taux américain à 10 ans passé sous le taux à 3 mois dans l'année (Yahoo ^TNX et
   ^IRX) : récession probable dans les 12 à 18 mois.
5. Modèle de Markov à 2 régimes (Hamilton, 1989 ; Kritzman, Page et Turkington, 2012) : régime calme ou agité du marché, estimé
   chaque 1er janvier avec les seules semaines passées, probabilité filtrée semaine par semaine (sans regarder la suite).
6. Illiquidité du marché (Avramov, Cheng et Hameed, 2016) : momentum plus faible quand le marché devient peu liquide (mesure
   d'Amihud de chaque société face à ses 3 années précédentes, médiane des sociétés).
Marché : moyenne des sociétés de l'étude (parts égales ; sociétés encore cotées, biais du survivant). Seuils « élevé » : tiers
supérieur de l'historique connu à la date (5 ans au moins).

Mesures : écart des sociétés choisies avec la moyenne des sociétés sur les 26 semaines suivantes, selon l'état (t de Newey-West,
26 retards) ; rendement du marché selon l'état ; variantes applicables dans un PEA, portefeuille simulé : dans l'état défavorable,
acheter l'indice (toutes les sociétés à parts égales) au lieu des 🎯 et 📣, ou garder les liquidités.
Pour information (dates connues après coup) : récessions de la zone euro datées par le comité du CEPR (2008-2009, 2011-2013,
2020) et phases du tableau du cycle (cycle_secteurs.py).
7. Surapprentissage (Bailey et López de Prado, 2014) : ratio de Sharpe « dégonflé » de l'avance de la règle actuelle sur le marché
   (rendements de 13 semaines), pour 100 à 10 000 essais.

Règle fixée avant le calcul : une variante ne remplace la règle actuelle que si elle fait mieux dans chacune des périodes 1998-2008,
2009-2017 et 2018-2026, avec t ≥ 3 sur l'ensemble (blocs de 26 semaines) ; sinon, résultat documenté (research/README.md et aide).
Lancé par « Recherche (à la demande) » (script cycle_litterature.py), environ 10 minutes.
"""
import time
from statistics import NormalDist

import numpy as np
import pandas as pd

import cycle_secteurs as CS
import figures_bougies as FB
import proba as PB

log = FB.log
ERAS3 = ('1998-2008', '2009-2017', '2018-2026')
ND = NormalDist()


def yields(dates):
    """Taux américains à 10 ans et à 3 mois (Yahoo ^TNX, ^IRX), dernière clôture connue à chaque vendredi de l'étude."""
    import yfinance as yf
    idx = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    out = {}
    for s in ('^TNX', '^IRX'):
        for k in range(3):
            try:
                df = yf.download(s, start='1985-01-01', interval='1d', auto_adjust=False, progress=False)
                c = df['Close']
                if isinstance(c, pd.DataFrame):
                    c = c.iloc[:, 0]
                c = c.dropna()
                c.index = pd.to_datetime(c.index).tz_localize(None)
                c = c[~c.index.duplicated()].sort_index()
                if len(c) > 1000:
                    out[s] = c.reindex(idx, method='ffill').values
                    log(f"  {s} : {len(c)} séances, depuis le {c.index[0].date()}")
                    break
            except Exception as e:  # source absente : la piste est sautée, le reste continue
                log(f"  {s} : {type(e).__name__} {e}")
            time.sleep(5)
    return out


def past_pct(x, minp=260):
    """Rang de x[t] dans son historique connu à t (0 à 1), à partir de minp semaines."""
    out = np.full(len(x), np.nan)
    for t in range(len(x)):
        if not np.isfinite(x[t]):
            continue
        h = x[:t + 1]
        h = h[np.isfinite(h)]
        if len(h) >= minp:
            out[t] = (h < x[t]).mean()
    return out


def hmm2(x, init=None, iters=300, tol=1e-5):
    """Baum-Welch à 2 régimes gaussiens (Hamilton, 1989). Renvoie mu, sd, A (transitions), pi."""
    n = len(x)
    if init is None:
        m, s = x.mean(), x.std()
        mu, sd = np.array([m + .1 * s, m - .4 * s]), np.array([.7 * s, 1.7 * s])
        A, pi = np.array([[.97, .03], [.08, .92]]), np.array([.5, .5])
    else:
        mu, sd, A, pi = (np.array(v, float) for v in init)
    last = -np.inf
    for _ in range(iters):
        B = np.maximum(np.exp(-.5 * ((x[:, None] - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi)), 1e-300)
        al, c = np.zeros((n, 2)), np.zeros(n)
        al[0] = pi * B[0]
        c[0] = al[0].sum()
        al[0] /= c[0]
        for t in range(1, n):
            al[t] = (al[t - 1] @ A) * B[t]
            c[t] = al[t].sum()
            al[t] /= c[t]
        be = np.ones((n, 2))
        for t in range(n - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
        ga = al * be
        ga /= ga.sum(1, keepdims=True)
        xi = al[:-1, :, None] * A[None] * (B[1:] * be[1:])[:, None, :] / c[1:, None, None]
        A = xi.sum(0) / xi.sum(0).sum(1, keepdims=True)
        pi = ga[0]
        w = ga.sum(0)
        mu = (ga * x[:, None]).sum(0) / w
        sd = np.maximum(np.sqrt((ga * (x[:, None] - mu) ** 2).sum(0) / w), 1e-4)
        ll = np.log(c).sum()
        if ll - last < tol:
            break
        last = ll
    return mu, sd, A, pi


def hmm_filter(x, mu, sd, A, pi):
    """Probabilités filtrées P(régime | semaines jusqu'à t), sans regarder la suite."""
    n = len(x)
    B = np.maximum(np.exp(-.5 * ((x[:, None] - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi)), 1e-300)
    al = np.zeros((n, 2))
    a = pi * B[0]
    al[0] = a / a.sum()
    for t in range(1, n):
        a = (al[t - 1] @ A) * B[t]
        al[t] = a / a.sum()
    return al


def states(G, Y):
    """État « défavorable au momentum » de chaque semaine, selon chaque piste (booléens, connus à la date)."""
    T, mkw, okn, P, dates = G['T'], G['mkw'], G['okn'], G['P'], G['dates']
    L = np.cumsum(np.log1p(mkw))

    def past(k):
        r = np.full(T, np.nan)
        r[k:] = np.expm1(L[k:] - L[:-k])
        return r
    t0 = int(np.argmax([okn[:, t - 1].sum() > 30 if t else False for t in range(T)]))
    S, info = {}, {}
    S['cgh'] = past(156) < 0
    vol = pd.Series(mkw).rolling(26, min_periods=26).std().values * np.sqrt(52)
    vol[:t0 + 26] = np.nan
    S['panique'] = (past(104) < 0) & (past_pct(vol) >= 2 / 3)
    # dispersion : écart-type entre sociétés des hausses sur 4 semaines (2 % extrêmes coupés), moyenne de 13 semaines
    with np.errstate(all='ignore'):
        r4 = P / np.concatenate([np.full((P.shape[0], 4), np.nan), P[:, :-4]], 1) - 1
    rd = np.full(T, np.nan)
    for t in range(t0 + 4, T):
        v = r4[okn[:, t], t]
        v = v[np.isfinite(v)]
        if len(v) > 30:
            lo, hi = np.percentile(v, [2, 98])
            rd[t] = np.clip(v, lo, hi).std()
    rdm = pd.Series(rd).rolling(13, min_periods=13).mean().values
    S['dispersion'] = past_pct(rdm) >= 2 / 3
    # courbe des taux américaine : 10 ans − 3 mois négatif au moins une semaine dans l'année écoulée
    if '^TNX' in Y and '^IRX' in Y:
        sp = Y['^TNX'] - Y['^IRX']
        inv = pd.Series(sp < 0).rolling(52, min_periods=1).max().values.astype(bool)
        S['courbe'] = inv & np.isfinite(sp)
        info['courbe'] = sp
    # Markov à 2 régimes sur les rendements hebdomadaires du marché, réestimé chaque 1er janvier (semaines passées seulement)
    yr = G['yr']
    p_ag = np.full(T, np.nan)
    init = None
    for y in range(int(yr[G['t1997']]), int(yr[-1]) + 1):
        a = int(np.searchsorted(yr, y))
        b = int(np.searchsorted(yr, y + 1))
        x = mkw[t0:a]
        mu, sd, A, pi = hmm2(x, init=init)
        init = (mu, sd, A, pi)
        ag = int(np.argmax(sd))
        al = hmm_filter(mkw[t0:b], mu, sd, A, pi)
        p_ag[a:b] = al[a - t0:b - t0, ag]
        if y in (1998, 2009, 2018, int(yr[-1])):
            k = 1 - ag
            info.setdefault('hmm', []).append(
                f"{y} : calme {mu[k] * 5200:+.0f} %/an, volatilité {sd[k] * np.sqrt(52) * 100:.0f} % ; agité {mu[ag] * 5200:+.0f} %/an, "
                f"{sd[ag] * np.sqrt(52) * 100:.0f} % ; durée moyenne du régime agité {1 / max(1 - A[ag, ag], 1e-9):.0f} semaines")
    S['markov'] = p_ag > .5
    # illiquidité d'Amihud : |rendement| / capitaux échangés, moyenne de 26 semaines face aux 3 années précédentes
    VO = G['VO']
    with np.errstate(all='ignore'):
        am = np.abs(G['r1']) / (P * VO)
    am = np.where(np.isfinite(am) & (am > 0), am, np.nan)
    a26 = pd.DataFrame(am.T).rolling(26, min_periods=20).mean()
    base = a26.shift(26).rolling(156, min_periods=104).median()
    rel = np.log(a26 / base).values.T
    ilq = np.array([np.nanmedian(rel[okn[:, t], t]) if np.isfinite(rel[okn[:, t], t]).sum() > 30 else np.nan for t in range(T)])
    S['illiquidite'] = past_pct(ilq) >= 2 / 3
    info['t0'] = dates[t0]
    return S, p_ag, info


REC = [('2008-04-01', '2009-06-30'), ('2011-10-01', '2013-03-31'), ('2020-01-01', '2020-06-30')]
LAB = {'cgh': "marché en baisse sur 3 ans (Cooper et al.)", 'panique': "panique : baisse sur 2 ans et forte agitation",
       'dispersion': "forte dispersion des cours (Stivers et Sun)", 'courbe': "courbe des taux inversée dans l'année",
       'markov': "régime agité (Markov à 2 régimes)", 'illiquidite': "marché peu liquide (Amihud)"}


def hac(y, x, L=26):
    """y = a + b·x : a, b et t de Newey-West (L retards)."""
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok].astype(float)
    X = np.column_stack([np.ones(len(y)), x])
    Q = np.linalg.inv(X.T @ X)
    b = Q @ X.T @ y
    Z = X * (y - X @ b)[:, None]
    Sg = Z.T @ Z
    for k in range(1, L + 1):
        g = Z[k:].T @ Z[:-k]
        Sg += (1 - k / (L + 1)) * (g + g.T)
    se = np.sqrt(np.diag(Q @ Sg @ Q))
    return b, b / se


def slots(G, f, n=5, hold=26, cost=.003):
    """Comme cycle_secteurs.weekly_slots ; f(t) peut aussi renvoyer 'M' : l'indice (toutes les sociétés à parts égales, la
    tranche entière) ; [] : liquidités."""
    t1997, T, retw, okn = G['t1997'], G['T'], G['retw'], G['okn']
    sleeves, R = [], []
    for t in range(t1997, T - 1):
        s = f(t)
        if isinstance(s, str):
            idx = np.where(okn[:, t])[0]
            w, inv = np.ones(len(idx)) / len(idx), 1.0
        else:
            idx = np.array(s, dtype=int)
            w, inv = np.ones(len(idx)) / n, len(idx) / n
        sleeves.append([t, idx, w])
        sleeves = [x for x in sleeves if t - x[0] < hold]
        r = 0.0
        for x in sleeves:
            if len(x[1]):
                rr = retw[x[1], t + 1]
                r += (x[2] * rr).sum()
                x[2] = x[2] * (1 + rr)
        R.append(r / hold - cost * 2 * inv / hold)
    return np.array(R)


def dsr(x, trials):
    """Ratio de Sharpe dégonflé (Bailey et López de Prado, 2014) : probabilité que le vrai ratio soit positif, compte tenu du
    meilleur ratio attendu par hasard sur « trials » essais indépendants, de l'asymétrie et des queues épaisses."""
    x = x[np.isfinite(x)]
    n, m, s = len(x), x.mean(), x.std(ddof=1)
    sr = m / s
    g3 = ((x - m) ** 3).mean() / x.std() ** 3
    g4 = ((x - m) ** 4).mean() / x.std() ** 4
    eg = .5772156649
    emax = (1 - eg) * ND.inv_cdf(1 - 1 / trials) + eg * ND.inv_cdf(1 - 1 / (trials * np.e))
    sr0 = emax / np.sqrt(n - 1)
    z = (sr - sr0) * np.sqrt(n - 1) / np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-9))
    return sr, g3, g4, sr0, ND.cdf(z)


def main():
    t0 = time.time()
    G = PB.load()
    t1997, T, ERAS, retw, okn, SEL, mkw = (G[k] for k in ('t1997', 'T', 'ERAS', 'retw', 'okn', 'SEL', 'mkw'))
    log(f"données prêtes en {time.time() - t0:.0f} s")
    Y = yields(G['dates'])
    S, p_ag, info = states(G, Y)
    log(f"états calculés en {time.time() - t0:.0f} s (marché mesuré depuis le {info['t0']})")
    for line in info.get('hmm', []):
        log("  Markov " + line)
    eras = [(el, a, min(b, T - 1)) for el, a, b in ERAS if el in ERAS3]

    # 0. Part des semaines dans l'état défavorable et nombre d'épisodes
    log("\n0. Semaines dans l'état défavorable au momentum (part par période, épisodes de 4 semaines ou plus)")
    for k, s in S.items():
        cells = []
        for el, a, b in eras:
            x = s[a:b]
            runs = np.diff(np.concatenate([[0], x.astype(int), [0]]))
            st, en = np.where(runs == 1)[0], np.where(runs == -1)[0]
            cells.append(f"{el} {x.mean() * 100:3.0f} % ({int(((en - st) >= 4).sum())} ép.)")
        log(f"  {LAB[k]:46s} " + ' · '.join(cells))

    # 1. Écart des sociétés choisies sur les 26 semaines suivantes, et rendement du marché, selon l'état
    with np.errstate(all='ignore'):
        Lr = np.log1p(np.where(np.isfinite(retw), retw, 0.0))
        C = np.concatenate([np.zeros((Lr.shape[0], 1)), np.cumsum(Lr, 1)], 1)
    e, mk = np.full(T, np.nan), np.full(T, np.nan)
    for t in range(t1997, T - 27):
        fw = np.clip(np.expm1(C[:, t + 27] - C[:, t + 1]), -.95, 5)
        ok = okn[:, t]
        m = np.nanmean(fw[ok])
        mk[t] = m
        s = list(SEL.get(t, []))
        if s:
            e[t] = np.nanmean(fw[s]) - m
    tt = np.arange(T)
    log("\n1. 26 semaines suivantes, en points de % : écart des sociétés choisies avec la moyenne (autres semaines → état "
        "défavorable), et rendement du marché")
    yy = e[np.isfinite(e)]
    log(f"  {'toutes les semaines':46s} écart {yy.mean() * 100:+5.1f}")
    for k, s in S.items():
        b, tv = hac(e, s.astype(float))
        bm, tm = hac(mk, s.astype(float))
        cells = []
        for el, a, c in eras:
            w = (tt >= a) & (tt < c) & np.isfinite(e)
            g, d = e[w & ~s], e[w & s]
            cells.append(f"{el} {g.mean() * 100:+5.1f} → {d.mean() * 100:+5.1f}" if len(d) >= 8 else f"{el} {g.mean() * 100:+5.1f} → —")
        log(f"  {LAB[k]:46s} écart {b[0] * 100:+5.1f} → {(b[0] + b[1]) * 100:+5.1f} (différence t {tv[1]:4.1f}) · "
            + ' · '.join(cells))
        log(f"  {'':46s} marché {bm[0] * 100:+5.1f} → {(bm[0] + bm[1]) * 100:+5.1f} (t {tm[1]:4.1f})")
    # pour information, dates connues après coup : récessions de la zone euro (comité du CEPR) et phases du tableau du cycle
    d = np.array([str(x) for x in G['dates']])
    rec = np.zeros(T, bool)
    for a, b in REC:
        rec |= (d >= a) & (d <= b)
    b, tv = hac(e, rec.astype(float))
    bm, tm = hac(mk, rec.astype(float))
    log(f"  {'récession de la zone euro (CEPR, après coup)':46s} écart {b[0] * 100:+5.1f} → {(b[0] + b[1]) * 100:+5.1f} "
        f"(différence t {tv[1]:4.1f}) ; marché {bm[0] * 100:+5.1f} → {(bm[0] + bm[1]) * 100:+5.1f} (t {tm[1]:4.1f}) ; "
        f"{int(rec[t1997:].sum())} semaines")
    FIT, PH = CS.phases(G)
    labels = {c['key']: c['label'] for c in CS.CYCLE}
    for el, a, c in eras:
        cells = []
        for k, lab in labels.items():
            w = (tt >= a) & (tt < c) & np.isfinite(e) & (PH == k)
            cells.append(f"{lab} {e[w].mean() * 100:+5.1f} ({w.sum()} sem.)" if w.sum() >= 8 else f"{lab} —")
        log(f"  phase du tableau du cycle, {el} : " + ' · '.join(cells))

    # 2. Variantes applicables dans un PEA
    ref = CS.weekly_slots(G, lambda t: SEL.get(t, []))
    same = np.allclose(slots(G, lambda t: list(SEL.get(t, []))), ref)
    log(f"\ncopie du portefeuille simulé identique à l'original : {same}")

    def cagr(R):
        out = []
        for el, a, b in eras:
            x = R[a - t1997:b - t1997]
            out.append(f"{el} {(np.prod(1 + x) ** (52 / len(x)) - 1) * 100:+.1f}")
        eq = np.cumprod(1 + R)
        dd = (eq / np.maximum.accumulate(eq) - 1).min()
        return f"{(eq[-1] ** (52 / len(R)) - 1) * 100:+.1f} %/an (pire baisse {dd * 100:.0f} %) · " + ' · '.join(out)

    def vs_ref(lab, R):
        d = R - ref
        out, ok_all = [], True
        for el, a, b in eras:
            x = d[a - t1997:b - t1997]
            out.append(f"{el} {x.mean() * 52 * 100:+5.1f}")
            ok_all &= x.mean() > 0
        blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
        tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
        v = ' → BAT LA RÈGLE ACTUELLE' if ok_all and tv >= 3 else ' → rejetée'
        log(f"  {lab:58s} {cagr(R)}\n  {'':58s} écart : {' · '.join(out)} pts/an, t {tv:4.1f}{v}")

    log("\n2. Portefeuille simulé (4 🎯 + 1 📣, 26 semaines, frais compris) : dans l'état défavorable, l'indice ou les liquidités")
    log(f"  {'règle actuelle':58s} {cagr(ref)}")
    log(f"  {'indice (toutes les sociétés à parts égales), pour comparer':58s} {cagr(slots(G, lambda t: 'M'))}")
    for k, s in S.items():
        vs_ref(f"{LAB[k]} : l'indice", slots(G, lambda t, s=s: 'M' if s[t] else list(SEL.get(t, []))))
        vs_ref(f"{LAB[k]} : liquidités", slots(G, lambda t, s=s: [] if s[t] else list(SEL.get(t, []))))

    # 3. Surapprentissage : ratio de Sharpe dégonflé de l'avance sur le marché, rendements de 13 semaines
    M = mkw[t1997 + 1:T]
    q = [(np.prod(1 + ref[k:k + 13]) - np.prod(1 + M[k:k + 13])) for k in range(0, len(ref) - 12, 13)]
    q = np.array(q)
    log("\n3. Avance de la règle actuelle sur le marché, par trimestre (13 semaines)")
    for n in (100, 1000, 10000):
        sr, g3, g4, sr0, p = dsr(q, n)
        log(f"  {n:6d} essais : ratio de Sharpe annuel {sr * 2:.2f} (asymétrie {g3:+.1f}, aplatissement {g4:.1f}) ; meilleur ratio "
            f"attendu par hasard {sr0 * 2:.2f} ; probabilité d'une avance réelle {p * 100:.1f} %")
    for el, a, b in eras:
        qq = np.array([(np.prod(1 + ref[k:k + 13]) - np.prod(1 + M[k:k + 13])) for k in range(a - t1997, b - t1997 - 12, 13)])
        sr, g3, g4, sr0, p = dsr(qq, 1000)
        log(f"  {el} : ratio de Sharpe annuel {sr * 2:.2f}, probabilité d'une avance réelle sur 1 000 essais {p * 100:.1f} %")
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
