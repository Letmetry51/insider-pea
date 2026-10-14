"""
Euro Signal — Secteurs en tendance, thèmes (IA, électrification, défense…), leader et challenger.

Univers FIXE et complet (indépendant des déclarations de dirigeants) : actions des bourses de l'Union européenne
et de l'EEE (éligibles au PEA) d'au moins MIN_CAP_EUR de capitalisation, trouvées avec le filtre d'actions de Yahoo.
Les paniers américains (Nvidia, géants du cloud…) servent seulement de baromètres : non éligibles au PEA, jamais proposés.

Méthode (fixée à l'avance, aucun paramètre optimisé sur le passé) :
  1. Secteur en tendance : médianes, sur les sociétés du groupe, de la force relative 6 mois (hors dernier mois) et
     3 mois face au STOXX 600, de la part au-dessus de la moyenne 40 semaines et de la part à moins de 5 % du plus haut
     52 semaines ; note = moyenne des rangs. « En tendance » : 20 % meilleurs groupes, force 6 mois positive, au moins
     la moitié des sociétés au-dessus de leur moyenne 40 semaines.  (Moskowitz et Grinblatt, 1999 : momentum sectoriel.)
  2. Anticipation : baromètre américain de chaque thème (clients) en avance sur les fournisseurs européens
     (Cohen et Frazzini, 2008 : liens économiques et rendements prévisibles).
  3. Leader : plus grosse capitalisation du groupe. Challenger : parmi les numéros 2 à 4, le plus fort sur 6 mois.

Usage :
  python scrapers/sectors.py --universe     univers (filtre Yahoo + fiches), data/sectors/universe.json (1 fois par semaine)
  python scrapers/sectors.py --prices       cours hebdomadaires 8 ans en euros, data/sectors/weekly.csv.gz
  python scrapers/sectors.py --backtest     test historique → data/sectors/backtest.json et rapport texte
  python scrapers/sectors.py --dashboard    classement du jour → data/sectors.json (lu par le tableau de bord)
  python scrapers/sectors.py --synthetic …  mêmes calculs sur des données simulées (vérification sans réseau)
"""
import argparse
import gzip
import io
import json
import math
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SEC = DATA / "sectors"
UNIVERSE = SEC / "universe.json"
WEEKLY = SEC / "weekly.csv.gz"
BACKTEST = SEC / "backtest.json"
OUT = DATA / "sectors.json"

MIN_CAP_EUR = 500e6
BENCH = "^STOXX"          # STOXX Europe 600 (euros)
US_BENCH = "^GSPC"        # S&P 500
COST = 0.003              # frais par aller simple (courtage + écart achat-vente), appliqués au taux de rotation
FX_PAIRS = {"SEK": "EURSEK=X", "DKK": "EURDKK=X", "NOK": "EURNOK=X", "PLN": "EURPLN=X", "USD": "EURUSD=X"}
REGIONS = {"fr": ["PAR"], "de": ["GER"], "nl": ["AMS"], "it": ["MIL"], "es": ["MCE"], "be": ["BRU"], "pt": ["LIS"],
           "fi": ["HEL"], "ie": ["ISE"], "at": ["VIE"], "se": ["STO"], "dk": ["CPH"], "no": ["OSL"]}
COUNTRY = {"PAR": "FR", "GER": "DE", "AMS": "NL", "MIL": "IT", "MCE": "ES", "BRU": "BE", "LIS": "PT", "HEL": "FI",
           "ISE": "IE", "VIE": "AT", "STO": "SE", "CPH": "DK", "OSL": "NO"}

# Thèmes : chaîne de valeur européenne (éligible PEA) et baromètre américain (clients ou pionniers du thème)
THEMES = [
    {"key": "ia-puces", "name": "IA : puces et équipements",
     "us": ["NVDA", "AVGO", "AMD", "TSM", "MU"],
     "eu": ["ASML.AS", "ASM.AS", "BESI.AS", "AIXA.DE", "IFX.DE", "STMPA.PA", "SOI.PA", "TPRO.MI", "WAF.DE", "NOD.OL"]},
    {"key": "ia-energie", "name": "IA : électricité et data centers",
     "us": ["VRT", "ETN", "PWR", "MSFT", "AMZN", "GOOGL", "META"],
     "eu": ["SU.PA", "LR.PA", "PRY.MI", "NEX.PA", "ENR.DE", "SIE.DE", "SPIE.PA", "MTRS.ST", "NKT.CO", "ABB.ST"]},
    {"key": "ia-logiciel", "name": "IA : logiciels et services",
     "us": ["MSFT", "GOOGL", "META", "ORCL", "NOW"],
     "eu": ["SAP.DE", "DSY.PA", "CAP.PA", "NEM.DE", "TMV.DE", "SOP.PA", "REY.MI"]},
    {"key": "defense", "name": "Défense",
     "us": ["LMT", "RTX", "NOC", "GD"],
     "eu": ["RHM.DE", "HO.PA", "SAF.PA", "LDO.MI", "AM.PA", "HAG.DE", "R3NK.DE", "KOG.OL", "SAAB-B.ST", "EXA.PA"]},
    {"key": "obesite", "name": "Obésité (GLP-1)",
     "us": ["LLY"],
     "eu": ["NOVO-B.CO", "ZEAL.CO"]},
]
EU_EEA = set(COUNTRY.values()) | {"LU", "GR", "PL", "CZ", "HU", "RO", "IS", "LI"}


