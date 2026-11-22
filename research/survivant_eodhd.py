"""Test sans biais du survivant (22/11/2026, François a pris un mois de la formule « Historian » d'EODHD : « Faire ce qui est
pertinent »).

Tous les tests de l'outil tournent sur les sociétés encore cotées en 2026 (Yahoo) : les faillites et les sociétés rachetées ou
retirées de la cote manquent. Ici, toutes les actions ordinaires des 13 bourses de l'étude (Paris, Xetra, Milan, Madrid,
Amsterdam, Bruxelles, Lisbonne, Vienne, Helsinki, Stockholm, Copenhague, Oslo, Dublin), cotées ou retirées de la cote, sociétés de
l'EEE (code ISIN ; à Xetra sans ISIN : forme juridique allemande), cours hebdomadaires ajustés EODHD depuis 1998 (sociétés hors
États-Unis : surtout depuis 2000). Liquidité connue à la date : échanges moyens des 26 semaines précédentes, en euros (change
EODHD), au moins 1 M€ par jour. Même sélection que l'outil (4 🎯 + 1 📣 chaque semaine, règles de backtest/_selection_sim.py,
mêmes calculs), portefeuille simulé de 2001 à 2026 (6 mois, frais 0,3 % par sens), avec et sans la protection −30 %.

Univers comparés (mêmes données EODHD) :
  A. sociétés encore cotées, liquides aujourd'hui (comme l'étude Yahoo : reproduit-elle les chiffres ?) ;
  B. sociétés encore cotées, liquidité connue à la date ;
  C. toutes les sociétés, retirées de la cote comprises, liquidité connue à la date : le chiffre honnête.
Une société retirée de la cote est vendue à son dernier cours ; variante : −30 % de plus si elle avait perdu la moitié de sa valeur
sur l'année précédente (disparition probable pour difficultés ; Shumway, 1997, mesure environ −30 % pour ces cas aux États-Unis).
Rendements hebdomadaires bornés à −95 % / +300 % (au lieu de −60 % / +150 % dans les autres études) pour garder les effondrements.

Les cours EODHD restent en mémoire : rien n'est écrit dans research/out (licence d'usage personnel, artefacts publics).
La clé n'est jamais affichée : en cas d'erreur, seuls le code HTTP et le type d'erreur sont imprimés.
Lancé par « Recherche (à la demande) » (script survivant_eodhd.py), environ 30 minutes, 9 000 appels environ.
"""
import concurrent.futures as cf
import gc
import glob
import json
import os
import re
import threading
import time

import numpy as np
import pandas as pd
import requests

import cycle_secteurs as CS
import figures_bougies as FB
import proba as PB

log = FB.log
KEY = os.environ.get('EODHD_API_KEY', '').strip()
EXC = {'PA': 'FR', 'XETRA': 'DE', 'MC': 'ES', 'AS': 'NL', 'BR': 'BE', 'LS': 'PT', 'VI': 'AT', 'HE': 'FI', 'ST': 'SE', 'CO': 'DK',
       'OL': 'NO', 'IR': 'IE'}
YSUF = {'XETRA': 'DE'}  # suffixe Yahoo quand il diffère du code EODHD
EEA = set('AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IS IT LI LT LU LV MT NL NO PL PT RO SE SI SK'.split())
CUR = {'EUR', 'SEK', 'NOK', 'DKK'}
JUNK = re.compile(r'\b(rights?|warrants?|bezugsrechte?|droits?|wts|certificates?|tracker|etf|etc|fund|fonds|sicav)\b', re.I)
LEGAL_DE = re.compile(r'\b(AG|SE|KGaA|GmbH)\b')
LIQ = 1e6
_lock = threading.Lock()
_last = [0.0]
calls = [0]


def get(path, **params):
    """Appel EODHD, au plus 14 par seconde ; renvoie (données, erreur) sans jamais exposer l'adresse (qui contient la clé)."""
    for a in range(5):
        with _lock:
            w = _last[0] + 1 / 14 - time.time()
            if w > 0:
                time.sleep(w)
            _last[0] = time.time()
            calls[0] += 1
        try:
            r = requests.get('https://eodhd.com/api/' + path, params={'api_token': KEY, 'fmt': 'json', **params}, timeout=90)
        except Exception as e:
            err = type(e).__name__
            time.sleep(2 + 3 * a)
            continue
        if r.status_code == 200:
            try:
                return r.json(), None
            except Exception as e:
                return None, type(e).__name__
        err = f'HTTP {r.status_code}'
        if r.status_code in (404, 401, 402, 403):
            return None, err
        time.sleep(3 + 5 * a)
    return None, err


