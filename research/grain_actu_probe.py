"""Grain Signal — sonde avant d'intégrer l'actualité, la géopolitique et la psychologie des marchés.

A. Sources d'actualité joignables depuis GitHub Actions : GDELT (articles et tonalité), Google Actualités (RSS), flux de la
   presse agricole, indice de risque géopolitique (Caldara et Iacoviello, quotidien et par pays).
B. Psychologie des marchés : un indice « peur ↔ euphorie » (RSI, écart à la MM200, élan sur 20 séances, position des fonds)
   annonce-t-il la suite ? Rendements des 20 et 60 séances suivantes par tranche d'indice (Chicago depuis 2000, Euronext depuis
   2019), par période.
C. Risque géopolitique et tonalité de l'actualité → rendement suivant du blé.

Lit le cache des historiques Grain Signal (data/grain/prive), rien n'est publié.   python grain_actu_probe.py
Résultat : out/grain_actu_probe.txt
"""
import bisect
import csv
import io
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "grain_signal"))
PRIV = os.path.join(ROOT, "data", "grain", "prive")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)


def get(url, **kw):
    try:
        r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 40), **kw)
        return r
    except Exception as e:  # noqa: BLE001
        log("   erreur", type(e).__name__, str(e)[:150])
        return None


# ------------------------------------------------------------------------------------------------ A. sources
def gdelt():
    log("\n== GDELT (DOC 2.0) ==")
    base = "https://api.gdeltproject.org/api/v2/doc/doc"
    for q in ['wheat (russia OR ukraine OR "black sea")', '(fertilizer OR urea OR ammonia) (sanctions OR export OR hormuz)',
              'blé sourcelang:french', '(wheat OR corn OR grain) (tariff OR embargo OR war)']:
        r = get(base, params={"query": q, "mode": "artlist", "format": "json", "maxrecords": 25, "timespan": "3d", "sort": "datedesc"})
        if r is None:
            continue
        try:
            arts = r.json().get("articles") or []
        except Exception:  # noqa: BLE001
            log(f"   {q!r} : HTTP {r.status_code}, réponse non JSON : {r.text[:150]!r}")
            continue
        log(f"   {q!r} : HTTP {r.status_code}, {len(arts)} articles")
        for a in arts[:4]:
            log(f"      {a.get('seendate')} {a.get('domain')} [{a.get('language')}] {a.get('title', '')[:110]}")
        time.sleep(6)
    out = {}
    for q, lab in (('wheat', 'blé'), ('wheat (russia OR ukraine OR "black sea")', 'blé mer Noire'), ('fertilizer', 'engrais')):
        for span in ("5y", "24m", "12m"):
            r = get(base, params={"query": q, "mode": "timelinetone", "format": "json", "timespan": span, "timelinesmooth": 7})
            time.sleep(6)
            if r is None:
                continue
            try:
                tl = (r.json().get("timeline") or [{}])[0].get("data") or []
            except Exception:  # noqa: BLE001
                log(f"   tonalité {lab} {span} : HTTP {r.status_code} {r.text[:120]!r}")
                continue
            log(f"   tonalité {lab} {span} : {len(tl)} points, {tl[0]['date'] if tl else '-'} → {tl[-1]['date'] if tl else '-'}"
                + (f", dernière {tl[-1]['value']:.2f}" if tl else ""))
            if tl:
                out[lab] = [(x["date"][:8], x["value"]) for x in tl]
                break
    return out


def rss(url):
    r = get(url)
    if r is None:
        return None, []
    try:
        root = ET.fromstring(r.content)
    except Exception:  # noqa: BLE001
        return r.status_code, []
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out = []
    for it in items:
        t = it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or ""
        d = it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}updated") or ""
        out.append((d[:25], t.strip()[:120]))
    return r.status_code, out