def log(*a):
    print(*a, flush=True)


def clean(o):
    """JSON strict : NaN et infinis remplacés par null, types numpy convertis."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else round(float(o), 6)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, date)):
        return str(o)[:10]
    return o


# --------------------------------------------------------------------------- univers
def screen_universe():
    import yfinance as yf
    from yfinance import EquityQuery as Q
    seen = {}
    for region, exchs in REGIONS.items():
        ex = Q("or", [Q("eq", ["exchange", e]) for e in exchs]) if len(exchs) > 1 else Q("eq", ["exchange", exchs[0]])
        q = Q("and", [Q("eq", ["region", region]), ex, Q("gt", ["intradaymarketcap", 2e8])])
        off, total = 0, None
        while total is None or off < total:
            try:
                r = yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False)
            except Exception as e:
                log(f"  filtre {region} : erreur {str(e)[:100]}")
                break
            quotes = r.get("quotes") or []
            total = r.get("total") or len(quotes)
            for x in quotes:
                s = x.get("symbol")
                if s and x.get("quoteType", "EQUITY") == "EQUITY" and s not in seen:
                    seen[s] = {"symbol": s, "name": x.get("longName") or x.get("shortName"), "exchange": x.get("exchange"),
                               "country": COUNTRY.get(x.get("exchange"), region.upper()), "currency": x.get("currency")}
            off += 250
            if not quotes:
                break
            time.sleep(0.5)
        log(f"  {region} : {sum(1 for v in seen.values() if v['country'] == COUNTRY.get(exchs[0]))} titres")
    return seen


def enrich(items, fx_now):
    """Fiche Yahoo de chaque titre : secteur, industrie, capitalisation, croissance, marges, ISIN si disponible."""
    import yfinance as yf
    out = {}
    for n, (s, it) in enumerate(sorted(items.items()), 1):
        try:
            inf = yf.Ticker(s).info or {}
        except Exception:
            inf = {}
        cur = inf.get("currency") or it.get("currency") or "EUR"
        unit = 100.0 if cur in ("GBp", "GBX") else 1.0
        rate = 1.0 if cur.upper() == "EUR" else fx_now.get(cur.upper())
        cap = inf.get("marketCap")
        cap_eur = cap / unit / rate if cap and rate else None
        if cap_eur is not None and cap_eur < MIN_CAP_EUR:
            continue
        def f(k):
            v = inf.get(k)
            return None if v is None or (isinstance(v, float) and math.isnan(v)) else v
        out[s] = dict(it, name=f("longName") or it.get("name"), sector=f("sector"), industry=f("industry"), capEur=cap_eur,
                      currency=cur, revGrowth=f("revenueGrowth"), opMargin=f("operatingMargins"), grossMargin=f("grossMargins"),
                      revenue=f("totalRevenue"), fwdPE=f("forwardPE"), isin=f("isin"))
        if n % 50 == 0:
            log(f"  fiches : {n}/{len(items)}")
        time.sleep(0.25)
    return out


def build_universe():
    import yfinance as yf
    fx_now = {}
    for cur, pair in FX_PAIRS.items():
        try:
            h = yf.Ticker(pair).history(period="5d")
            fx_now[cur] = float(h["Close"].dropna().iloc[-1])
        except Exception:
            pass
    raw = screen_universe()
    # thèmes : leurs valeurs européennes font toujours partie de l'univers (même si le filtre les a manquées)
    for th in THEMES:
        for s in th["eu"]:
            raw.setdefault(s, {"symbol": s, "name": None, "exchange": None, "country": None, "currency": None})
    uni = enrich(raw, fx_now)
    for s, it in uni.items():
        if not it.get("country"):
            suf = s.rsplit(".", 1)[-1] if "." in s else ""
            it["country"] = {"PA": "FR", "DE": "DE", "AS": "NL", "MI": "IT", "MC": "ES", "BR": "BE", "LS": "PT", "HE": "FI",
                             "IR": "IE", "VI": "AT", "ST": "SE", "CO": "DK", "OL": "NO"}.get(suf)
        it["pea"] = it.get("country") in EU_EEA
    SEC.mkdir(parents=True, exist_ok=True)
    UNIVERSE.write_text(json.dumps({"generatedAt": datetime.now(timezone.utc).isoformat(), "minCapEur": MIN_CAP_EUR,
                                    "fx": fx_now, "items": uni}, ensure_ascii=False, indent=0), encoding="utf-8")
    log(f"Univers : {len(uni)} sociétés d'au moins {MIN_CAP_EUR / 1e6:.0f} M€ ({sum(1 for v in uni.values() if v['pea'])} éligibles PEA)")


# --------------------------------------------------------------------------- cours
def download_weekly(tickers, years=8):
    import yfinance as yf
    frames = []
    tick = sorted(set(tickers))
    for i in range(0, len(tick), 80):
        batch = tick[i:i + 80]
        for attempt in range(3):
            try:
                df = yf.download(batch, period=f"{years}y", interval="1wk", auto_adjust=True, progress=False, threads=True, group_by="column")
                break
            except Exception as e:
                log(f"  lot {i}: erreur {str(e)[:80]}, nouvel essai")
                time.sleep(5)
                df = None
        if df is None or df.empty:
            continue
        c = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": batch[0]})
        frames.append(c)
        time.sleep(1)
    W = pd.concat(frames, axis=1) if frames else pd.DataFrame()
    W = W.loc[:, ~W.columns.duplicated()]
    W.index = pd.to_datetime(W.index).tz_localize(None).normalize()
    return W.sort_index()


def to_eur(W, uni):
    """Cours en euros (dividendes réinvestis via auto_adjust) ; devises hors euro converties à la semaine."""
    out = W.copy()
    for cur, pair in FX_PAIRS.items():
        if pair not in W.columns:
            continue
        fx = W[pair].ffill()
        for s, it in uni.items():
            if s in out.columns and str(it.get("currency") or "").upper() == cur:
                out[s] = W[s] / fx
    return out


def fetch_prices():
    uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))["items"]
    us = sorted({s for th in THEMES for s in th["us"]})
    W = download_weekly(list(uni) + us + [BENCH, US_BENCH] + list(FX_PAIRS.values()))
    W = to_eur(W, uni)
    miss = [s for s in list(uni) + us + [BENCH] if s not in W.columns or W[s].notna().sum() < 30]
    W.to_csv(WEEKLY, compression="gzip", float_format="%.5g")
    log(f"Cours hebdomadaires : {W.shape[1]} séries, {W.shape[0]} semaines ({W.index[0].date()} → {W.index[-1].date()}) ; manquants : {len(miss)} {miss[:15]}")


def load_weekly():
    W = pd.read_csv(WEEKLY, index_col=0, parse_dates=True, compression="gzip")
    return W.sort_index()


# --------------------------------------------------------------------------- moteur (identique pour le test et le tableau de bord)
def groups_of(uni, min_members=4):
    """Groupe = industrie Yahoo si au moins min_members sociétés de l'univers, sinon « autres » du secteur."""
    ind = {}
    for s, it in uni.items():
        if it.get("industry"):
            ind.setdefault(it["industry"], []).append(s)
    g = {}
    for s, it in uni.items():
        if not it.get("sector"):
            continue
        i = it.get("industry")
        g[s] = i if i and len(ind.get(i, [])) >= min_members else "Autres : " + it["sector"]
    return g


