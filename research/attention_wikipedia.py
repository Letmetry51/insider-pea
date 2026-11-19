"""Attention des internautes (19/11/2026, François : « est-ce qu'il y aurait une méthode de suivre les recherches internet ou
l'augmentation soudaine des forums sur une action qui permettrait d'anticiper une future hausse ? (discussion, nombre de
recherche...etc) », puis « faire ce qui est pertinent »).

Les forums (Boursorama, Reddit, X) n'ont pas d'historique accessible ; Google Trends ne donne que des indices relatifs, souvent
nuls pour les valeurs moyennes, et limite fortement les requêtes (sondé ici). Mesure retenue : les consultations quotidiennes de
la page Wikipédia de chaque société (API Wikimedia, depuis juillet 2015, robots exclus), en anglais, français, allemand et dans
la langue du pays de la société, additionnées. Sociétés de l'étude longue (cours journaliers Yahoo, survivantes : biais du
survivant, mêmes sociétés pour la référence), reliées à Wikidata par leur site officiel puis par leur code de cotation.

Signaux, par semaine (vendredi) :
- pic d'attention : consultations de la semaine au moins doublées (puis triplées) par rapport à la médiane des 8 semaines
  précédentes (« attention anormale » de Da, Engelberg et Gao, 2011), page vue 20 fois par semaine au moins ;
- pic sans mouvement de cours (semaine entre −5 et +5 %), pic avec hausse de 5 % ou plus, pic avec baisse de 5 % ou plus ;
- montée durable : 4 dernières semaines à 1,5 fois la moyenne des 26 précédentes ;
- niveau d'attention : consultations rapportées aux capitaux échangés (sociétés méconnues contre très suivies, tiers de la semaine).
Croisements : zone du 🎯 (en tendance, +60 à +200 % sur 12 mois) avec ou sans pic ; 📣 bond du jour (+8 % sur 5 fois le volume
moyen de 50 séances, clôture dans la moitié haute, en tendance) avec ou sans pic la même semaine.

Mesure : achat à l'ouverture de la séance suivante, écart avec la moyenne des sociétés à 1 semaine, 1, 3, 6 et 12 mois, une
entrée par société et par semestre, t regroupé par mois ; trois périodes 2015-2019 / 2020-2022 / 2023-2026 (pas de données
Wikipédia avant juillet 2015). Règle fixée avant le calcul : un signal d'attention ne compte que s'il bat la moyenne à 6 mois
dans chacune des trois périodes avec t ≥ 3 ; pour compléter le 🎯 ou le 📣, il doit faire mieux qu'eux sans lui dans chaque
période. Lancé par « Recherche (à la demande) » (script attention_wikipedia.py), environ 25 minutes.
"""
import concurrent.futures as cf
import glob
import json
import re
import time
import urllib.parse

import numpy as np
import pandas as pd
import requests

import figures_bougies as FB
import hausse_tot as HT
import hausse_tot3 as H3

log, shift, dedup, roll = FB.log, FB.shift, FB.dedup, HT.roll
UA = {'User-Agent': 'EuroSignal-research/1.0 (https://github.com/Letmetry51/insider-pea; recherche ponctuelle)'}
WDQS = 'https://query.wikidata.org/sparql'
HOME = {'FR': ['fr'], 'BE': ['fr', 'nl'], 'LU': ['fr'], 'NL': ['nl'], 'DE': ['de'], 'AT': ['de'], 'CH': ['de', 'fr'], 'IT': ['it'],
        'ES': ['es'], 'PT': ['pt'], 'IE': ['en'], 'GB': ['en'], 'FI': ['fi'], 'SE': ['sv'], 'DK': ['da'], 'NO': ['no'], 'PL': ['pl'],
        'GR': ['el'], 'CZ': ['cs'], 'HU': ['hu']}
EXCH = {'PA': 'paris', 'AS': 'amsterdam', 'BR': 'brussels', 'LS': 'lisbon', 'IR': 'dublin|irish', 'DE': 'frankfurt|xetra|deutsche',
        'MI': 'italiana|milan|italian', 'MC': 'madrid|spanish|bme', 'ST': 'stockholm', 'HE': 'helsinki', 'CO': 'copenhagen',
        'OL': 'oslo', 'VI': 'vienna|wiener', 'L': 'london', 'SW': 'six|swiss', 'WA': 'warsaw', 'AT': 'athens'}