def flux():
    log("\n== Google Actualités (RSS de recherche) ==")
    g = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl}"
    for q, hl, gl in (("blé exportations Russie when:3d", "fr", "FR"), ("marché des céréales when:2d", "fr", "FR"),
                      ("wheat export Russia when:3d", "en", "US"), ("urea fertilizer prices when:7d", "en", "US"),
                      ("Euronext blé when:3d", "fr", "FR")):
        code, items = rss(g.format(q=requests.utils.quote(q), hl=hl, gl=gl))
        log(f"   {q!r} : HTTP {code}, {len(items)} articles")
        for d, t in items[:4]:
            log(f"      {d} {t}")
    log("\n== Flux de la presse agricole ==")
    for u in ("https://www.terre-net.fr/rss", "https://www.terre-net.fr/rss.xml", "https://www.terre-net.fr/feed",
              "https://www.web-agri.fr/rss", "https://www.reussir.fr/rss.xml", "https://www.reussir.fr/grandes-cultures/rss.xml",
              "https://www.world-grain.com/rss/articles", "https://www.world-grain.com/rss", "https://farmdocdaily.illinois.edu/feed",
              "https://www.euractiv.com/sections/agriculture-food/feed/", "https://ukragroconsult.com/en/feed/",
              "https://www.agriculture.com/markets/rss", "https://www.farmprogress.com/rss.xml", "https://www.grainews.ca/feed/",
              "https://www.franceagrimer.fr/rss", "https://www.pleinchamp.com/rss", "https://www.agri-mutuel.com/feed/",
              "https://www.lafranceagricole.fr/rss", "https://www.agrimoney.com/rss", "https://www.fao.org/newsroom/rss/en/"):
        code, items = rss(u)
        log(f"   {u} : HTTP {code}, {len(items)} articles" + (f" — {items[0][0]} {items[0][1]}" if items else ""))


def gpr():
    log("\n== Indice de risque géopolitique (Caldara et Iacoviello) ==")
    import pandas as pd
    res = {}
    for nom, u in (("quotidien", "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"),
                   ("mensuel", "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls")):
        r = get(u, timeout=90)
        if r is None:
            continue
        log(f"   {nom} : HTTP {r.status_code}, {len(r.content)} octets, {r.headers.get('last-modified')}")
        if r.status_code != 200:
            continue
        try:
            df = pd.read_excel(io.BytesIO(r.content))
        except Exception as e:  # noqa: BLE001
            log("   lecture impossible", e)
            continue
        log(f"   colonnes : {list(df.columns)[:40]}")
        log(f"   {len(df)} lignes ; dernières :\n{df.tail(3).to_string()[:1500]}")
        res[nom] = df
    return res


# ------------------------------------------------------------------------------------------------ B. psychologie
def pct_rank(w, v):
    if not w:
        return None
    lo = sum(1 for x in w if x < v)
    eq = sum(1 for x in w if x == v)
    return (lo + 0.5 * eq) / len(w) * 100


def psy_index(dates, p, cot=None, win=756):
    """Indice 0 (peur) → 100 (euphorie), chaque composante en percentile sur 3 ans glissants."""
    import backtest as bt
    r = bt.rsi(p)
    m200 = bt.sma(p, 200)
    ec = [p[i] / m200[i] - 1 if m200[i] else None for i in range(len(p))]
    mo = [p[i] / p[i - 20] - 1 if i >= 20 else None for i in range(len(p))]
    out = [None] * len(p)
    comps = {"rsi": r, "ecart200": ec, "elan20": mo}
    for i in range(len(p)):
        if i < 260:
            continue
        vals = []
        for k, s in comps.items():
            if s[i] is None:
                continue
            w = [x for x in s[max(0, i - win):i] if x is not None]
            if len(w) >= 200:
                vals.append(pct_rank(w, s[i]))
        if cot:
            c = cot(dates[i])
            if c is not None:
                vals.append(c)
        if len(vals) >= 3:
            out[i] = sum(vals) / len(vals)
    return out


def cot_fn(cftc, cult):
    from datetime import datetime, timedelta
    series = [v["serie"] for v in cftc.values() if isinstance(v, dict) and v.get("culture") == cult and v.get("serie")]
    cot = []
    for ser in series:
        dd = [x["date"] for x in ser]
        nets = [x["long"] - x["short"] for x in ser]
        cot.append((dd, nets))

    def f(d):
        lim = (datetime.fromisoformat(d) - timedelta(days=3)).date().isoformat()
        sc = []
        for dd, nets in cot:
            j = bisect.bisect_right(dd, lim) - 1
            if j < 52:
                continue
            w = nets[max(0, j - 156):j]
            sc.append(pct_rank(w, nets[j]))
        return sum(sc) / len(sc) if sc else None
    return f if cot else None