def stock_metrics(W, bench, t):
    """Mesures par titre à la semaine d'indice t (aucune donnée postérieure)."""
    if t < 52:
        return None
    w, b = W.iloc[: t + 1], bench.iloc[: t + 1]
    ret = lambda a, k, lag=0: a.iloc[-1 - lag] / a.iloc[-1 - k] - 1
    rs6 = ret(w, 26, 4) - ret(b, 26, 4)
    rs3 = ret(w, 13) - ret(b, 13)
    ma40 = w.iloc[-40:].mean()
    hi52 = w.iloc[-52:].max()
    last = w.iloc[-1]
    ok = w.iloc[-52:].notna().sum() >= 45
    return pd.DataFrame({"rs6": rs6, "rs3": rs3, "above": (last > ma40).astype(float), "nearHigh": (last >= 0.95 * hi52).astype(float),
                         "last": last}).where(ok, np.nan)


def group_table(W, bench, groups, t, top_frac=0.2):
    m = stock_metrics(W, bench, t)
    if m is None:
        return None, None
    m = m.loc[[s for s in groups if s in m.index]].dropna(subset=["rs6", "rs3"])
    m["group"] = [groups[s] for s in m.index]
    g = m.groupby("group").agg(n=("rs6", "size"), rs6=("rs6", "median"), rs3=("rs3", "median"), breadth=("above", "mean"), highs=("nearHigh", "mean"))
    g = g[g.n >= 3]
    if g.empty:
        return g, m
    g["score"] = sum(g[c].rank(pct=True) for c in ("rs6", "rs3", "breadth", "highs")) / 4
    g["rank"] = g.score.rank(ascending=False, method="first").astype(int)
    k = max(1, int(round(len(g) * top_frac)))
    g["trending"] = (g["rank"] <= k) & (g.rs6 > 0) & (g.breadth >= 0.5)
    return g.sort_values("rank"), m


