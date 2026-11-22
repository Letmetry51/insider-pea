"""Les cours Yahoo du calcul du soir, contrôlés société par société avec EODHD (22/11/2026, François : « Comment exploiter davantage les
données disponibles avec l'abonnement ? … Oui faire ce qui est pertinent »).

Sources contrôlées (celles que le moteur lit) :
  - fiches publiées (data/societes) : clôtures journalières d'un an (« d », ajustées, devise locale : 📣 bond du jour, fiche),
    volumes des 60 dernières séances (« dv » : seuil de 5 fois du bond du jour), clôtures hebdomadaires de 5 ans (« w » : 🎯,
    hausse sur 52 semaines) et volumes de 62 semaines (« wv » : liquidité) ;
  - cours bruts de deux ans des dossiers d'initiés (data/prices.json, cache du calcul du soir, jamais publié).
Comparaison avec les cours EODHD de la même place (même code, nom vérifié) : niveau des cours, dernière clôture, séances fausses
(écart de plus de 5 % à la médiane glissante), séances manquantes, cours figés, volumes (rapport médian, séances au volume faux d'un
facteur 3), semaines fausses (écart de rendement de plus de 10 points), hausse sur 52 semaines du 🎯 (décalée de 4 semaines).
Bourses de l'étude EODHD (Milan absent d'EODHD ; Londres et Suisse hors PEA, non contrôlées). N'imprime que des écarts et des
comptes, jamais de cours EODHD ; rien n'est écrit dans out/ ; la clé n'est jamais affichée. Lancé par « Recherche (à la demande) »
(script audit_yahoo_eodhd.py), environ 3 300 appels.
"""
import collections
import concurrent.futures as cf
import glob
import json
import re
import time
import unicodedata

import numpy as np
import pandas as pd

import survivant_eodhd as SE

log = SE.log
SUF = {'PA': 'PA', 'DE': 'XETRA', 'F': 'F', 'MC': 'MC', 'AS': 'AS', 'BR': 'BR', 'LS': 'LS', 'VI': 'VI', 'HE': 'HE', 'ST': 'ST',
       'CO': 'CO', 'OL': 'OL', 'IR': 'IR'}
STOP = set('ab asa as sa se ag nv plc oyj oy spa a/s s.a. n.v. group holding holdings the de la le du publ class ser series b a inc '
           'ltd limited corp corporation company co bv international'.split())