def spearman(a, b):
    n = len(a)
    if n < 30:
        return None

    def rk(x):
        o = sorted(range(n), key=lambda i: x[i])
        r = [0] * n
        for k, i in enumerate(o):
            r[i] = k
        return r
    ra, rb = rk(a), rk(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / va / vb if va and vb else None


def evalue(nom, dates, p, idx, horizons=(20, 60)):
    log(f"\n-- {nom} : {dates[0]} → {dates[-1]}, {len(p)} séances")
    B = ((0, 20, "peur extrême"), (20, 40, "peur"), (40, 60, "neutre"), (60, 80, "optimisme"), (80, 101, "euphorie"))
    for h in horizons:
        pts = [(idx[i], p[i + h] / p[i] - 1) for i in range(len(p) - h) if idx[i] is not None]
        if len(pts) < 100:
            log(f"   {h} séances : trop peu de points")
            continue
        allm = sum(x[1] for x in pts) / len(pts) * 100
        rho = spearman([x[0] for x in pts], [x[1] for x in pts])
        txt = []
        for a, b, lab in B:
            sub = [x[1] for x in pts if a <= x[0] < b]
            if len(sub) >= 20:
                up = sum(1 for x in sub if x > 0) / len(sub) * 100
                txt.append(f"{lab} {sum(sub) / len(sub) * 100:+.1f} % ({up:.0f} % de hausses, n={len(sub)})")
        log(f"   {h} séances : moyenne {allm:+.1f} %, corrélation de rang {rho:+.3f}")
        for t in txt:
            log("      " + t)
        # par période (seulement les extrêmes)
        for a0, b0 in (("2000", "2012"), ("2013", "2019"), ("2020", "2099")):
            sel = [(idx[i], p[i + h] / p[i] - 1) for i in range(len(p) - h) if idx[i] is not None and a0 <= dates[i][:4] <= b0]
            if len(sel) < 200:
                continue
            lo = [x[1] for x in sel if x[0] < 20]
            hi = [x[1] for x in sel if x[0] >= 80]
            m = sum(x[1] for x in sel) / len(sel) * 100
            log(f"      {a0}-{b0[:4] if b0 != '2099' else 'auj.'} : tout {m:+.1f} % · peur extrême "
                + (f"{sum(lo) / len(lo) * 100:+.1f} % (n={len(lo)})" if len(lo) >= 15 else "–")
                + " · euphorie " + (f"{sum(hi) / len(hi) * 100:+.1f} % (n={len(hi)})" if len(hi) >= 15 else "–"))


def psychologie():
    log("\n== Psychologie des marchés : indice peur ↔ euphorie et rendements suivants ==")
    import backtest as bt
    import build
    yl = bt.load(os.path.join(PRIV, "yahoo_long.json"), {})
    cftc = bt.load(os.path.join(PRIV, "cftc_long.json"), {})
    log(f"   historiques : yahoo_long {sorted(k for k in yl if not k.startswith('_'))}, cftc_long {len([k for k in cftc if not k.startswith('_')])} marchés")
    res = {}
    for tk, cult in (("ZW=F", "ble"), ("ZC=F", "mais")):
        s = (yl.get(tk) or {}).get("serie") or {}
        d = sorted(s)
        p = [s[x] for x in d]
        if len(p) < 1000:
            log(f"   {tk} : {len(p)} séances seulement")
            continue
        cf = cot_fn(cftc, cult)
        idx = psy_index(d, p, cf)
        evalue(f"{tk} Chicago (avec fonds CFTC dès 2006)", d, p, idx)
        idx2 = psy_index(d, p, None)
        evalue(f"{tk} Chicago, prix seuls (sans les fonds)", d, p, idx2, horizons=(60,))
        res[tk] = (d, p, idx)
    path = os.path.join(PRIV, "euronext.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8"))) if os.path.exists(path) else []
    for prod, cult in (("EBM", "ble"), ("ECO", "colza"), ("EMA", "mais")):
        d, p, *_ = build.continuous(rows, prod)
        if len(p) < 600:
            log(f"   {prod} : {len(p)} séances seulement")
            continue
        cf = cot_fn(cftc, cult)
        idx = psy_index(d, p, cf)
        evalue(f"{prod} Euronext (série ajustée des roulements)", d, p, idx)
        res[prod] = (d, p, idx)
    return res