_fri = {}


def friday(d):
    f = _fri.get(d)
    if f is None:
        t = pd.Timestamp(d)
        f = _fri[d] = (t + pd.Timedelta(days=(4 - t.weekday()) % 7)).normalize()
    return f


def universe():
    """Lignes retenues : actions ordinaires de l'EEE en EUR, SEK, NOK ou DKK, une par ISIN (cotée d'abord, bourse d'origine)."""
    x, err = get('exchanges-list/')
    if err:
        log(f"  liste des bourses : {err}")
    ita = [e.get('Code') for e in (x or []) if str(e.get('CountryISO2') or '').upper() == 'IT' or 'ital' in str(e.get('Country') or '').lower()]
    log(f"  bourses italiennes connues d'EODHD : {ita or 'aucune'}")
    best = None
    for c in list(dict.fromkeys(ita[:4] + ['MI', 'MIL', 'BIT', 'XMIL', 'MTA'])):
        y, e2 = get(f'exchange-symbol-list/{c}')
        n = sum(1 for r in (y or []) if r.get('Type') == 'Common Stock' and str(r.get('Isin') or '')[:2] == 'IT')
        log(f"  bourse « {c} » : {n} actions ordinaires italiennes cotées" + (f" ({e2})" if e2 else ''))
        if n and (best is None or n > best[1]):
            best = (c, n)
    if best:
        EXC[best[0]] = 'IT'
        YSUF[best[0]] = 'MI'
    else:
        log("  bourse italienne introuvable chez EODHD : Milan absent du test")
    rows, stat = [], {}
    for ex, cc in EXC.items():
        for dl in (0, 1):
            y, err = get(f'exchange-symbol-list/{ex}', **({'delisted': 1} if dl else {}))
            if err:
                log(f"  {ex} {'retirées' if dl else 'cotées'} : {err}")
            kept = 0
            for r in y or []:
                name, isin = str(r.get('Name') or ''), str(r.get('Isin') or '')
                if r.get('Type') != 'Common Stock' or r.get('Currency') not in CUR or JUNK.search(name):
                    continue
                if isin:
                    if isin[:2] not in EEA:
                        continue
                elif ex == 'XETRA' and not LEGAL_DE.search(name):
                    continue
                rows.append(dict(sym=f"{r['Code']}.{ex}", code=r['Code'], ex=ex, cc=cc, isin=isin, cur=r.get('Currency'), dl=dl))
                kept += 1
            stat[(ex, dl)] = kept
    # une ligne par ISIN : cotée avant retirée, bourse d'origine d'abord
    rows.sort(key=lambda r: (r['dl'], 0 if r['isin'][:2] == r['cc'] else 1))
    seen, out = set(), []
    for r in rows:
        if r['isin']:
            if r['isin'] in seen:
                continue
            seen.add(r['isin'])
        out.append(r)
    log("  lignes retenues par bourse (cotées / retirées) : " +
        ' · '.join(f"{ex} {stat.get((ex, 0), 0)}/{stat.get((ex, 1), 0)}" for ex in EXC))
    log(f"  après dédoublonnage par ISIN : {sum(1 for r in out if not r['dl'])} cotées, {sum(1 for r in out if r['dl'])} retirées")
    return out


def download(rows, idx):
    """Cours hebdomadaires (clôture ajustée, clôture brute, volume) sur les vendredis idx."""
    pos = {d: k for k, d in enumerate(idx)}
    N, T = len(rows), len(idx)
    P, C, V = (np.full((N, T), np.nan, np.float32) for _ in range(3))
    errs = {}

    def one(k):
        x, err = get(f"eod/{rows[k]['sym']}", period='w', **{'from': '1998-01-01'})
        return k, x, err
    t0 = time.time()
    with cf.ThreadPoolExecutor(8) as pool:
        for n, (k, x, err) in enumerate(pool.map(one, range(N))):
            if err:
                errs[err] = errs.get(err, 0) + 1
            for b in x or []:
                j = pos.get(friday(b['date']))
                if j is None:
                    continue
                try:
                    a, c, v = float(b.get('adjusted_close') or 'nan'), float(b.get('close') or 'nan'), float(b.get('volume') or 0)
                except (TypeError, ValueError):
                    continue
                if a > 0 and c > 0:
                    P[k, j], C[k, j], V[k, j] = a, c, v
            if n % 1000 == 999:
                log(f"  {n + 1} séries en {time.time() - t0:.0f} s")
    log(f"  téléchargé : {N} séries en {time.time() - t0:.0f} s ; erreurs {errs or 'aucune'}")
    return P, C, V