def nkey(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return [t for t in re.split(r'[^a-z0-9]+', s) if t and t not in STOP]


def same_name(a, b):
    A, B = nkey(a), nkey(b)
    if not A or not B:
        return True  # nom inconnu d'un côté : on ne tranche pas
    if A[0] == B[0] or A[0].startswith(B[0][:5]) or B[0].startswith(A[0][:5]):
        return True
    return len(set(A) & set(B)) / min(len(set(A)), len(set(B))) >= .5


def fiches():
    F, dD, wD = {}, None, None
    for f in sorted(glob.glob('../data/societes/*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception as e:
            log(f"  fiche illisible {f[-8:]} : {type(e).__name__}")
            continue
        dD, wD = dD or d.get('dDates'), wD or d.get('wDates')
        for s, r in (d.get('items') or {}).items():
            F[s] = r
    return F, dD or [], wD or []


def dossiers():
    try:
        P = json.load(open('../data/prices.json', encoding='utf-8'))
    except Exception as e:
        log(f"  cours des dossiers d'initiés (data/prices.json) : {type(e).__name__}")
        return {}
    it = P.get('items', P) if isinstance(P, dict) else {}
    return {v['ticker']: v for v in it.values() if isinstance(v, dict) and v.get('ticker') and v.get('rows')}


def fetch(code):
    x, err = SE.get(f"eod/{code}", **{'from': '2021-10-01'})
    if not x:
        return code, None, err
    try:
        df = pd.DataFrame(x)
        df.index = pd.to_datetime(df['date'], errors='coerce')
        df = df[df.index.notna()]
        out = pd.DataFrame({k: pd.to_numeric(df[k], errors='coerce') for k in ('close', 'adjusted_close', 'volume') if k in df})
        return code, out[~out.index.duplicated()].sort_index(), None
    except Exception as e:
        return code, None, type(e).__name__


def rel_bad(q, thr=.05, win=21):
    """séances dont le rapport des cours s'écarte de plus de thr de sa médiane glissante"""
    s = pd.Series(q)
    m = s.rolling(win, center=True, min_periods=5).median()
    return ((s / m - 1).abs() > thr) & s.notna()


def check_fiche(sym, r, E, dD, wD):
    """écarts d'une fiche publiée avec EODHD ; renvoie {problème: ampleur}"""
    out = {}
    di = pd.DatetimeIndex(pd.to_datetime(dD))
    ea = E['adjusted_close'].where(E['adjusted_close'] > 0)
    ev = E['volume'] if 'volume' in E else pd.Series(dtype=float)
    d = pd.Series([np.nan if v is None else float(v) for v in r.get('d') or []], index=di[:len(r.get('d') or [])])
    if len(d):
        a = ea.reindex(d.index)
        q = (d / a).where((d > 0) & (a > 0))
        n = int(q.notna().sum())
        if n < 40:
            out['trop peu de séances communes'] = n
        else:
            med = float(q.iloc[-60:].median())
            if abs(med - 1) > .03:
                out['niveau des cours différent'] = round((med - 1) * 100, 1)
            nb = int(rel_bad(q.values).sum())
            if nb:
                out['séances fausses (écart > 5 %)'] = nb
            last = di[-1]
            vlast = ev.get(last, np.nan) if len(ev) else np.nan
            if not np.isfinite(d.iloc[-1]) and np.isfinite(a.iloc[-1]) and vlast > 0:
                out['dernière clôture manquante'] = 1
            elif np.isfinite(q.iloc[-1]) and abs(q.iloc[-1] / med - 1) > .02:
                out['dernière clôture différente'] = round((q.iloc[-1] / med - 1) * 100, 1)
            evv = ev.reindex(d.index)
            miss = int(((~np.isfinite(d.values[-60:])) & (evv.values[-60:] > 0)).sum())
            if miss:
                out['séances manquantes (60 dernières)'] = miss
            # cours figés : 5 clôtures Yahoo identiques de suite, alors qu'EODHD bouge au moins 3 fois
            dv_, av_ = d.values, a.values
            run, fz = 0, 0
            for k in range(1, len(dv_)):
                if np.isfinite(dv_[k]) and dv_[k] == dv_[k - 1]:
                    run += 1
                    if run == 4 and np.sum(np.abs(np.diff(av_[k - 4:k + 1])) > 1e-9) >= 3:
                        fz += 1
                else:
                    run = 0
            if fz:
                out['cours figés (5 séances)'] = fz
    dv = r.get('dv') or []
    if dv and len(ev):
        idx = di[-len(dv):]
        y = pd.Series([np.nan if v is None else float(v) for v in dv], index=idx)
        e = ev.reindex(idx)
        m = (y > 0) & (e > 0)
        if m.sum() >= 20:
            lr = np.log(y[m] / e[m])
            medv = float(np.exp(lr.median()))
            if medv < .67 or medv > 1.5:
                out['volumes différents (rapport)'] = round(medv, 2)
            nbv = int((np.abs(lr - lr.median()) > np.log(3)).sum())
            if nbv:
                out['séances au volume faux (facteur 3)'] = nbv
    w = r.get('w') or []
    if w:
        wi = pd.DatetimeIndex(pd.to_datetime(wD[-len(w):]))
        ys = pd.Series([np.nan if v is None else float(v) for v in w], index=wi)
        ew = ea.resample('W-FRI').last().reindex(wi)
        m = ys.notna() & ew.notna()
        if m.sum() >= 60:
            ry, re_ = ys.pct_change(fill_method=None), ew.pct_change(fill_method=None)
            bw = int(((ry - re_).abs() > .10).sum())
            if bw:
                out['semaines fausses (écart > 10 points)'] = bw
            if len(ys) >= 53 and np.isfinite(ys.iloc[-5]) and np.isfinite(ys.iloc[-53]) and np.isfinite(ew.iloc[-5]) and np.isfinite(ew.iloc[-53]):
                dm = (ys.iloc[-5] / ys.iloc[-53] - ew.iloc[-5] / ew.iloc[-53]) * 100
                if abs(dm) > 10:
                    out['hausse sur 52 semaines du 🎯 différente (points)'] = round(dm, 1)
    wv = r.get('wv') or []
    if wv and len(ev):
        wi = pd.DatetimeIndex(pd.to_datetime(wD[-len(wv):]))
        y = pd.Series([np.nan if v is None else float(v) for v in wv], index=wi)
        e = ev.resample('W-FRI').sum(min_count=1).reindex(wi)
        m = (y > 0) & (e > 0)
        if m.sum() >= 26:
            medw = float(np.exp(np.log(y[m] / e[m]).median()))
            if medw < .67 or medw > 1.5:
                out['volumes hebdomadaires différents (rapport)'] = round(medw, 2)
    return out


def check_dossier(t, v, E):
    """cours bruts (non ajustés) de deux ans d'un dossier d'initiés contre les cours bruts EODHD"""
    out = {}
    rows = v.get('rows') or []
    try:
        idx = pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows]))
        c = pd.Series([np.nan if r[4] is None else float(r[4]) for r in rows], index=idx)
        vol = pd.Series([np.nan if r[5] is None else float(r[5]) for r in rows], index=idx)
    except Exception as e:
        return {f'format inattendu ({type(e).__name__})': 1}, []
    c, vol = c[~c.index.duplicated()], vol[~vol.index.duplicated()]
    ec = E['close'].where(E['close'] > 0).reindex(c.index)
    q = (c / ec).where((c > 0) & (ec > 0))
    if q.notna().sum() < 40:
        return {'trop peu de séances communes': int(q.notna().sum())}, []
    med = float(q.iloc[-60:].median())
    if abs(med - 1) > .03:
        out['niveau des cours différent'] = round((med - 1) * 100, 1)
    nb = int(rel_bad(q.values).sum())
    if nb:
        out['séances fausses (écart > 5 %)'] = nb
    if 'volume' in E:
        e = E['volume'].reindex(vol.index)
        m = (vol > 0) & (e > 0)
        if m.sum() >= 40:
            lr = np.log(vol[m] / e[m])
            medv = float(np.exp(lr.iloc[-120:].median()))
            if medv < .67 or medv > 1.5:
                out['volumes différents (rapport)'] = round(medv, 2)
    # dernière clôture (alertes des positions, protection à −30 %) : même séance, même cours
    lc, ld = c.dropna(), E['close'].where(E['close'] > 0).dropna()
    if len(lc) and len(ld):
        if lc.index[-1] < ld.index[-1] - pd.Timedelta(days=4):
            out['dernier cours en retard (jours)'] = int((ld.index[-1] - lc.index[-1]).days)
        elif lc.index[-1] in ld.index and abs(lc.iloc[-1] / ld[lc.index[-1]] / med - 1) > .02:
            out['dernière clôture différente'] = round((lc.iloc[-1] / ld[lc.index[-1]] / med - 1) * 100, 1)
    # sauts bruts de plus de 60 % (ou −37,5 %) en une séance chez EODHD, sans division dans la liste Yahoo : division manquée
    # possible (le moteur l'ajusterait mal), confirmée ensuite par la liste des divisions d'EODHD
    raw = E['close'].where(E['close'] > 0)
    jr = raw / raw.shift(1)
    sp = [pd.Timestamp(x.get('date')) for x in (v.get('splits') or []) if isinstance(x, dict) and x.get('date')]
    jumps = [dte for dte in jr[(jr > 1.6) | (jr < 1 / 1.6)].index
             if c.index[0] <= dte <= c.index[-1] and not any(abs((x - dte).days) <= 5 for x in sp)]
    return out, jumps