def geo_vs_prix(gp, tone, psy):
    log("\n== Risque géopolitique / tonalité → rendement suivant du blé ==")
    if "ZW=F" not in psy:
        log("   pas de série blé")
        return
    d, p, _ = psy["ZW=F"]
    if "quotidien" in gp:
        df = gp["quotidien"]
        cols = [c for c in df.columns if str(c).upper() in ("GPRD", "GPRD_MA7", "GPRD_ACT", "GPRD_THREAT")]
        dcol = next((c for c in df.columns if "date" in str(c).lower()), None)
        log(f"   colonnes retenues {cols}, date {dcol}")
        if cols and dcol is not None:
            g = {}
            for _, r in df.iterrows():
                try:
                    k = str(r[dcol])[:10].replace("/", "-")
                    if re.match(r"^\d{8}$", k):
                        k = f"{k[:4]}-{k[4:6]}-{k[6:]}"
                    g[k] = float(r[cols[0]])
                except Exception:  # noqa: BLE001
                    pass
            gd = sorted(g)
            log(f"   GPR quotidien {gd[0] if gd else '-'} → {gd[-1] if gd else '-'} ({len(gd)} jours)")
            for h in (20, 60):
                a, b = [], []
                for i in range(len(p) - h):
                    j = bisect.bisect_right(gd, d[i]) - 1
                    if j < 30 or d[i] < "2000-01-01":
                        continue
                    m30 = sum(g[gd[k]] for k in range(j - 29, j + 1)) / 30
                    a.append(m30)
                    b.append(p[i + h] / p[i] - 1)
                if a:
                    rho = spearman(a, b)
                    q = sorted(a)[int(len(a) * 0.9)]
                    hi = [y for x, y in zip(a, b) if x >= q]
                    log(f"   GPR (moy. 30 j) → blé à {h} séances : corrélation de rang {rho:+.3f} ; 10 % des jours les plus tendus "
                        f"{sum(hi) / len(hi) * 100:+.1f} % contre {sum(b) / len(b) * 100:+.1f} % en moyenne (n={len(hi)})")
    for lab, tl in tone.items():
        td = [f"{x[0][:4]}-{x[0][4:6]}-{x[0][6:8]}" for x in tl]
        tv = [x[1] for x in tl]
        for h in (20, 60):
            a, b = [], []
            for i in range(len(p) - h):
                j = bisect.bisect_right(td, d[i]) - 1
                if j < 0 or d[i] < td[0]:
                    continue
                a.append(tv[j])
                b.append(p[i + h] / p[i] - 1)
            if len(a) > 60:
                log(f"   tonalité GDELT « {lab} » → blé à {h} séances : corrélation de rang {spearman(a, b):+.3f} (n={len(a)})")


def main():
    t0 = time.time()
    tone = {}
    for fn in (gdelt,):
        try:
            tone = fn()
        except Exception as e:  # noqa: BLE001
            log("GDELT : échec", e)
    try:
        flux()
    except Exception as e:  # noqa: BLE001
        log("flux : échec", e)
    gp = {}
    try:
        gp = gpr()
    except Exception as e:  # noqa: BLE001
        log("GPR : échec", e)
    psy = {}
    try:
        psy = psychologie()
    except Exception as e:  # noqa: BLE001
        import traceback
        log("psychologie : échec", e, traceback.format_exc()[-800:])
    try:
        geo_vs_prix(gp, tone, psy)
    except Exception as e:  # noqa: BLE001
        log("géopolitique/prix : échec", e)
    log(f"\nDurée {time.time() - t0:.0f} s")
    open(os.path.join(OUT, "grain_actu_probe.txt"), "w", encoding="utf-8").write("\n".join(lines))


if __name__ == "__main__":
    main()
