"""
Euro Signal — événements des sociétés via Yahoo Finance (exécuté par GitHub Actions, après prices.py).

Pour chaque titre dont le ticker est connu (data/tickers.json) :
  - publications de résultats : BPA publié et consensus (estimation figée à la publication) ;
  - communiqués de l'émetteur (onglet « press releases ») : titre, date, diffuseur, lien ;
  - tendance du BPA annuel estimé (actuel / il y a 30 jours) : révisions des analystes ;
  - prévisionnels : BPA et chiffre d'affaires attendus (exercice en cours et suivant), objectif de cours moyen.
L'interprétation (rachat, perspectives, surprise) est faite par le moteur Euro Signal (core.js), testé.
Écrit data/events.json (régénéré à chaque exécution ; l'historique est conservé par build.mjs).
"""
import json
from concurrent.futures import ThreadPoolExecutor
import math
import os
import sys
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def num(v):
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return None


def press_items(t):
    out = []
    for tab in ("press releases", "news"):
        try:
            items = t.get_news(count=25, tab=tab) or []
        except Exception:
            items = []
        for it in items:
            c = it.get("content", it) or {}
            title = c.get("title")
            when = c.get("pubDate") or c.get("displayTime") or it.get("providerPublishTime")
            if isinstance(when, (int, float)):
                when = datetime.fromtimestamp(when, timezone.utc).isoformat()
            prov = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else it.get("publisher")
            url = ((c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else None) or ((c.get("clickThroughUrl") or {}).get("url") if isinstance(c.get("clickThroughUrl"), dict) else None) or it.get("link")
            if title and when:
                out.append({"title": title, "date": str(when)[:10], "provider": prov, "url": url, "tab": tab})
        if out and tab == "press releases":
            break  # les communiqués de l'émetteur suffisent quand ils existent
    return out


FUND_KEYS = {"totalDebt": "totalDebt", "totalCash": "totalCash", "ebitda": "ebitda", "freeCashflow": "freeCashflow",
             "operatingCashflow": "operatingCashflow", "profitMargins": "profitMargins", "returnOnEquity": "returnOnEquity",
             "currentRatio": "currentRatio", "debtToEquity": "debtToEquity", "marketCap": "marketCap",
             # multiples de valorisation : comparaison aux sociétés du même secteur (décote par rapport aux pairs)
             "forwardPE": "forwardPE", "trailingPE": "trailingPE", "evToEbitda": "enterpriseToEbitda", "priceToBook": "priceToBook",
             # taille : position concurrentielle (leader / challenger) parmi les sociétés suivies
             "revenue": "totalRevenue",
             # actionnariat : part détenue par les dirigeants et leurs proches, flottant (repérer les sociétés contrôlées)
             "insidersPct": "heldPercentInsiders", "floatShares": "floatShares", "sharesOut": "sharesOutstanding"}


def _estimates(df, year_ago):
    """Consensus annuel (exercice en cours « 0y » et suivant « +1y ») : moyenne, fourchette, nombre d'analystes, base N-1, croissance."""
    if df is None or getattr(df, "empty", True):
        return None
    out = {}
    for per in ("0y", "+1y"):
        if per in df.index:
            r = df.loc[per]
            row = {"avg": num(r.get("avg")), "low": num(r.get("low")), "high": num(r.get("high")), "n": num(r.get("numberOfAnalysts")),
                   "yearAgo": num(r.get(year_ago)), "growth": num(r.get("growth"))}
            if any(v is not None for v in row.values()):
                out[per] = row
    return out or None


def forecasts(t, inf):
    """Prévisionnels des analystes (Yahoo) : bénéfice par action et chiffre d'affaires attendus, révisions sur 90 jours, objectif de cours.
    Données du jour seulement (Yahoo ne fournit pas l'historique des prévisions) : Euro Signal les fige à la date de chaque achat."""
    fc = {}
    try:
        fc["eps"] = _estimates(t.earnings_estimate, "yearAgoEps")
    except Exception:
        pass
    try:
        fc["rev"] = _estimates(t.revenue_estimate, "yearAgoRevenue")
    except Exception:
        pass
    try:
        tr = t.eps_trend
        if tr is not None and not tr.empty:
            fc["trend"] = {per: {k: num(tr.loc[per].get(src)) for k, src in (("cur", "current"), ("d7", "7daysAgo"), ("d30", "30daysAgo"), ("d90", "90daysAgo"))}
                           for per in ("0y", "+1y") if per in tr.index}
    except Exception:
        pass
    inf = inf or {}
    tgt = {"mean": num(inf.get("targetMeanPrice")), "median": num(inf.get("targetMedianPrice")), "low": num(inf.get("targetLowPrice")),
           "high": num(inf.get("targetHighPrice")), "n": num(inf.get("numberOfAnalystOpinions")), "current": num(inf.get("currentPrice")),
           "currency": inf.get("currency")}
    if tgt["mean"] and tgt["current"]:
        fc["target"] = tgt
    if num(inf.get("recommendationMean")) is not None:
        fc["reco"] = {"mean": num(inf.get("recommendationMean")), "key": inf.get("recommendationKey")}
    fy = inf.get("nextFiscalYearEnd")
    if isinstance(fy, (int, float)):
        fc["fyEnd"] = datetime.fromtimestamp(fy, timezone.utc).date().isoformat()
    fc = {k: v for k, v in fc.items() if v}
    if fc:
        fc["asOf"] = datetime.now(timezone.utc).date().isoformat()
    return fc or None


def fundamentals(t, inf=None):
    """Dernières données financières publiées (Yahoo). Non historisées : jamais utilisées pour la validation."""
    if inf is None:
        try:
            inf = t.info or {}
        except Exception:
            return None
    out = {k: num(inf.get(src)) for k, src in FUND_KEYS.items()}
    if all(v is None for v in out.values()):
        return None
    # Dirigeants publiés (nom, fonction) : sert à reconnaître le DG et le DAF quand la déclaration ne dit que « membre du directoire »
    officers = [{"name": o.get("name"), "title": o.get("title")} for o in (inf.get("companyOfficers") or []) if isinstance(o, dict) and o.get("name") and o.get("title")][:15]
    out.update({"officers": officers or None})
    out.update({"sector": inf.get("sector"), "industry": inf.get("industry"), "currency": inf.get("financialCurrency"),
                "asOf": datetime.now(timezone.utc).date().isoformat()})
    return out


def main():
    try:
        tickers = json.loads((DATA / "tickers.json").read_text(encoding="utf-8"))
    except Exception:
        print("data/tickers.json absent : aucun événement collecté")
        return 0
    items, errors = {}, 0
    pairs = [(isin, v["ticker"]) for isin, v in tickers.items() if v.get("ticker")]
    try:
        prices = json.loads((DATA / "prices.json").read_text(encoding="utf-8")).get("items", {})
        pairs = [(i, prices[i]["ticker"]) for i in prices] or pairs  # mêmes tickers que les cours
    except Exception:
        pass
    # Prévisionnels : relus au plus une fois par semaine par titre (Euro Signal conserve le dernier relevé 30 jours)
    try:
        prev_fc = {k: (v or {}).get("asOf") for k, v in json.loads((DATA / "euro-signal-state.json").read_text(encoding="utf-8")).get("forecast", {}).items()}
    except Exception:
        prev_fc = {}
    today_d = datetime.now(timezone.utc).date()
    def fc_age(isin):
        try:
            return (today_d - datetime.fromisoformat(str(prev_fc.get(isin))[:10]).date()).days
        except Exception:
            return 999  # jamais relevé
    # les plus anciens d'abord, au plus un cinquième des titres par soir (relevés étalés sur la semaine), les nouveaux toujours
    due = sorted((i for i, _ in pairs if fc_age(i) >= 6), key=lambda i: -fc_age(i))
    fc_todo = set(i for i in due if fc_age(i) == 999) | set(due[:max(150, len(pairs) // 5)])
    fc_due = lambda isin: isin in fc_todo
    # Budget de temps : l'étape du workflow est coupée au-delà de sa limite, et rien ne serait écrit. On s'arrête donc à
    # temps et on écrit ce qui est fait (Euro Signal garde les données des autres titres de la veille). Ordre : d'abord
    # les prévisionnels à relire, puis les autres titres en partant d'un point qui tourne chaque soir, pour que tous
    # soient relus au fil des soirs même quand la collecte n'a pas le temps de tout faire.
    budget = float(os.environ.get("EVENTS_MINUTES", "0") or 0) * 60
    t0 = time.monotonic()
    first = [x for x in pairs if x[0] in fc_todo]
    rest = [x for x in pairs if x[0] not in fc_todo]
    if rest:
        k = (today_d.toordinal() * 97) % len(rest)
        rest = rest[k:] + rest[:k]
    pairs = first + rest
    partial = False
    print(f"Événements Yahoo : {len(pairs)} titres ; prévisionnels à relire ce soir : {len(fc_todo)}" + (f" ; budget {budget / 60:.0f} min" if budget else ""))
    # Communiqués : Yahoo ne les sert plus (0 partout depuis octobre 2026). On n'interroge plus qu'un échantillon de 30 titres,
    # pour repérer leur retour ; le reste du temps gagné accélère la collecte. Trois titres à la fois, avec une pause par appel.
    press_sample = set(i for i, _ in pairs[:30])

    def fetch(isin, ticker):
        errs = 0
        t = yf.Ticker(ticker)
        rec = {"ticker": ticker, "earnings": [], "press": [], "epsTrend": None, "fund": None, "nextEarnings": None, "forecast": None}
        try:
            ed = t.get_earnings_dates(limit=12)
            if ed is not None and not ed.empty:
                for idx, row in ed.iterrows():
                    rec["earnings"].append({"date": idx.strftime("%Y-%m-%d"), "epsEstimate": num(row.get("EPS Estimate")), "epsActual": num(row.get("Reported EPS"))})
                today_s = datetime.now(timezone.utc).date().isoformat()
                fut = sorted(e["date"] for e in rec["earnings"] if e["date"] > today_s)
                rec["nextEarnings"] = fut[0] if fut else None
        except Exception:
            errs += 1
        if isin in press_sample:
            try:
                rec["press"] = press_items(t)
            except Exception:
                errs += 1
        try:
            tr = t.eps_trend
            if tr is not None and not tr.empty and "0y" in tr.index:
                rec["epsTrend"] = {"current": num(tr.loc["0y"].get("current")), "d30": num(tr.loc["0y"].get("30daysAgo"))}
        except Exception:
            pass
        try:
            inf = t.info or {}
        except Exception:
            inf = {}
        rec["fund"] = fundamentals(t, inf) if inf else None
        if fc_due(isin):
            try:
                rec["forecast"] = forecasts(t, inf)
            except Exception:
                rec["forecast"] = None
        # Nombre d'actions sur un an : une baisse nette révèle des rachats, une hausse une émission d'actions.
        # Relu pour un cinquième des titres chaque soir de semaine (tous les titres chaque semaine).
        if zlib.crc32(isin.encode()) % 5 == today_d.weekday() % 5:
            try:
                sh = t.get_shares_full(start=(today_d - timedelta(days=400)).isoformat())
                if sh is not None and len(sh) >= 5:
                    sh = sh[sh > 0]
                    sh.index = [str(x)[:10] for x in sh.index]
                    sh = sh.groupby(level=0).last()
                    old = sh[sh.index <= (today_d - timedelta(days=330)).isoformat()]
                    base = old if len(old) else sh
                    rec["shares"] = {"from": base.index[-1] if len(old) else base.index[0], "n0": int(base.iloc[-1] if len(old) else base.iloc[0]),
                                     "to": sh.index[-1], "n1": int(sh.iloc[-1])}
            except Exception:
                pass
        time.sleep(0.4)
        return isin, rec, errs

    workers = int(os.environ.get("EVENTS_THREADS", "3") or 3)
    done = 0
    with ThreadPoolExecutor(max(1, workers)) as ex:
        for k in range(0, len(pairs), 30):
            if budget and time.monotonic() - t0 > budget:
                partial = True
                print(f"  Budget de temps atteint : {done} titres sur {len(pairs)} relus ce soir, les autres gardent les données de la veille")
                break
            for isin, rec, errs in ex.map(lambda p: fetch(*p), pairs[k:k + 30]):
                items[isin] = rec
                errors += errs
                done += 1
            print(f"  {done}/{len(pairs)} ({time.monotonic() - t0:.0f} s)")
    (DATA / "events.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "items": items, "errors": errors, "partial": partial, "total": len(pairs)}, ensure_ascii=False), encoding="utf-8")
    withE = sum(1 for v in items.values() if v["earnings"])
    withP = sum(1 for v in items.values() if v["press"])
    withF = sum(1 for v in items.values() if v.get("fund"))
    print(f"Nombre d'actions sur un an : {sum(1 for v in items.values() if v.get('shares'))} titres relus ce soir")
    print(f"Prévisionnels d'analystes : {sum(1 for v in items.values() if (v.get('forecast') or {}).get('eps'))} titres ; objectifs de cours : {sum(1 for v in items.values() if (v.get('forecast') or {}).get('target'))}")
    print(f"Données financières : {withF} titres ; prochaines publications connues : {sum(1 for v in items.values() if v.get('nextEarnings'))}")
    print(f"Événements écrits : {len(items)} titres, {withE} avec résultats, {withP} avec communiqués, {errors} erreur(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