def despike(P):
    """Retire les pics isolés d'une semaine (×3 puis ÷3, ou l'inverse) : erreurs de cotation, pas des effondrements."""
    n = 0
    for i in range(P.shape[0]):
        p = P[i]
        ok = np.where(np.isfinite(p))[0]
        if len(ok) < 3:
            continue
        q = p[ok[1:]] / p[ok[:-1]]
        bad = np.where(((q[:-1] > 3) & (q[1:] < 1 / 3)) | ((q[:-1] < 1 / 3) & (q[1:] > 3)))[0]
        if len(bad):
            P[i, ok[bad + 1]] = np.nan
            n += len(bad)
    return n


def sectors(rows):
    """Secteurs Yahoo des sociétés connues de l'outil (universe.json, catalogue) ; sinon un secteur propre à la société."""
    sec = {}
    for k, v in json.load(open('../data/sectors/universe.json'))['items'].items():
        sec[k] = v.get('sector')
    for f in glob.glob('../data/societes/*.json'):
        for k, x in json.load(open(f))['items'].items():
            sec.setdefault(k, x.get('sector'))
    out, hit = [], 0
    for r in rows:
        s = sec.get(f"{r['code']}.{YSUF.get(r['ex'], r['ex'])}")
        hit += bool(s)
        out.append(s or ('?' + r['sym']))
    return out, hit


def chain(P, V, dates, cols, secs, okmask):
    """Mêmes calculs que proba.load() (backtest/_depart.py … _selection_sim.py), sur ces cours ; liquidité connue à la date."""
    os.chdir('backtest')
    try:
        # backtest/_depart.py lit long.npz : fichier temporaire, effacé aussitôt (jamais dans research/out)
        np.savez_compressed('long.npz', P=P.astype('float32'), V=V.astype('float32'), dates=np.array(dates),
                            cols=np.array(cols), sec=np.array(secs))
        G = {'__name__': 'selection_sim'}
        exec(compile(open('_selection_sim2.py').read().split('print("Écart avec')[0], '_selection_sim2.py', 'exec'), G)
        G['okn'] = G['okn'] & okmask
        exec(compile(PB.SIM, 'proba.SIM', 'exec'), G)
    finally:
        if os.path.exists('long.npz'):
            os.remove('long.npz')
        os.chdir('..')
    return G