def main():
    t0 = time.time()
    if not SE.KEY:
        log("Secret EODHD_API_KEY absent.")
        return
    F, dD, wD = fiches()
    Dz = dossiers()
    log(f"Fiches publiées : {len(F)} sociétés, {len(dD)} séances ({dD[0] if dD else '·'} → {dD[-1] if dD else '·'}), {len(wD)} semaines ; "
        f"dossiers d'initiés avec cours : {len(Dz)}")
    # liste des sociétés de chaque place (codes et noms EODHD)
    lists = {}
    for ex in sorted(set(SUF.values())):
        x, err = SE.get(f"exchange-symbol-list/{ex}")
        lists[ex] = {str(r.get('Code')): r.get('Name') for r in (x or []) if isinstance(r, dict)}
        if err:
            log(f"  liste {ex} : {err}")
    want = {}  # code EODHD → (symbole Yahoo, nom)
    unmatched, badname = collections.Counter(), collections.Counter()
    for sym, name in [(s, r.get('name')) for s, r in F.items()] + [(t, v.get('name')) for t, v in Dz.items()]:
        if '.' not in sym:
            continue
        code, suf = sym.rsplit('.', 1)
        ex = SUF.get(suf)
        if not ex:
            continue
        L = lists.get(ex) or {}
        c2 = next((c for c in (code, code.replace('-', '.'), code.replace('-', '_'), code.replace('-', '')) if c in L), None)
        if c2 is None:
            unmatched[suf] += 1
            continue
        if not same_name(name, L[c2]):
            badname[suf] += 1
            continue
        want[f"{c2}.{ex}"] = (sym, name)
    log(f"Rapprochées avec EODHD : {len(want)} cotations ; code absent chez EODHD : {sum(unmatched.values())} {dict(unmatched)} ; nom "
        f"différent (écartées) : {sum(badname.values())} {dict(badname)}")
    E, errs = {}, collections.Counter()
    with cf.ThreadPoolExecutor(8) as pool:
        for k, (code, df, err) in enumerate(pool.map(fetch, sorted(want))):
            if df is not None and len(df):
                E[want[code][0]] = df
            elif err:
                errs[err] += 1
            if k % 1000 == 999:
                log(f"  {k + 1} séries EODHD en {time.time() - t0:.0f} s")
    log(f"Séries EODHD reçues : {len(E)} ; erreurs {dict(errs) or 'aucune'} ; {time.time() - t0:.0f} s, {SE.calls[0]} appels")
    for lab, items, fn in (("Fiches publiées (d, dv, w, wv)", {s: r for s, r in F.items() if s in E}, lambda s, r: check_fiche(s, r, E[s], dD, wD)),
                           ("Dossiers d'initiés (cours bruts de deux ans)", {t: v for t, v in Dz.items() if t in E}, lambda t, v: check_dossier(t, v, E[t]))):
        res, jumps = {}, {}
        for s, r in items.items():
            try:
                o = fn(s, r)
            except Exception as e:
                o = {f'contrôle impossible ({type(e).__name__})': 1}
            if isinstance(o, tuple):
                o, J = o
                if J:
                    jumps[s] = J
            res[s] = o
        code_of = {sym: code for code, (sym, _) in want.items()}
        nconf = 0
        for s, J in jumps.items():
            x, err = SE.get(f"splits/{code_of[s]}", **{'from': '2021-10-01'})
            es = [pd.Timestamp(z['date']) for z in (x or []) if isinstance(z, dict) and z.get('date')]
            k = sum(1 for dte in J if any(abs((z - dte).days) <= 5 for z in es))
            if k:
                res[s]['division absente de la liste Yahoo (confirmée par EODHD)'] = k
                nconf += 1
        log(f"\n{lab} : {len(res)} sociétés contrôlées")
        if jumps:
            log(f"  sauts bruts de plus de 60 % sans division Yahoo : {len(jumps)} sociétés, dont {nconf} divisions confirmées par EODHD "
                f"(les autres sont de vraies séances extrêmes)")
        by_ex = collections.defaultdict(list)
        for s, o in res.items():
            by_ex[s.rsplit('.', 1)[-1]].append(o)
        probs = sorted({p for o in res.values() for p in o})
        log("  par place, part des sociétés touchées (%) : " + ' ; '.join(
            f"{ex} {len(v)} soc. : " + ', '.join(f"{p.split(' (')[0]} {100 * sum(1 for o in v if p in o) / len(v):.0f}" for p in probs
                                                 if any(p in o for o in v)) for ex, v in sorted(by_ex.items(), key=lambda kv: -len(kv[1]))))
        for p in probs:
            hit = [(s, o[p]) for s, o in res.items() if p in o]
            vals = [abs(v) for _, v in hit if isinstance(v, (int, float))]
            ex_ = sorted(hit, key=lambda z: -abs(z[1]) if isinstance(z[1], (int, float)) else 0)[:12]
            log(f"  {p} : {len(hit)} sociétés ({100 * len(hit) / max(1, len(res)):.1f} %)" +
                (f", médiane {np.median(vals):g}" if vals else '') + " ; " + ', '.join(f"{s} {v:g}" for s, v in ex_))
        clean = sum(1 for o in res.values() if not o)
        log(f"  sans aucun écart : {clean} sur {len(res)} ({100 * clean / max(1, len(res)):.0f} %)")
    u, err = SE.get('user')
    log(f"\nterminé en {time.time() - t0:.0f} s ; {SE.calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