def leader_challenger(m, group, cap_now, W, t):
    """Leader : plus grosse capitalisation (estimée à la date t d'après le cours) ; challenger : n° 2 à 4, le plus fort sur 6 mois."""
    mem = m[m.group == group]
    if mem.empty:
        return None, None
    last_now = W.iloc[-1]
    size = {s: (cap_now.get(s) or 0) * (W.iloc[t][s] / last_now[s]) if last_now.get(s) and not np.isnan(last_now[s]) else 0 for s in mem.index}
    order = sorted(size, key=lambda s: -size[s])
    leader = order[0] if size[order[0]] > 0 else None
    pool = [s for s in order[1:4] if size[s] > 0]
    challenger = max(pool, key=lambda s: mem.loc[s, "rs6"]) if pool else None
    return leader, challenger


# --------------------------------------------------------------------------- test historique
def perf(r, periods_per_year=13):
    r = pd.Series(r).dropna()
    if len(r) < 6:
        return {}
    nav = (1 + r).cumprod()
    yrs = len(r) / periods_per_year
    return {"cagr": nav.iloc[-1] ** (1 / yrs) - 1, "vol": r.std() * math.sqrt(periods_per_year),
            "sharpe": r.mean() / r.std() * math.sqrt(periods_per_year) if r.std() > 0 else None,
            "maxdd": float((nav / nav.cummax() - 1).min()), "n": len(r)}


def excess_stats(r, b):
    x = (pd.Series(r) - pd.Series(b)).dropna()
    if len(x) < 6:
        return {}
    se = x.std() / math.sqrt(len(x))
    return {"meanPerPeriod": x.mean(), "t": x.mean() / se if se > 0 else None, "beatPct": float((x > 0).mean()), "n": len(x)}