PERIODS = ((2015, 2020), (2020, 2023), (2023, 2027))


def sparql(q, tries=4):
    for a in range(tries):
        try:
            r = requests.get(WDQS, params={'query': q, 'format': 'json'}, headers=UA, timeout=180)
            if r.status_code == 200:
                return r.json()['results']['bindings']
            log(f"  Wikidata : HTTP {r.status_code}, nouvel essai")
        except Exception as e:
            log(f"  Wikidata : {str(e)[:80]}, nouvel essai")
        time.sleep(10 * (a + 1))
    return None


def domain(url):
    try:
        h = urllib.parse.urlparse(url if '//' in url else 'http://' + url).netloc.lower().split(':')[0]
    except Exception:
        return None
    h = re.sub(r'^www\d?\.', '', h)
    p = h.split('.')
    if len(p) >= 3 and len(p[-1]) == 2 and p[-2] in ('co', 'com', 'net', 'org', 'gov', 'ac'):
        return '.'.join(p[-3:])
    return '.'.join(p[-2:]) if len(p) >= 2 else None


def norm_tick(t):
    return re.sub(r'[^A-Z0-9]', '', (t or '').upper())


def companies(symbols):
    cat = {}
    for f in glob.glob('../data/societes/*.json'):
        cat.update(json.load(open(f))['items'])
    return {s: cat.get(s, {}) for s in symbols}


def wikidata_links(info):
    """Société → élément Wikidata (site officiel, puis code de cotation sur la même place)."""
    rows, failed = [], 0
    for rx in ('euronext', 'frankfurt|xetra|deutsche b', 'italiana|milan', 'madrid|spanish|bme', 'nasdaq|stockholm|helsinki|copenhagen',
               'oslo|vienna|wiener|warsaw|athens|irish', 'london|six swiss'):
        q = ('SELECT ?item ?web ?ticker ?exl WHERE { ?item p:P414 ?st . ?st ps:P414 ?ex . OPTIONAL { ?st pq:P249 ?ticker } '
             'OPTIONAL { ?item wdt:P856 ?web } ?ex rdfs:label ?exl . FILTER(LANG(?exl) = "en") '
             f'FILTER(REGEX(?exl, "{rx}", "i")) }}')
        part = sparql(q)
        if part is None:
            failed += 1
            continue
        rows += part
    if not rows:
        log("  Wikidata injoignable : étude impossible")
        return {}
    if failed:
        log(f"  Wikidata : {failed} requête(s) sur 7 sans réponse")
    by_dom, by_tick = {}, {}
    for b in rows:
        it = b['item']['value'].rsplit('/', 1)[-1]
        if 'web' in b:
            d = domain(b['web']['value'])
            if d:
                by_dom.setdefault(d, set()).add(it)
        if 'ticker' in b:
            by_tick.setdefault((norm_tick(b['ticker']['value']), b['exl']['value'].lower()), set()).add(it)
    log(f"  Wikidata : {len(rows)} cotations européennes, {len(by_dom)} sites, {len(by_tick)} codes")
    out, how = {}, {'site': 0, 'code': 0}
    for s, x in info.items():
        d = domain(x.get('web') or '') if x.get('web') else None
        cand = by_dom.get(d, set()) if d else set()
        if len(cand) == 1:
            out[s] = next(iter(cand))
            how['site'] += 1
            continue
        base, _, suf = s.rpartition('.')
        rx = EXCH.get(suf)
        hits = set()
        if rx:
            for (tk, exl), its in by_tick.items():
                if tk == norm_tick(base) and re.search(rx, exl):
                    hits |= its
        if cand:
            hits = (hits & cand) or hits
        if len(hits) == 1:
            out[s] = next(iter(hits))
            how['code'] += 1
    log(f"  reliées : {len(out)} sur {len(info)} (par le site {how['site']}, par le code {how['code']})")
    return out