def main():
    t00 = time.time()
    if not KEY:
        log("Secret EODHD_API_KEY absent : rien à faire.")
        return
    u, err = get('user')
    log(f"Formule « {(u or {}).get('subscriptionType')} », {(u or {}).get('apiRequests')} appels utilisés aujourd'hui" if u else f"Compte : {err}")
    rows = universe()
    idx = list(pd.date_range('1998-01-02', pd.Timestamp.today().normalize() - pd.Timedelta(days=1), freq='W-FRI'))
    P, C, V = download(rows, idx)
    dates = [str(d.date()) for d in idx]
    T = len(idx)
    # change (devise locale pour 1 €), échanges par jour en euros, moyenne des 26 semaines précédentes
    fx = {'EUR': np.ones(T)}
    for c in ('SEK', 'NOK', 'DKK'):
        x, err = get(f'eod/EUR{c}.FOREX', period='w', **{'from': '1998-01-01'})
        s = pd.Series({friday(b['date']): float(b['close']) for b in x or [] if b.get('close')})
        fx[c] = s.reindex(idx).ffill().bfill().values if len(s) else np.full(T, np.nan)
        log(f"  change EUR/{c} : {len(s)} semaines" + ('' if len(s) else f" ({err})"))
    cur = np.array([r['cur'] for r in rows])
    FXm = np.vstack([fx[c] for c in cur])
    tov = np.where(np.isfinite(C) & np.isfinite(V), C * V / 5 / FXm, np.nan)
    liq = pd.DataFrame(tov.T).rolling(26, min_periods=13).mean().values.T
    nspk = despike(P)
    valid = np.isfinite(P).sum(1) >= 104
    ever = np.nanmax(np.where(np.isfinite(liq), liq, 0), 1) >= LIQ
    keep = valid & ever
    dl = np.array([r['dl'] for r in rows], bool)
    log(f"  pics isolés retirés : {nspk} ; sociétés liquides à un moment (≥ 1 M€ par jour, 2 ans de cours) : {int((keep & ~dl).sum())} "
        f"cotées, {int((keep & dl).sum())} retirées de la cote")
    ki = np.where(keep)[0]
    rows = [rows[k] for k in ki]
    P, C, V, liq, dl = P[ki], C[ki], V[ki], liq[ki], dl[ki]
    cols = [r['sym'] for r in rows]
    secs, hit = sectors(rows)
    log(f"  secteur connu pour {hit} des {len(rows)} sociétés (les autres : un secteur propre, sans plafond)")
    last = np.array([np.where(np.isfinite(p))[0].max() for p in P])
    gone = dl & (last < T - 3)
    for y in (2001, 2005, 2010, 2015, 2020, 2025):
        t = int(np.searchsorted(dates, f'{y}-06-01'))
        inv = np.isfinite(P[:, t]) & (liq[:, t] >= LIQ)
        log(f"  {y} : {int((inv & ~dl).sum())} sociétés investissables encore cotées aujourd'hui, {int((inv & dl).sum())} disparues depuis")
    # disparitions « après une chute » : la moitié de la valeur perdue sur l'année précédant le dernier cours
    drop = np.array([P[i, last[i]] / np.nanmax(P[i, max(0, last[i] - 52):last[i] + 1]) - 1 for i in range(len(P))])
    perf = gone & (drop <= -.5)
    log(f"  sociétés disparues de l'univers : {int(gone.sum())}, dont {int(perf.sum())} après une chute de moitié sur l'année")

    t2001 = int(np.searchsorted(dates, '2001-01-01'))
    ERAS = [('2001-2008', t2001, int(np.searchsorted(dates, '2009-01-01'))),
            ('2009-2017', int(np.searchsorted(dates, '2009-01-01')), int(np.searchsorted(dates, '2018-01-01'))),
            ('2018-2026', int(np.searchsorted(dates, '2018-01-01')), T - 1)]

    def measure(lab, G, haircut=False, relaxed=True):
        G['t1997'] = t2001
        r1 = G['r1']
        retw = np.clip(np.nan_to_num(r1), -.95, 3.0) if relaxed else np.clip(np.nan_to_num(r1), -.6, 1.5)
        if haircut:
            for i in np.where(G['_perf'])[0]:
                if G['_last'][i] + 1 < T:
                    retw[i, G['_last'][i] + 1] = -.30
        G['retw'] = retw
        okn = G['okn']
        mk = np.array([np.mean(retw[okn[:, t - 1], t]) if t and okn[:, t - 1].sum() > 30 else 0.0 for t in range(T)])
        G['mkw'] = mk
        out = {}
        for nm, f in (('sans protection', lambda: CS.weekly_slots(G, lambda t: G['SEL'].get(t, []))), ('protection −30 %', G['sim30'])):
            R = f()
            M = mk[t2001 + 1:T]
            cells = []
            for el, a, b in ERAS:
                x, m = R[a - t2001:b - t2001], M[a - t2001:b - t2001]
                cells.append(f"{el} {(np.prod(1 + x) ** (52 / len(x)) - 1) * 100:+.1f} (marché {(np.prod(1 + m) ** (52 / len(m)) - 1) * 100:+.1f})")
            eq = np.cumprod(1 + R)
            dd = (eq / np.maximum.accumulate(eq) - 1).min()
            cg = (eq[-1] ** (52 / len(R)) - 1) * 100
            cm = (np.prod(1 + M) ** (52 / len(M)) - 1) * 100
            d = R - M
            blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
            tv = blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk)))
            out[nm] = (cg, cm)
            log(f"    {lab} · {nm:16s} {cg:+.1f} %/an contre {cm:+.1f} pour le marché (écart t {tv:.1f}), pire baisse {dd * 100:.0f} % · "
                + ' · '.join(cells))
        return out

    def picks_report(G, lab):
        """Écart à 6 mois des sociétés choisies, et sort de celles qui disparaissent dans les 6 mois."""
        retw, okn, SEL = G['retw'], G['okn'], G['SEL']
        Lr = np.log1p(retw)
        Cc = np.concatenate([np.zeros((Lr.shape[0], 1)), np.cumsum(Lr, 1)], 1)
        ex, tt, n, ng, rg = [], [], 0, 0, []
        for t in range(t2001, T - 27):
            s = list(SEL.get(t, []))
            if not s:
                continue
            fw = np.clip(np.expm1(Cc[:, t + 27] - Cc[:, t + 1]), -1, 5)
            ex.append(np.mean(fw[s]) - np.mean(fw[okn[:, t]]))
            tt.append(t)
            for i in s:
                n += 1
                if G['_gone'][i] and t < G['_last'][i] <= t + 26:
                    ng += 1
                    rg.append(fw[i])
        ex, tt = np.array(ex), np.array(tt)
        per = ' · '.join(f"{el} {ex[(tt >= a) & (tt < b)].mean() * 100:+.1f}" for el, a, b in ERAS)
        log(f"    {lab} : écart des sociétés choisies à 6 mois {ex.mean() * 100:+.1f} points ({per}) ; {ng} choix sur {n} "
            f"({ng / max(n, 1) * 100:.1f} %) disparus dans les 6 mois, rendement moyen de ces lignes "
            f"{np.mean(rg) * 100 if rg else float('nan'):+.0f} %")

    log(f"\nCalculs prêts en {time.time() - t00:.0f} s ({calls[0]} appels)")
    res = {}
    # A. encore cotées et liquides aujourd'hui (comme l'étude Yahoo)
    A = ~dl & (liq[:, -1] >= LIQ)
    for lab, sel, tv_ in (('A. cotées, liquides aujourd\'hui', A, False), ('B. cotées, liquidité à la date', ~dl, True),
                          ('C. toutes, disparues comprises', np.ones(len(rows), bool), True)):
        ii = np.where(sel)[0]
        okm = (liq[ii] >= LIQ) if tv_ else np.ones((len(ii), T), bool)
        t0 = time.time()
        G = chain(P[ii], V[ii], dates, [cols[i] for i in ii], [secs[i] for i in ii], okm)
        G['_gone'], G['_perf'], G['_last'] = gone[ii], perf[ii], last[ii]
        log(f"\n  {lab} : {len(ii)} sociétés ({int(gone[ii].sum())} disparues), calcul en {time.time() - t0:.0f} s")
        if lab.startswith('A'):
            res[lab + ' (bornes −60 % / +150 %)'] = measure(lab[:2] + ' bornes habituelles', G, relaxed=False)
        res[lab] = measure(lab[:2] + ' sortie au dernier cours', G)
        picks_report(G, lab[:2] + ' sortie au dernier cours')
        if lab.startswith('C'):
            M = G['mkw'][t2001 + 1:T]
            for nm, R in (('10 lignes (8 🎯 + 2 📣), sans protection', CS.weekly_slots(G, lambda t, g=G: g['SEL10'].get(t, []), n=10)),
                          ('frais 0,5 % par sens, sans protection', CS.weekly_slots(G, lambda t, g=G: g['SEL'].get(t, []), cost=.005))):
                cells = ' · '.join(f"{el} {(np.prod(1 + R[a - t2001:b - t2001]) ** (52 / (b - a)) - 1) * 100:+.1f}" for el, a, b in ERAS)
                log(f"    C. {nm:42s} {(np.prod(1 + R) ** (52 / len(R)) - 1) * 100:+.1f} %/an (marché {(np.prod(1 + M) ** (52 / len(M)) - 1) * 100:+.1f}) · {cells}")
            res[lab + ' −30 %'] = measure(lab[:2] + ' −30 % après une chute', G, haircut=True)
            picks_report(G, lab[:2] + ' −30 % après une chute')
        del G
        gc.collect()
    log("\nRésumé (rendement par an, protection −30 % comprise, et écart avec le marché de chaque univers)")
    for k, v in res.items():
        cg, cm = v['protection −30 %']
        log(f"  {k:46s} {cg:+.1f} %/an, marché {cm:+.1f}, écart {cg - cm:+.1f} points par an")
    u, err = get('user')
    log(f"\nterminé en {time.time() - t00:.0f} s ; {calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