def backtest(W, uni, step=4, top=3):
    bench = W[BENCH].ffill()
    groups = groups_of(uni)
    cap_now = {s: it.get("capEur") for s, it in uni.items()}
    stocks = [s for s in groups if s in W.columns]
    Ws = W[stocks].ffill(limit=2)
    fwd = lambda cols, t: (Ws.iloc[min(t + step, len(Ws) - 1)][cols] / Ws.iloc[t][cols] - 1).fillna(0) if cols else pd.Series(dtype=float)
    rows, prev = [], {"top": set(), "lead": set(), "chal": set()}
    hist = []
    for t in range(56, len(Ws) - step, step):
        g, m = group_table(Ws, bench, groups, t)
        if g is None or g.empty:
            continue
        topg = list(g.index[:top])
        hist.append({"date": str(Ws.index[t].date()), "top": topg, "trending": list(g.index[g.trending])})
        members = [s for s in m.index if m.loc[s, "group"] in topg]
        lc = [leader_challenger(m, gg, cap_now, Ws, t) for gg in topg]
        leads = [a for a, _ in lc if a]
        chals = [b for _, b in lc if b]
        allm = list(m.index)
        def ret(cols, key):
            r = fwd(cols, t).mean() if cols else 0.0
            new = set(cols)
            turn = 1 - len(new & prev[key]) / max(1, len(new)) if key else 0
            if key:
                prev[key] = new
            return r - 2 * COST * turn
        b_ret = bench.iloc[t + step] / bench.iloc[t] - 1
        rows.append({"date": Ws.index[t], "top": ret(members, "top"), "leaders": ret(leads, "lead"), "challengers": ret(chals, "chal"),
                     "universeEW": fwd(allm, t).mean(), "stoxx": b_ret})
    R = pd.DataFrame(rows).set_index("date")
    res = {"periods": len(R), "from": str(R.index[0].date()), "to": str(R.index[-1].date()), "stepWeeks": step, "topGroups": top, "cost": COST}
    res["perf"] = {k: perf(R[k]) for k in R.columns}
    res["vsStoxx"] = {k: excess_stats(R[k], R["stoxx"]) for k in ("top", "leaders", "challengers", "universeEW")}
    res["vsUniverse"] = {k: excess_stats(R[k], R["universeEW"]) for k in ("top", "leaders", "challengers")}
    res["challengerVsLeader"] = excess_stats(R["challengers"], R["leaders"])
    mid = R.index[len(R) // 2]
    res["halves"] = {k: [excess_stats(R.loc[:mid, k], R.loc[:mid, "universeEW"]), excess_stats(R.loc[mid:, k], R.loc[mid:, "universeEW"])] for k in ("top", "leaders", "challengers")}
    res["halvesSplit"] = str(mid.date())
    res["history"] = hist[-30:]
    return res, R


def basket(W, cols):
    cols = [c for c in cols if c in W.columns]
    if not cols:
        return None, []
    r = W[cols].ffill(limit=2).pct_change(fill_method=None)
    return (1 + r.mean(axis=1, skipna=True).fillna(0)).cumprod(), cols


def lead_lag(W, step=4):
    """Le baromètre américain d'un thème annonce-t-il la chaîne européenne ? Corrélations décalées et règle simple."""
    out = []
    spx, stx = W[US_BENCH].ffill(), W[BENCH].ffill()
    for th in THEMES:
        us, usc = basket(W, th["us"])
        eu, euc = basket(W, th["eu"])
        if us is None or eu is None:
            continue
        idx = list(range(0, len(W) - step, step))
        usx = pd.Series([us.iloc[i + step] / us.iloc[i] - spx.iloc[i + step] / spx.iloc[i] for i in idx], index=W.index[idx])
        eux = pd.Series([eu.iloc[i + step] / eu.iloc[i] - stx.iloc[i + step] / stx.iloc[i] for i in idx], index=W.index[idx])
        corr = {f"t+{k}": float(usx.corr(eux.shift(-k))) for k in range(0, 4)}
        # règle : tenir la chaîne européenne quand le baromètre américain bat son marché sur 13 semaines, sinon le STOXX 600
        rule, always = [], []
        for i in idx:
            if i < 13:
                continue
            sig = us.iloc[i] / us.iloc[i - 13] - spx.iloc[i] / spx.iloc[i - 13] > 0
            e = eu.iloc[i + step] / eu.iloc[i] - 1
            s = stx.iloc[i + step] / stx.iloc[i] - 1
            rule.append(e if sig else s)
            always.append(e)
        stxr = [stx.iloc[i + step] / stx.iloc[i] - 1 for i in idx if i >= 13]
        out.append({"theme": th["key"], "name": th["name"], "us": usc, "eu": euc, "corr": corr,
                    "rule": perf(rule), "alwaysEU": perf(always), "stoxx": perf(stxr), "ruleVsAlways": excess_stats(rule, always)})
    return out


def ai_case(W, uni):
    """Cas de l'IA : dates de détection après le lancement de ChatGPT (30/11/2022) et rendements ensuite."""
    bench = W[BENCH].ffill()
    groups = groups_of(uni)
    cap_now = {s: it.get("capEur") for s, it in uni.items()}
    Ws = W[[s for s in groups if s in W.columns]].ffill(limit=2)
    start = Ws.index.searchsorted(pd.Timestamp("2022-11-30"))
    spx = W[US_BENCH].ffill()
    us, _ = basket(W, THEMES[0]["us"])
    us_date = None
    for t in range(start, len(W)):
        if t >= 13 and all(us.iloc[k] / us.iloc[k - 13] - spx.iloc[k] / spx.iloc[k - 13] > 0 for k in range(t - 3, t + 1)):
            us_date = W.index[t]
            break
    targets = {}
    for key in ("ASML.AS", "SU.PA", "IFX.DE", "PRY.MI"):
        if key in groups:
            targets.setdefault(groups[key], key)
    out = {"chatgpt": "2022-11-30", "usBarometerConfirmed": str(us_date.date()) if us_date is not None else None, "groups": []}
    for grp, ex in targets.items():
        first = None
        for t in range(start, len(Ws)):
            g, m = group_table(Ws, bench, groups, t)
            if g is not None and grp in g.index and bool(g.loc[grp, "trending"]):
                first = t
                break
        rec = {"group": grp, "example": ex, "firstTrending": str(Ws.index[first].date()) if first is not None else None}
        if first is not None:
            g, m = group_table(Ws, bench, groups, first)
            lead, chal = leader_challenger(m, grp, cap_now, Ws, first)
            end = min(first + 52, len(Ws) - 1)
            r = lambda s, a, b: float(Ws.iloc[b][s] / Ws.iloc[a][s] - 1) if s else None
            rec.update({"leader": lead, "challenger": chal, "weeksAfterChatGPT": first - start,
                        "leader12m": r(lead, first, end), "challenger12m": r(chal, first, end), "stoxx12m": float(bench.iloc[end] / bench.iloc[first] - 1),
                        "leaderToNow": r(lead, first, len(Ws) - 1), "challengerToNow": r(chal, first, len(Ws) - 1),
                        "stoxxToNow": float(bench.iloc[-1] / bench.iloc[first] - 1),
                        "leaderFromChatGPT": r(lead, start, len(Ws) - 1)})
        out["groups"].append(rec)
    return out


def run_backtest():
    uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))["items"]
    W = load_weekly()
    res, R = backtest(W, uni)
    res["leadLag"] = lead_lag(W)
    res["aiCase"] = ai_case(W, uni)
    res["generatedAt"] = datetime.now(timezone.utc).isoformat()
    res["universe"] = {"n": len(uni), "minCapEur": MIN_CAP_EUR,
                       "bias": "univers d'aujourd'hui appliqué au passé : les sociétés disparues ou devenues petites manquent (biais du survivant) ; "
                               "comparer à l'univers à poids égaux, qui a le même biais, plutôt qu'au STOXX 600"}
    BACKTEST.write_text(json.dumps(clean(res), indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(report(res))


def report(res):
    p = lambda v: "   n/d" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:+6.1f} %"
    L = ["=" * 76, "SECTEURS EN TENDANCE — TEST HISTORIQUE", "=" * 76,
         f"{res['periods']} périodes de {res['stepWeeks']} semaines, {res['from']} → {res['to']}, {res['topGroups']} meilleurs groupes, frais {res['cost'] * 100:.1f} % par aller simple",
         f"Univers : {res['universe']['n']} sociétés ; " + res["universe"]["bias"], "", "Performance annualisée :"]
    for k, v in res["perf"].items():
        if v:
            L.append(f"  {k:12s} CAGR {p(v['cagr'])}  vol {p(v['vol'])}  Sharpe {v['sharpe']:.2f}  pire baisse {p(v['maxdd'])}")
    L.append("\nÉcart par période de 4 semaines face à l'univers à poids égaux (même biais) :")
    for k, v in res["vsUniverse"].items():
        if v:
            L.append(f"  {k:12s} {p(v['meanPerPeriod'])} par période, t = {v['t']:.2f}, bat l'univers {v['beatPct'] * 100:.0f} % du temps")
    v = res["challengerVsLeader"]
    if v:
        L.append(f"  challenger − leader : {p(v['meanPerPeriod'])} par période, t = {v['t']:.2f}")
    L.append(f"\nStabilité (avant / après le {res['halvesSplit']}) :")
    for k, hv in res["halves"].items():
        L.append(f"  {k:12s} " + " | ".join(f"{p(h.get('meanPerPeriod'))} (t = {h['t']:.2f})" if h and h.get('t') is not None else "n/d" for h in hv))
    L.append("\nBaromètre américain → chaîne européenne :")
    for x in res["leadLag"]:
        c = x["corr"]
        L.append(f"  {x['name']:34s} corrélation t+0 {c['t+0']:+.2f} · t+1 {c['t+1']:+.2f} · t+2 {c['t+2']:+.2f} · t+3 {c['t+3']:+.2f}")
        if x["rule"] and x["alwaysEU"]:
            L.append(f"  {'':34s} règle (tenir si le baromètre US monte) CAGR {p(x['rule']['cagr'])}, pire baisse {p(x['rule']['maxdd'])} | toujours investi {p(x['alwaysEU']['cagr'])}, {p(x['alwaysEU']['maxdd'])} | STOXX {p(x['stoxx'].get('cagr'))}")
    a = res["aiCase"]
    L.append(f"\nCas de l'IA (ChatGPT le {a['chatgpt']}) : baromètre américain confirmé le {a['usBarometerConfirmed']}")
    for g in a["groups"]:
        if g.get("firstTrending"):
            L.append(f"  {g['group']:38s} en tendance le {g['firstTrending']} ({g['weeksAfterChatGPT']} sem. après) · leader {g['leader']} {p(g['leader12m'])} sur 12 mois, challenger {g['challenger']} {p(g['challenger12m'])}, STOXX {p(g['stoxx12m'])}")
            L.append(f"  {'':38s} depuis la détection jusqu'à aujourd'hui : leader {p(g['leaderToNow'])}, challenger {p(g['challengerToNow'])}, STOXX {p(g['stoxxToNow'])} (leader acheté le jour de ChatGPT : {p(g['leaderFromChatGPT'])})")
        else:
            L.append(f"  {g['group']:38s} jamais en tendance depuis")
    return "\n".join(L)


# --------------------------------------------------------------------------- tableau de bord (classement du jour)
def daily_rows(tickers):
    import yfinance as yf
    out = {}
    for s in tickers:
        try:
            h = yf.Ticker(s).history(period="1y", interval="1d", auto_adjust=False)
            out[s] = [[i.strftime("%Y-%m-%d"), *(round(float(v), 4) if v == v else None for v in (r["Open"], r["High"], r["Low"], r["Close"])), int(r["Volume"]) if r["Volume"] == r["Volume"] else None]
                      for i, r in h.iterrows() if r["Close"] == r["Close"] and r["Close"] > 0]
        except Exception:
            pass
        time.sleep(0.2)
    return out


def dashboard(fetch_daily=True):
    uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))["items"]
    W = load_weekly()
    bench = W[BENCH].ffill()
    groups = groups_of(uni)
    Ws = W[[s for s in groups if s in W.columns]].ffill(limit=2)
    cap_now = {s: it.get("capEur") for s, it in uni.items()}
    t = len(Ws) - 1
    g, m = group_table(Ws, bench, groups, t)
    g8, _ = group_table(Ws, bench, groups, t - 8)
    def stock(s):
        if not s:
            return None
        it = uni.get(s, {})
        return {"symbol": s, "name": it.get("name"), "country": it.get("country"), "pea": it.get("pea"), "isin": it.get("isin"),
                "capEur": it.get("capEur"), "revGrowth": it.get("revGrowth"), "opMargin": it.get("opMargin"), "fwdPE": it.get("fwdPE"),
                "rs6": float(m.loc[s, "rs6"]) if s in m.index else None, "rs3": float(m.loc[s, "rs3"]) if s in m.index else None}
    out_groups = []
    for grp, r in g.iterrows():
        lead, chal = leader_challenger(m, grp, cap_now, Ws, t)
        mem = m[m.group == grp].sort_values("rs6", ascending=False)
        prev = int(g8.loc[grp, "rank"]) if g8 is not None and grp in g8.index else None
        sector = next((uni[s].get("sector") for s in mem.index if uni.get(s)), None)
        out_groups.append({"key": grp, "sector": sector, "n": int(r.n), "rs6": float(r.rs6), "rs3": float(r.rs3), "breadth": float(r.breadth),
                           "highs": float(r.highs), "score": float(r.score), "rank": int(r["rank"]), "rank8w": prev, "trending": bool(r.trending),
                           "emerging": bool(prev is not None and prev - int(r["rank"]) >= max(5, len(g) // 6) and r.rs3 > 0),
                           "leader": stock(lead), "challenger": stock(chal), "top": [stock(s) for s in mem.index[:5]]})
    spx = W[US_BENCH].ffill()
    themes = []
    for th in THEMES:
        us, usc = basket(W, th["us"])
        eu, euc = basket(W, th["eu"])
        if us is None or eu is None:
            continue
        rsx = lambda a, b, k: float(a.iloc[-1] / a.iloc[-1 - k] - b.iloc[-1] / b.iloc[-1 - k])
        mem = [s for s in euc if s in m.index]
        size = sorted(mem, key=lambda s: -(cap_now.get(s) or 0))
        lead = size[0] if size else None
        chal = max(size[1:4], key=lambda s: m.loc[s, "rs6"]) if len(size) > 1 else None
        themes.append({"key": th["key"], "name": th["name"], "us": usc, "eu": euc,
                       "usRs13": rsx(us, spx, 13), "usRs26": rsx(us, spx, 26), "euRs13": rsx(eu, bench, 13), "euRs26": rsx(eu, bench, 26),
                       "leader": stock(lead), "challenger": stock(chal), "members": [stock(s) for s in sorted(mem, key=lambda s: -m.loc[s, "rs6"])]})
    picks = set()
    for x in out_groups[:8] + themes:
        for k in ("leader", "challenger"):
            if x.get(k):
                picks.add(x[k]["symbol"])
    bt = json.loads(BACKTEST.read_text(encoding="utf-8")) if BACKTEST.exists() else None
    payload = {"format": "euro-signal-sectors", "generatedAt": datetime.now(timezone.utc).isoformat(), "asOf": str(Ws.index[-1].date()),
               "universe": {"n": len(uni), "minCapEur": MIN_CAP_EUR}, "groups": out_groups, "themes": themes,
               "daily": daily_rows(sorted(picks)) if fetch_daily else {},
               "backtest": {k: bt.get(k) for k in ("from", "to", "periods", "vsUniverse", "challengerVsLeader", "halves", "halvesSplit", "aiCase", "perf", "generatedAt")} if bt else None}
    OUT.write_text(json.dumps(clean(payload), ensure_ascii=False, allow_nan=False), encoding="utf-8")
    log(f"Secteurs : {len(out_groups)} groupes, {sum(x['trending'] for x in out_groups)} en tendance, {len(themes)} thèmes, {len(picks)} leaders / challengers")


# --------------------------------------------------------------------------- données simulées (vérification hors ligne)
def synthetic():
    rng = np.random.default_rng(3)
    dates = pd.date_range("2018-10-05", "2026-10-09", freq="W-FRI")
    T = len(dates)
    inds = [("Semiconductor Equipment & Materials", "Technology"), ("Semiconductors", "Technology"), ("Electrical Equipment & Parts", "Industrials"),
            ("Banks - Regional", "Financial Services"), ("Utilities - Regulated Electric", "Utilities"), ("Aerospace & Defense", "Industrials"),
            ("Drug Manufacturers - General", "Healthcare"), ("Auto Manufacturers", "Consumer Cyclical")]
    mkt = rng.normal(0.0015, 0.022, T)
    uni, cols = {}, {}
    names = {"Semiconductor Equipment & Materials": ["ASML.AS", "ASM.AS", "BESI.AS", "AIXA.DE", "SOI.PA"], "Electrical Equipment & Parts": ["SU.PA", "LR.PA", "PRY.MI", "NEX.PA", "ENR.DE"],
             "Semiconductors": ["IFX.DE", "STMPA.PA", "TPRO.MI", "WAF.DE", "NOD.OL"], "Aerospace & Defense": ["RHM.DE", "HO.PA", "SAF.PA", "LDO.MI", "HAG.DE"]}
    for k, (ind, sec) in enumerate(inds):
        boom = np.zeros(T)
        if ind in ("Semiconductor Equipment & Materials", "Electrical Equipment & Parts", "Semiconductors"):
            boom[(dates > "2023-02-01") & (dates < "2024-08-01")] = 0.008
        if ind == "Aerospace & Defense":
            boom[(dates > "2022-03-01")] = 0.006
        tick = names.get(ind, [f"X{k}{j}.PA" for j in range(6)])
        for j, s in enumerate(tick):
            r = mkt * rng.uniform(0.7, 1.4) + boom * (1.3 if j == 1 else 1.0) + rng.normal(0, 0.03, T)
            cols[s] = 50 * np.exp(np.cumsum(r))
            uni[s] = {"symbol": s, "name": s, "country": "FR", "sector": sec, "industry": ind, "capEur": float(10 ** rng.uniform(9, 11.5)) * (3 if j == 0 else 1), "pea": True, "currency": "EUR"}
    us_boom = np.zeros(T)
    us_boom[(dates > "2022-12-15") & (dates < "2024-07-01")] = 0.012
    for s in sorted({x for th in THEMES for x in th["us"]}):
        cols[s] = 100 * np.exp(np.cumsum(mkt + us_boom + rng.normal(0, 0.03, T)))
    cols[BENCH] = 400 * np.exp(np.cumsum(mkt))
    cols[US_BENCH] = 3000 * np.exp(np.cumsum(mkt * 1.1))
    SEC.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(cols, index=dates).to_csv(WEEKLY, compression="gzip", float_format="%.5g")
    UNIVERSE.write_text(json.dumps({"generatedAt": "synthétique", "items": uni}), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--universe-if-older", type=int, default=None, help="reconstruit l'univers s'il a plus de N jours")
    ap.add_argument("--prices", action="store_true")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--dashboard", action="store_true")
    ap.add_argument("--no-daily", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    if a.synthetic:
        synthetic()
    def universe_age():
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(UNIVERSE.read_text(encoding="utf-8"))["generatedAt"])).days
        except Exception:
            return 10 ** 6
    if a.universe or (a.universe_if_older is not None and universe_age() >= a.universe_if_older):
        build_universe()
    if a.prices:
        fetch_prices()
    if a.backtest:
        run_backtest()
    if a.dashboard:
        dashboard(fetch_daily=not a.no_daily and not a.synthetic)
    return 0


if __name__ == "__main__":
    sys.exit(main())