def sitelinks(qids, langs):
    res = {}
    ql = sorted(set(qids))
    sites = ' '.join(f'<https://{lg}.wikipedia.org/>' for lg in sorted(langs))
    for i in range(0, len(ql), 200):
        vals = ' '.join('wd:' + q for q in ql[i:i + 200])
        rows = sparql(f'SELECT ?item ?article ?site WHERE {{ VALUES ?item {{ {vals} }} VALUES ?site {{ {sites} }} '
                      f'?article schema:about ?item ; schema:isPartOf ?site . }}')
        for b in rows or []:
            it = b['item']['value'].rsplit('/', 1)[-1]
            lg = b['site']['value'].split('//')[1].split('.')[0]
            title = urllib.parse.unquote(b['article']['value'].split('/wiki/', 1)[1])
            res.setdefault(it, {})[lg] = title
        time.sleep(1)
    return res


def pageviews(lang, title, end):
    url = ('https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/'
           f'{lang}.wikipedia/all-access/user/{urllib.parse.quote(title, safe="")}/daily/20150701/{end}')
    for a in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 200:
                it = r.json().get('items', [])
                return pd.Series({pd.Timestamp(x['timestamp'][:8]): x['views'] for x in it}, dtype='float64')
            if r.status_code == 404:
                return None
            time.sleep(2 * (a + 1))
        except Exception:
            time.sleep(2 * (a + 1))
    return None


def probe_trends():
    """Google Trends répond-il depuis GitHub ? (page d'accueil puis requête « explore » pour un nom de société)."""
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'fr-FR,fr;q=0.9'})
    try:
        r0 = s.get('https://trends.google.com/trends/?geo=FR', timeout=30)
        req = json.dumps({'comparisonItem': [{'keyword': 'Euronext', 'geo': 'FR', 'time': 'today 5-y'}], 'category': 7,
                          'property': ''})
        r1 = s.get('https://trends.google.com/trends/api/explore', params={'hl': 'fr', 'tz': '-60', 'req': req}, timeout=30)
        log(f"  Google Trends : accueil HTTP {r0.status_code}, requête de données HTTP {r1.status_code}"
            + (" (trop de requêtes : bloqué depuis GitHub)" if r1.status_code == 429 else ""))
    except Exception as e:
        log(f"  Google Trends injoignable : {str(e)[:80]}")


def stats(lab, M, EX, RAW, months, yrs):
    lab_h = {5: '1 s', 21: '1 m', 63: '3 m', 125: '6 m', 250: '12 m'}
    out = []
    n6 = 0
    for h, X in EX.items():
        ii, tt = np.where(M & np.isfinite(X))
        if len(ii) < 30:
            out.append(f"{lab_h[h]}   ·  ")
            continue
        e = X[ii, tt]
        if h == 125:
            n6 = len(ii)
            g = pd.Series(e).groupby(months[tt]).mean()
            tv = g.mean() / (g.std(ddof=1) / np.sqrt(len(g))) if len(g) > 10 else np.nan
            pp = []
            for a, b in PERIODS:
                m = (yrs[tt] >= a) & (yrs[tt] < b)
                pp.append(f"{e[m].mean() * 100:+5.1f}" if m.sum() >= 20 else "  ·  ")
            r = RAW[ii, tt]
            out.append(f"6 m {e.mean() * 100:+5.1f} (t {tv:4.1f}) [{' / '.join(pp)}] ≥+50 % {np.mean(r >= .5) * 100:4.1f} %")
        else:
            out.append(f"{lab_h[h]} {e.mean() * 100:+5.1f}")
    log(f"  {lab:58s} {n6:5d} | " + " · ".join(out))


def main():
    t0 = time.time()
    log("=== Sources")
    probe_trends()
    syms = sorted(FB.universe())
    info = companies(syms)
    links = wikidata_links(info)
    if not links:
        return
    langs = {'en', 'fr', 'de'} | {lg for s in links for lg in HOME.get(info[s].get('country') or '', [])}
    sl = sitelinks(links.values(), langs)
    jobs = []
    for s, q in links.items():
        want = {'en', 'fr', 'de'} | set(HOME.get(info[s].get('country') or '', []))
        for lg, title in sl.get(q, {}).items():
            if lg in want:
                jobs.append((s, lg, title))
    log(f"  pages Wikipédia : {len(jobs)} pour {len({j[0] for j in jobs})} sociétés ({time.time() - t0:.0f} s)")
    end = (pd.Timestamp.today() - pd.Timedelta(days=1)).strftime('%Y%m%d')
    views = {}
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(pageviews, lg, title, end): s for s, lg, title in jobs}
        for f in cf.as_completed(futs):
            v = f.result()
            if v is not None and len(v):
                s = futs[f]
                views[s] = v if s not in views else views[s].add(v, fill_value=0)
    log(f"  consultations lues pour {len(views)} sociétés ({time.time() - t0:.0f} s)")

    D = FB.download(syms)
    O, H, L, C, V = (D[k].values.T.astype('float32') for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    dates = D['Close'].index
    cols = list(D['Close'].columns)
    yrs, months = np.array(dates.year), np.array(dates.year * 100 + dates.month)
    N, T = C.shape
    log(f"cours : {N} sociétés, {T} séances ({time.time() - t0:.0f} s)")
    with np.errstate(all='ignore'):
        ok = np.isfinite(O) & np.isfinite(C) & (np.nan_to_num(V) > 0)
        C1 = shift(C, 1)
        ret1 = C / C1 - 1
        Vp = np.where(V > 0, V, np.nan).astype(np.float32)
        vx = V / shift(roll(Vp, 50, 'mean', 40), 1)
        m50, m200 = roll(C, 50, 'mean'), roll(C, 200, 'mean', 180)
        trend = (C > m200) & (m50 > m200)
        clv = (C - L) / (H - L)
        mom = shift(C, 21) / shift(C, 252) - 1
        turn = roll(np.where(ok, C * V, np.nan).astype(np.float32), 63, 'mean', 50)
        zone = ok & trend & (mom >= .6) & (mom <= 2.0) & (turn >= 1e6)
        bond = ok & (ret1 >= .08) & (vx >= 5) & (clv >= .5) & trend & (turn >= 1e6)

    # semaines (vendredi) : dernière séance de cotation de chaque semaine dans le calendrier commun
    wk = pd.Series(np.arange(T), index=dates).groupby(dates.to_period('W-FRI')).max()
    wend = wk.values                                   # indice de séance de fin de semaine
    wper = wk.index
    A = {k: np.zeros((N, T), bool) for k in ('pic2', 'pic3', 'pic_calme', 'pic_hausse', 'pic_baisse', 'durable', 'data')}
    pic_wk = np.zeros((N, len(wend)), bool)
    has_wk = np.zeros((N, len(wend)), bool)
    att = np.full((N, T), np.nan, np.float32)          # consultations moyennes par semaine sur 26 semaines (niveau)
    wret_all = []
    for i, s in enumerate(cols):
        v = views.get(s)
        if v is None:
            continue
        w = v.resample('W-FRI').sum()
        w = w.reindex(wper.to_timestamp(how='end').normalize(), fill_value=np.nan)
        wv = w.values.astype(float)
        base = pd.Series(wv).shift(1).rolling(8, min_periods=8).median().values
        lvl26 = pd.Series(wv).rolling(26, min_periods=20).mean().values
        prev26 = pd.Series(wv).shift(4).rolling(26, min_periods=20).mean().values
        last4 = pd.Series(wv).rolling(4, min_periods=4).mean().values
        with np.errstate(all='ignore'):
            awv = np.log1p(wv) - np.log1p(base)
            good = np.isfinite(awv) & (base >= 20)
            cw = C[i, wend]
            cw_prev = np.concatenate([[np.nan], cw[:-1]])
            wret = cw / cw_prev - 1
        p2, p3 = good & (awv >= np.log(2)), good & (awv >= np.log(3))
        dur = np.isfinite(last4) & np.isfinite(prev26) & (prev26 >= 20) & (last4 >= 1.5 * prev26)
        pic_wk[i], has_wk[i] = p2, good
        idx = wend
        A['pic2'][i, idx] = p2
        A['pic3'][i, idx] = p3
        A['pic_calme'][i, idx] = p2 & (np.abs(wret) < .05)
        A['pic_hausse'][i, idx] = p2 & (wret >= .05)
        A['pic_baisse'][i, idx] = p2 & (wret <= -.05)
        A['durable'][i, idx] = dur
        A['data'][i, idx] = good
        att[i, idx] = lvl26
        wret_all.append(wret[p2 & np.isfinite(wret)])
    n_co = int(A['data'].any(1).sum())
    wr = np.concatenate(wret_all) if wret_all else np.array([])
    log(f"sociétés avec consultations utilisables : {n_co} ; pics d'attention (×2) : {int(A['pic2'].sum())}, dont semaine en "
        f"hausse de 5 % ou plus {np.mean(wr >= .05) * 100:.0f} %, en baisse de 5 % ou plus {np.mean(wr <= -.05) * 100:.0f} %, "
        f"cours de la semaine du pic {np.nanmean(wr) * 100:+.1f} % en moyenne")
    start = dates >= pd.Timestamp('2015-09-01')
    for k in A:
        A[k] &= start[None, :] & ok & (turn >= 1e6)
    # croisements : décision en fin de semaine, quand les consultations de la semaine sont connues (achat à l'ouverture suivante)
    is_end = np.zeros(T, bool)
    is_end[wend] = True
    bond_wk = np.zeros((N, len(wend)), bool)
    for w0 in range(len(wend)):
        a = wend[w0 - 1] + 1 if w0 else 0
        bond_wk[:, w0] = bond[:, a:wend[w0] + 1].any(1)
    zone_end = np.zeros((N, T), bool)
    bond_end = np.zeros((N, T), bool)
    spike_end = np.zeros((N, T), bool)
    has_end = np.zeros((N, T), bool)
    zone_end[:, wend] = zone[:, wend]
    bond_end[:, wend] = bond_wk
    spike_end[:, wend] = pic_wk
    has_end[:, wend] = has_wk

    EX, RAW = {}, None
    for h in (5, 21, 63, 125, 250):
        e, r = H3.excess(C, O, yrs, h)
        e[:, ~start] = np.nan
        EX[h] = e
        if h == 125:
            RAW = r

    def S(lab, X, k=125):
        stats(lab, dedup(X, k), EX, RAW, months, yrs)

    log("\nÉcart avec la moyenne des sociétés (points de %), achat à l'ouverture suivante, une entrée par société et par semestre")
    log("=== Pics d'attention (consultations Wikipédia de la semaine contre la médiane des 8 précédentes)")
    S("consultations au moins doublées", A['pic2'])
    S("consultations au moins triplées", A['pic3'])
    S("  doublées, cours de la semaine entre −5 et +5 %", A['pic_calme'])
    S("  doublées, semaine en hausse de 5 % ou plus", A['pic_hausse'])
    S("  doublées, semaine en baisse de 5 % ou plus", A['pic_baisse'])
    S("montée durable (4 semaines à 1,5 fois les 26 d'avant)", A['durable'])
    S("court terme : tous les pics ×2, une entrée par 10 séances", A['pic2'], 10)
    log("=== Niveau d'attention : consultations rapportées aux capitaux échangés, tiers de la semaine")
    with np.errstate(all='ignore'):
        ratio = np.where(A['data'] & np.isfinite(att) & (att > 0), np.log(att) - np.log(turn), np.nan)
        R = pd.DataFrame(ratio.T).rank(axis=1, pct=True).values.T
    with np.errstate(invalid='ignore'):
        r_lo, r_mid, r_hi = (R > 0) & (R <= 1 / 3), (R > 1 / 3) & (R < 2 / 3), R >= 2 / 3
    S("sociétés méconnues (tiers le moins consulté)", r_lo)
    S("tiers du milieu", r_mid)
    S("sociétés très suivies (tiers le plus consulté)", r_hi)
    log("=== Avec la méthode")
    base_z = zone_end & has_end & start[None, :]
    S("zone du 🎯 en fin de semaine (pages suivies)", base_z)
    S("  zone du 🎯 et pic d'attention cette semaine", base_z & spike_end)
    S("  zone du 🎯 sans pic", base_z & ~spike_end)
    base_b = bond_end & has_end & start[None, :]
    S("📣 bond du jour dans la semaine (achat en fin de semaine)", base_b)
    S("  bond et pic d'attention la même semaine", base_b & spike_end)
    S("  bond sans pic", base_b & ~spike_end)
    log(f"\nterminé en {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
