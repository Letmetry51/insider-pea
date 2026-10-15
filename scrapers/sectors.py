"""
Euro Signal — Secteurs en tendance, thèmes (IA, cybersécurité, défense…), leader et challenger.

Univers FIXE et complet (indépendant des déclarations de dirigeants) : actions des bourses de l'Union européenne
et de l'EEE (éligibles au PEA) d'au moins MIN_CAP_EUR de capitalisation, une cotation par société (siège UE / EEE).
Les paniers américains (Nvidia, CrowdStrike…) servent seulement de baromètres : non éligibles au PEA, jamais proposés.

Signaux par groupe (industrie Yahoo, ou « autres » du secteur si moins de 4 sociétés), tous connus à la date t :
  composite  médiane de la force relative 6 mois (hors dernier mois) et 3 mois face au STOXX 600, part au-dessus de la
             moyenne 40 semaines, part à moins de 5 % du plus haut 52 semaines ; moyenne des rangs (Moskowitz et Grinblatt, 1999)
  mom12      force relative 12 mois hors dernier mois (momentum classique, Jegadeesh et Titman, 1993)
  high52     proximité médiane du plus haut 52 semaines (George et Hwang, 2004)
  emerging   remontée du classement composite en 8 semaines
  volume     accumulation : volume des semaines de hausse / volume des semaines de baisse sur 13 semaines
  surprise   part des sociétés dont les derniers résultats (13 semaines) ont battu le consensus (historique Yahoo ≈ 3 ans)
  revisions  part des prévisions de bénéfice relevées moins abaissées sur 30 jours (instantané, historique constitué chaque semaine)
Leader : plus grosse capitalisation du groupe. Challenger : parmi les numéros 2 à 4, le plus fort sur 6 mois.

Usage :
  --universe [--universe-if-older N]  univers (filtre Yahoo, fiches mises en cache 30 jours, en parallèle)
  --estimates                         révisions des analystes et surprises de résultats (une fois par semaine)
  --prices                            cours et volumes hebdomadaires 8 ans en euros
  --backtest                          test historique et stress test → data/sectors/backtest.json
  --trends                            test Google Trends (expérimental, souvent bloqué par Google)
  --dashboard                         classement du jour → data/sectors.json (lu par le tableau de bord)
  --synthetic                         données simulées (vérification sans réseau)
"""
import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SEC = DATA / "sectors"
UNIVERSE = SEC / "universe.json"
INFO_CACHE = SEC / "info_cache.json"
ESTIMATES = SEC / "estimates.json"
REV_HIST = SEC / "revisions_history.json"
WEEKLY = SEC / "weekly.csv.gz"
WEEKLY_VOL = SEC / "weekly_volume.csv.gz"
BACKTEST = SEC / "backtest.json"
OUT = DATA / "sectors.json"
OUT_CO = DATA / "sectors-companies.json"  # ancien fichier unique (remplacé par les fiches réparties ci-dessous)
CATALOG = SEC / "catalog.json"            # toutes les sociétés cotées des places de l'UE / l'EEE (filtre Yahoo, chaque semaine)
CO_DIR = DATA / "societes"                # fiche de chaque société cotée, en 32 fichiers (lus à la demande)
CO_INDEX = DATA / "societes-index.json"   # liste de recherche : symbole, nom, pays, capitalisation, secteur, tendance
CO_SHARDS = 32

MIN_CAP_EUR = 500e6
BENCH = "^STOXX"          # STOXX Europe 600 (euros)
US_BENCH = "^GSPC"        # S&P 500
COST = 0.003              # frais par aller simple (courtage + écart achat-vente), appliqués au taux de rotation
PLACEBO_N = 500           # tirages au hasard du placebo
INFO_MAX_AGE = 30         # jours avant de relire la fiche Yahoo d'une cotation
THREADS = 4
FX_PAIRS = {"SEK": "EURSEK=X", "DKK": "EURDKK=X", "NOK": "EURNOK=X", "PLN": "EURPLN=X", "USD": "EURUSD=X"}
REGIONS = {"fr": ["PAR"], "de": ["GER"], "nl": ["AMS"], "it": ["MIL"], "es": ["MCE"], "be": ["BRU"], "pt": ["LIS"],
           "fi": ["HEL"], "ie": ["ISE"], "at": ["VIE"], "se": ["STO"], "dk": ["CPH"], "no": ["OSL"]}
COUNTRY = {"PAR": "FR", "GER": "DE", "AMS": "NL", "MIL": "IT", "MCE": "ES", "BRU": "BE", "LIS": "PT", "HEL": "FI",
           "ISE": "IE", "VIE": "AT", "STO": "SE", "CPH": "DK", "OSL": "NO"}
SUFFIX = {"PA": "FR", "DE": "DE", "AS": "NL", "MI": "IT", "MC": "ES", "BR": "BE", "LS": "PT", "HE": "FI", "IR": "IE",
          "VI": "AT", "ST": "SE", "CO": "DK", "OL": "NO"}
EU_EEA = set(COUNTRY.values()) | {"LU", "GR", "PL", "CZ", "HU", "RO", "IS", "LI", "CY", "MT", "EE", "LV", "LT", "SI", "SK", "HR", "BG"}
HQ = {"France": "FR", "Germany": "DE", "Netherlands": "NL", "Italy": "IT", "Spain": "ES", "Belgium": "BE", "Portugal": "PT",
      "Finland": "FI", "Ireland": "IE", "Austria": "AT", "Sweden": "SE", "Denmark": "DK", "Norway": "NO", "Luxembourg": "LU",
      "Greece": "GR", "Poland": "PL", "Czech Republic": "CZ", "Czechia": "CZ", "Hungary": "HU", "Romania": "RO", "Iceland": "IS",
      "Liechtenstein": "LI", "Cyprus": "CY", "Malta": "MT", "Estonia": "EE", "Latvia": "LV", "Lithuania": "LT", "Slovenia": "SI",
      "Slovakia": "SK", "Croatia": "HR", "Bulgaria": "BG"}
LEGAL = {"n.v.", "nv", "s.a.", "sa", "se", "ag", "spa", "s.p.a.", "plc", "ab", "asa", "a/s", "oyj", "publ", "(publ)", "kgaa",
         "&", "co.", "inc.", "ltd", "group", "holding", "holdings", "aktiengesellschaft"}

# Thèmes : chaîne de valeur européenne (éligible PEA) et baromètre américain (clients ou pionniers du thème)
THEMES = [
    {"key": "ia-puces", "name": "IA : puces et équipements", "trends": "Nvidia",
     "us": ["NVDA", "AVGO", "AMD", "TSM", "MU"],
     "eu": ["ASML.AS", "ASM.AS", "BESI.AS", "AIXA.DE", "IFX.DE", "STMPA.PA", "SOI.PA", "TPRO.MI", "WAF.DE", "NOD.OL"]},
    {"key": "ia-energie", "name": "IA : électricité et data centers", "trends": "data center",
     "us": ["VRT", "ETN", "PWR", "MSFT", "AMZN", "GOOGL", "META"],
     "eu": ["SU.PA", "LR.PA", "PRY.MI", "NEX.PA", "ENR.DE", "SIE.DE", "SPIE.PA", "MTRS.ST", "NKT.CO"]},
    {"key": "ia-logiciel", "name": "IA : logiciels et services", "trends": "ChatGPT",
     "us": ["MSFT", "GOOGL", "META", "ORCL", "NOW"],
     "eu": ["SAP.DE", "DSY.PA", "CAP.PA", "NEM.DE", "SOP.PA", "REY.MI"]},
    {"key": "cyber", "name": "Cybersécurité", "trends": "cybersecurity",
     "us": ["CRWD", "PANW", "FTNT", "ZS", "NET", "CHKP"],
     "eu": ["HO.PA", "YSN.DE", "YUBICO.ST", "FSECURE.HE", "ALLIX.PA", "CLAV.ST", "HAG.DE"]},
    {"key": "defense", "name": "Défense", "trends": "defense stocks",
     "us": ["LMT", "RTX", "NOC", "GD"],
     "eu": ["RHM.DE", "HO.PA", "SAF.PA", "LDO.MI", "AM.PA", "HAG.DE", "R3NK.DE", "KOG.OL", "SAAB-B.ST", "EXA.PA"]},
    {"key": "obesite", "name": "Obésité (GLP-1)", "trends": "Ozempic",
     "us": ["LLY"],
     "eu": ["NOVO-B.CO", "ZEAL.CO"]},
]
SIGNALS = ["composite", "mom12", "high52", "emerging", "volume", "surprise"]


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
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (pd.Timestamp, date)):
        return str(o)[:10]
    return o


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, obj, indent=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(clean(obj), ensure_ascii=False, allow_nan=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


def with_retry(fn, tries=3, wait=4):
    for k in range(tries):
        try:
            return fn()
        except Exception as e:
            if k == tries - 1:
                raise
            if "Crumb" in str(e) or "401" in str(e):
                reset_yahoo_session()
            time.sleep(wait * (k + 1) if "429" in str(e) or "Too Many" in str(e) else 1)


# --------------------------------------------------------------------------- catalogue de toutes les sociétés cotées
def screen_catalog(min_cap=1e6, info_minutes=15):
    """Toutes les actions des places de l'UE / l'EEE suivies (une place par pays), sans seuil de taille sauf les coquilles vides.
    Les places de Vienne et de Francfort cotent aussi des milliers de sociétés étrangères (américaines, asiatiques) : seules
    les sociétés dont le siège est dans l'UE ou l'EEE (fiche Yahoo, gardée 60 jours) sont retenues, comme pour le PEA."""
    import yfinance as yf
    from yfinance import EquityQuery as Q
    fx = fx_now()
    out, failed = {}, set()
    prev = read_json(CATALOG, {}).get("items", {})

    def screen_page(q, off):
        for attempt in range(3):
            try:
                return yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False)
            except Exception as e:
                if attempt == 2:
                    raise
                if "Crumb" in str(e) or "401" in str(e):
                    reset_yahoo_session()  # jeton Yahoo expiré après de nombreuses requêtes : nouvelle session
                time.sleep(5 * (attempt + 1))
    for region, exchs in REGIONS.items():
        q = Q("and", [Q("eq", ["region", region]), Q("eq", ["exchange", exchs[0]]), Q("gt", ["intradaymarketcap", min_cap])])
        off, total = 0, None
        while total is None or off < total:
            try:
                r = screen_page(q, off)
            except Exception as e:
                log(f"  catalogue {region} : erreur {str(e)[:100]}")
                failed.add(COUNTRY.get(exchs[0], region.upper()))
                break
            quotes = r.get("quotes") or []
            total = r.get("total") or len(quotes)
            for x in quotes:
                sym = x.get("symbol")
                if not sym or x.get("quoteType", "EQUITY") != "EQUITY" or sym in out:
                    continue
                cur = x.get("currency") or "EUR"
                unit = 100.0 if cur in ("GBp", "GBX") else 1.0
                rate = 1.0 if cur.upper() == "EUR" else fx.get(cur.upper())
                cap, px, vol = x.get("marketCap"), x.get("regularMarketPrice"), x.get("averageDailyVolume3Month")
                out[sym] = {"symbol": sym, "name": x.get("longName") or x.get("shortName"), "exchange": x.get("exchange"),
                            "country": COUNTRY.get(x.get("exchange"), region.upper()), "currency": cur,
                            "capEur": cap / unit / rate if cap and rate else None, "turnoverEur": px * vol / unit / rate if px and vol and rate else None,
                            "sector": x.get("sector"), "industry": x.get("industry")}
            off += 250
            if not quotes:
                break
            time.sleep(0.4)
    # place en échec ce soir : on garde ses sociétés de la semaine précédente plutôt que de les faire disparaître
    for sym, it in prev.items():
        if it.get("country") in failed and sym not in out:
            out[sym] = dict(it)
    if not out:
        log("Catalogue : filtre Yahoo indisponible, catalogue précédent conservé")
        return prev
    # siège, secteur et ISIN : fiche Yahoo (cache partagé avec l'univers), lue dans la limite du temps donné, les plus grosses d'abord
    cache = read_json(INFO_CACHE, {})
    limit = (date.today() - timedelta(days=60)).isoformat()
    todo = sorted([sym for sym in out if not cache.get(sym) or cache[sym].get("fetched", "") < limit], key=lambda x: -(out[x].get("capEur") or 0))
    t0, n = time.time(), 0
    with ThreadPoolExecutor(THREADS) as ex:
        for k in range(0, len(todo), 40):
            if time.time() - t0 > info_minutes * 60:
                break
            for sym, inf in ex.map(fetch_info, todo[k:k + 40]):
                n += 1
                if inf:
                    cache[sym] = inf
    write_json(INFO_CACHE, cache)
    kept, foreign, unknown = {}, 0, 0
    for sym, it in out.items():
        inf = cache.get(sym)
        if not inf:
            unknown += 1
            continue
        hq = HQ.get(inf.get("country"))
        if hq not in EU_EEA:
            foreign += 1
            continue
        it.update({"hq": hq, "sector": inf.get("sector"), "industry": inf.get("industry"), "isin": inf.get("isin"),
                   "name": inf.get("longName") or inf.get("shortName") or it.get("name")})
        kept[sym] = it
    write_json(CATALOG, {"generatedAt": datetime.now(timezone.utc).isoformat(), "minCapEur": min_cap, "items": kept,
                         "pending": len(out) - len(kept) - foreign})
    log(f"Catalogue : {len(out)} cotations sur {len(REGIONS)} places → {len(kept)} sociétés avec siège dans l'UE ou l'EEE "
        f"({foreign} étrangères écartées, {unknown} fiches Yahoo pas encore lues ; {n} lues ce soir en {time.time() - t0:.0f} s)")
    return kept


def reset_yahoo_session():
    """Jeton (crumb) Yahoo refusé : on force yfinance à en demander un nouveau."""
    try:
        from yfinance.data import YfData
        d = YfData()
        for k in ("_crumb", "_cookie"):
            if hasattr(d, k):
                setattr(d, k, None)
    except Exception:
        pass


def catalog_age():
    try:
        c = read_json(CATALOG, {})
        if c.get("pending"):  # fiches Yahoo encore à lire : on continue chaque soir jusqu'à ce que le catalogue soit complet
            return 10 ** 6
        return (datetime.now(timezone.utc) - datetime.fromisoformat(c["generatedAt"])).days
    except Exception:
        return 10 ** 6


def shard_of(sym, n=CO_SHARDS):
    """Même répartition que ES.shardOf (tableau de bord)."""
    h = 0
    for ch in str(sym):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % n


# --------------------------------------------------------------------------- univers
def screen_universe():
    import yfinance as yf
    from yfinance import EquityQuery as Q
    seen = {}
    for region, exchs in REGIONS.items():
        q = Q("and", [Q("eq", ["region", region]), Q("eq", ["exchange", exchs[0]]), Q("gt", ["intradaymarketcap", 2e8])])
        off, total = 0, None
        while total is None or off < total:
            try:
                r = with_retry(lambda: yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False))
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
            time.sleep(0.4)
    log(f"  filtre Yahoo : {len(seen)} cotations")
    return seen


def fetch_info(s):
    import yfinance as yf
    try:
        inf = with_retry(lambda: yf.Ticker(s).info or {})
    except Exception:
        return s, None
    keep = ("longName", "shortName", "sector", "industry", "country", "marketCap", "currency", "revenueGrowth", "operatingMargins",
            "grossMargins", "totalRevenue", "forwardPE", "isin", "currentPrice", "regularMarketPrice", "previousClose",
            "averageVolume", "averageDailyVolume10Day", "numberOfAnalystOpinions", "recommendationMean", "targetMeanPrice",
            "heldPercentInstitutions", "heldPercentInsiders", "shortPercentOfFloat")
    out = {k: inf.get(k) for k in keep if inf.get(k) is not None and not (isinstance(inf.get(k), float) and math.isnan(inf.get(k)))}
    out["fetched"] = date.today().isoformat()
    return s, out


def name_key(n):
    return " ".join(x for x in str(n or "").lower().replace(",", " ").split() if x not in LEGAL)[:40]


def make_item(s, base, inf, fx_now):
    cur = inf.get("currency") or base.get("currency") or "EUR"
    unit = 100.0 if cur in ("GBp", "GBX") else 1.0
    rate = 1.0 if cur.upper() == "EUR" else fx_now.get(cur.upper())
    cap = inf.get("marketCap")
    px = inf.get("currentPrice") or inf.get("regularMarketPrice") or inf.get("previousClose")
    vol = inf.get("averageVolume") or inf.get("averageDailyVolume10Day")
    country = base.get("country") or SUFFIX.get(s.rsplit(".", 1)[-1] if "." in s else "")
    hq = HQ.get(inf.get("country"))
    return {"symbol": s, "name": inf.get("longName") or inf.get("shortName") or base.get("name"), "exchange": base.get("exchange"),
            "country": country, "hq": hq, "currency": cur, "sector": inf.get("sector"), "industry": inf.get("industry"),
            "capEur": cap / unit / rate if cap and rate else None, "turnoverEur": px * vol / unit / rate if px and vol and rate else None,
            "revGrowth": inf.get("revenueGrowth"), "opMargin": inf.get("operatingMargins"), "grossMargin": inf.get("grossMargins"),
            "revenue": inf.get("totalRevenue"), "fwdPE": inf.get("forwardPE"), "isin": inf.get("isin"),
            "analysts": inf.get("numberOfAnalystOpinions"), "reco": inf.get("recommendationMean"),
            "upside": (inf["targetMeanPrice"] / px - 1) if inf.get("targetMeanPrice") and px else None,
            "instPct": inf.get("heldPercentInstitutions"), "insiderPct": inf.get("heldPercentInsiders"),
            "pea": (hq in EU_EEA) if hq else (country in EU_EEA)}


def dedupe(items):
    """Une seule cotation par société : siège dans l'UE ou l'EEE, puis la place où il s'échange le plus de capitaux."""
    best = {}
    for s, it in items.items():
        if it.get("hq") not in EU_EEA or not it.get("capEur") or it["capEur"] < MIN_CAP_EUR:
            continue
        k = name_key(it.get("name")) or s
        rank = (it.get("turnoverEur") or 0, 1 if COUNTRY.get(it.get("exchange")) == it.get("hq") else 0)
        if k not in best or rank > best[k][0]:
            best[k] = (rank, s)
    return {s: items[s] for _, s in best.values()}


def fx_now():
    import yfinance as yf
    out = {}
    for cur, pair in FX_PAIRS.items():
        try:
            out[cur] = float(yf.Ticker(pair).history(period="5d")["Close"].dropna().iloc[-1])
        except Exception:
            pass
    return out


def build_universe():
    t0 = time.time()
    fx = fx_now()
    raw = screen_universe()
    for th in THEMES:
        for s in th["eu"]:
            raw.setdefault(s, {"symbol": s})
    cache = read_json(INFO_CACHE, {})
    limit = (date.today() - timedelta(days=INFO_MAX_AGE)).isoformat()
    todo = [s for s in raw if not cache.get(s) or cache[s].get("fetched", "") < limit]
    log(f"  fiches Yahoo : {len(raw) - len(todo)} en cache, {len(todo)} à lire ({THREADS} en parallèle)")
    with ThreadPoolExecutor(THREADS) as ex:
        for n, (s, inf) in enumerate(ex.map(fetch_info, todo), 1):
            if inf:
                cache[s] = inf
            if n % 250 == 0:
                log(f"    {n}/{len(todo)}")
    cat = read_json(CATALOG, {}).get("items", {})
    cache = {s: v for s, v in cache.items() if s in raw or s in cat or v.get("fetched", "") >= limit}  # cotations disparues des deux filtres : oubliées
    write_json(INFO_CACHE, cache)
    items = {s: make_item(s, raw[s], cache[s], fx) for s in raw if cache.get(s)}
    uni = dedupe(items)
    # thèmes : une valeur citée sous une autre cotation que celle retenue (STMPA.PA → STMMI.MI) est rattachée par son nom ;
    # une valeur trop petite pour l'univers (moins de 500 M€) reste suivie dans son thème si son siège est dans l'UE / l'EEE
    by_name = {name_key(it.get("name")): s for s, it in uni.items()}
    alias, extra = {}, {}
    for th in THEMES:
        for s in th["eu"]:
            if s in uni:
                continue
            it = items.get(s)
            k = name_key(it.get("name")) if it else None
            if it and it.get("hq") in EU_EEA and not (k in by_name and it.get("capEur")):
                extra[s] = it  # cotation citée gardée telle quelle (petite valeur, ou capitalisation absente de sa fiche)
            elif k and k in by_name:
                alias[s] = by_name[k]
    write_json(UNIVERSE, {"generatedAt": datetime.now(timezone.utc).isoformat(), "minCapEur": MIN_CAP_EUR, "fx": fx, "items": uni,
                          "themeAlias": alias, "themeExtra": extra})
    log(f"Univers : {len(raw)} cotations → {len(uni)} sociétés éligibles PEA d'au moins {MIN_CAP_EUR / 1e6:.0f} M€ ({time.time() - t0:.0f} s)")


def universe_age():
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(read_json(UNIVERSE, {})["generatedAt"])).days
    except Exception:
        return 10 ** 6


# --------------------------------------------------------------------------- révisions et surprises (une fois par semaine)
def fetch_estimates(s):
    import yfinance as yf
    t = yf.Ticker(s)
    out = {"fetched": date.today().isoformat()}
    try:
        er = with_retry(lambda: t.eps_revisions, tries=2)
        if er is not None and not er.empty and "0y" in er.index:
            r = er.loc["0y"]
            out["rev"] = {k: (None if pd.isna(r.get(c)) else int(r.get(c))) for k, c in
                          (("up7", "upLast7days"), ("up30", "upLast30days"), ("down7", "downLast7Days"), ("down30", "downLast30days"))}
    except Exception:
        pass
    try:
        ed = with_retry(lambda: t.get_earnings_dates(limit=16), tries=2)
        if ed is not None and not ed.empty and "Surprise(%)" in ed.columns:
            out["surprises"] = sorted([[i.strftime("%Y-%m-%d"), float(v)] for i, v in ed["Surprise(%)"].items() if pd.notna(v)])
    except Exception:
        pass
    return s, out


def refresh_estimates():
    uni = read_json(UNIVERSE, {}).get("items", {})
    if not uni:
        log("Révisions : univers absent")
        return
    t0 = time.time()
    old = read_json(ESTIMATES, {})
    est = {}
    with ThreadPoolExecutor(THREADS) as ex:
        for s, e in ex.map(fetch_estimates, sorted(uni)):
            prev = (old.get(s) or {}).get("surprises") or []
            merged = {d: v for d, v in prev}
            merged.update({d: v for d, v in (e.get("surprises") or [])})  # historique des surprises conservé au-delà de 16 trimestres
            e["surprises"] = sorted([[d, v] for d, v in merged.items()])
            est[s] = e
    write_json(ESTIMATES, est)
    # instantané hebdomadaire de la largeur des révisions par groupe : constitue l'historique qui permettra de valider ce signal
    groups = groups_of(uni)
    snap = revision_breadth(est, groups)
    hist = read_json(REV_HIST, {})
    hist[date.today().isoformat()] = snap
    write_json(REV_HIST, dict(sorted(hist.items())[-260:]))
    n_rev = sum(1 for v in est.values() if v.get("rev"))
    n_sur = sum(1 for v in est.values() if v.get("surprises"))
    log(f"Révisions : {n_rev} sociétés avec révisions, {n_sur} avec surprises de résultats ({time.time() - t0:.0f} s)")


def revision_breadth(est, groups):
    """Par groupe : (sociétés aux prévisions relevées − abaissées sur 30 jours) / sociétés suivies par des analystes."""
    agg = {}
    for s, g in groups.items():
        r = (est.get(s) or {}).get("rev")
        if not r or r.get("up30") is None or r.get("down30") is None:
            continue
        up, dn = r["up30"] or 0, r["down30"] or 0
        a = agg.setdefault(g, [0, 0, 0])
        a[0] += 1
        a[1] += up > dn
        a[2] += dn > up
    return {g: {"n": a[0], "breadth": (a[1] - a[2]) / a[0]} for g, a in agg.items() if a[0] >= 3}


# --------------------------------------------------------------------------- cours
def download_weekly(tickers, years=8):
    import yfinance as yf
    closes, vols = [], []
    tick = sorted(set(tickers))
    for i in range(0, len(tick), 80):
        batch = tick[i:i + 80]
        df = None
        for attempt in range(3):
            try:
                df = yf.download(batch, period=f"{years}y", interval="1wk", auto_adjust=True, progress=False, threads=True, group_by="column")
                break
            except Exception as e:
                log(f"  lot {i}: erreur {str(e)[:80]}, nouvel essai")
                time.sleep(5)
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            closes.append(df["Close"])
            if "Volume" in df.columns.get_level_values(0):
                vols.append(df["Volume"])
        else:
            closes.append(df[["Close"]].rename(columns={"Close": batch[0]}))
            if "Volume" in df.columns:
                vols.append(df[["Volume"]].rename(columns={"Volume": batch[0]}))
        time.sleep(1)
    def tidy(frames):
        if not frames:
            return pd.DataFrame()
        X = pd.concat(frames, axis=1)
        X = X.loc[:, ~X.columns.duplicated()]
        X.index = pd.to_datetime(X.index).tz_localize(None).normalize()
        return X.sort_index()
    W, V = tidy(closes), tidy(vols)
    # une ligne par semaine (vendredi), quelle que soit la date de la barre renvoyée par chaque place
    return W.resample("W-FRI").last(), (V.resample("W-FRI").sum(min_count=1) if not V.empty else V)


def to_eur(W, uni):
    out = W.copy()
    for cur, pair in FX_PAIRS.items():
        if pair not in W.columns:
            continue
        fx = W[pair].ffill()
        cols = [s for s, it in uni.items() if s in out.columns and str(it.get("currency") or "").upper() == cur]
        if cols:
            out[cols] = W[cols].div(fx, axis=0)
    return out


def fetch_prices():
    U = read_json(UNIVERSE, {})
    uni = U.get("items", {})
    if not uni:
        raise SystemExit("Univers absent : lancer --universe")
    allu = dict(uni, **(U.get("themeExtra") or {}))
    us = sorted({s for th in THEMES for s in th["us"]})
    t0 = time.time()
    W, V = download_weekly(list(allu) + us + [BENCH, US_BENCH] + list(FX_PAIRS.values()))
    W = to_eur(W, allu)
    miss = [s for s in list(uni) + us + [BENCH] if s not in W.columns or W[s].notna().sum() < 30]
    W.to_csv(WEEKLY, compression="gzip", float_format="%.5g")
    if not V.empty:
        V.to_csv(WEEKLY_VOL, compression="gzip", float_format="%.4g")
    log(f"Cours hebdomadaires : {W.shape[1]} séries, {W.shape[0]} semaines ({W.index[0].date()} → {W.index[-1].date()}), "
        f"{time.time() - t0:.0f} s ; manquants : {len(miss)} {miss[:20]}")


def clean_prices(W):
    """Erreurs de cours Yahoo : prix nuls ou négatifs, pics isolés (×3 puis retour) effacés ; séries trop abîmées écartées."""
    W = W.where(W > 0)
    r = W / W.ffill().shift(1)
    nxt = W.shift(-1) / W
    W = W.mask(((r > 3) & (nxt < 1 / 2.5)) | ((r < 1 / 3) & (nxt > 2.5)))
    r = W / W.ffill().shift(1)
    bad = ((r > 3) | (r < 1 / 3)).sum()
    return W.drop(columns=[c for c in W.columns if bad[c] > 2 and c not in (BENCH, US_BENCH)])


def load_weekly():
    W = pd.read_csv(WEEKLY, index_col=0, parse_dates=True, compression="gzip").sort_index()
    if len(W) > 10 and pd.Series(W.index.dayofweek).nunique() > 1:
        W = W.resample("W-FRI").last()
    W = clean_prices(W)
    V = None
    if WEEKLY_VOL.exists():
        V = pd.read_csv(WEEKLY_VOL, index_col=0, parse_dates=True, compression="gzip").sort_index()
        if len(V) > 10 and pd.Series(V.index.dayofweek).nunique() > 1:
            V = V.resample("W-FRI").sum(min_count=1)
        V = V.reindex(W.index)
    return W, V


# --------------------------------------------------------------------------- moteur vectorisé (identique pour le test et le tableau de bord)
def groups_of(uni, min_members=4):
    """Groupe = industrie Yahoo si au moins min_members sociétés de l'univers, sinon « autres » du secteur."""
    count = {}
    for it in uni.values():
        if it.get("industry"):
            count[it["industry"]] = count.get(it["industry"], 0) + 1
    g = {}
    for s, it in uni.items():
        if it.get("sector"):
            i = it.get("industry")
            g[s] = i if i and count.get(i, 0) >= min_members else "Autres : " + it["sector"]
    return g


def panels(W, bench, V=None, est=None):
    """Mesures par titre et par semaine (aucune donnée postérieure à la semaine) : tableaux semaines × titres."""
    Wf = W.ffill(limit=2)
    b = bench.ffill()
    rel = lambda k, lag=0: Wf.shift(lag) / Wf.shift(k) - 1 - (b.shift(lag) / b.shift(k) - 1).values[:, None]
    valid = Wf.notna().rolling(52, min_periods=1).sum() >= 45
    P = {"rs6": rel(26, 4), "rs3": rel(13), "mom12": rel(52, 4),
         "above": (Wf > Wf.rolling(40, min_periods=36).mean()).astype(float),
         "hi52": Wf / Wf.rolling(52, min_periods=45).max()}
    P["nearHigh"] = (P["hi52"] >= 0.95).astype(float)
    if V is not None:
        up = (Wf.pct_change(fill_method=None) > 0)
        Vv = V.reindex(columns=W.columns)
        upv = Vv.where(up, 0).rolling(13, min_periods=10).sum()
        dnv = Vv.where(~up & Wf.pct_change(fill_method=None).notna(), 0).rolling(13, min_periods=10).sum()
        P["volume"] = np.log((upv + 1) / (dnv + 1)).where(Vv.notna().rolling(13).sum() >= 10)
    if est:
        S = pd.DataFrame(np.nan, index=W.index, columns=W.columns)
        for s, e in est.items():
            if s not in S.columns or not e.get("surprises"):
                continue
            ser = pd.Series({pd.Timestamp(d): (1.0 if v > 0 else -1.0 if v < 0 else 0.0) for d, v in e["surprises"]}).sort_index()
            ser = ser[~ser.index.duplicated(keep="last")]
            # dernière surprise connue à la semaine t, valable 13 semaines (un trimestre)
            idx = ser.index.searchsorted(W.index, side="right") - 1
            vals = np.where(idx >= 0, ser.values[np.clip(idx, 0, None)], np.nan)
            age = np.where(idx >= 0, (W.index - ser.index[np.clip(idx, 0, None)]).days, 1e9)
            S[s] = np.where(age <= 91, vals, np.nan)
        P["surprise"] = S
    return {k: v.where(valid) for k, v in P.items()}


def group_signals(P, groups):
    """Mesures par groupe et par semaine (médianes), note composite et classement ; tableaux semaines × groupes."""
    cols = [s for s in groups if s in P["rs6"].columns]
    gmap = pd.Series({s: groups[s] for s in cols})
    med = lambda X: X[cols].T.groupby(gmap).median().T
    G = {k: med(P[k]) for k in ("rs6", "rs3", "mom12", "hi52")}
    G["breadth"] = P["above"][cols].T.groupby(gmap).mean().T
    G["highs"] = P["nearHigh"][cols].T.groupby(gmap).mean().T
    G["n"] = P["rs6"][cols].notna().T.groupby(gmap).sum().T
    ok = G["n"] >= 3
    for k in list(G):
        if k != "n":
            G[k] = G[k].where(ok)
    G["composite"] = sum(G[c].rank(axis=1, pct=True) for c in ("rs6", "rs3", "breadth", "highs")) / 4
    G["rank"] = G["composite"].rank(axis=1, ascending=False, method="first")
    G["emerging"] = (G["rank"].shift(8) - G["rank"]).where(G["rs3"] > 0)  # places gagnées en 8 semaines, si le groupe monte
    G["high52"] = G["hi52"]
    if "volume" in P:
        G["volume"] = med(P["volume"])
    if "surprise" in P:
        G["surprise"] = P["surprise"][cols].T.groupby(gmap).mean().T.where(P["surprise"][cols].notna().T.groupby(gmap).sum().T >= 3)
    k = (G["composite"].notna().sum(axis=1) * 0.2).round().clip(lower=1)
    G["trending"] = (G["rank"].le(k, axis=0)) & (G["rs6"] > 0) & (G["breadth"] >= 0.5)
    return G


def leader_challenger(P, groups, group, cap_now, W, t):
    """Leader : plus grosse capitalisation (estimée à la semaine t d'après le cours) ; challenger : n° 2 à 4, le plus fort sur 6 mois."""
    mem = [s for s, g in groups.items() if g == group and s in W.columns and pd.notna(P["rs6"].iloc[t].get(s))]
    if not mem:
        return None, None
    last = W.ffill().iloc[-1]
    size = {s: (cap_now.get(s) or 0) * (W.iloc[t][s] / last[s]) if pd.notna(last.get(s)) and last[s] > 0 and pd.notna(W.iloc[t][s]) else 0 for s in mem}
    order = sorted(size, key=lambda s: -size[s])
    leader = order[0] if size[order[0]] > 0 else None
    pool = [s for s in order[1:4] if size[s] > 0]
    challenger = max(pool, key=lambda s: P["rs6"].iloc[t][s]) if pool else None
    return leader, challenger


# --------------------------------------------------------------------------- test historique et stress test
PER_YEAR = 52


def perf(r, step):
    r = pd.Series(r).dropna()
    if len(r) < 6:
        return {}
    ppy = PER_YEAR / step
    nav = (1 + r).cumprod()
    return {"cagr": nav.iloc[-1] ** (ppy / len(r)) - 1, "vol": r.std() * math.sqrt(ppy),
            "sharpe": r.mean() / r.std() * math.sqrt(ppy) if r.std() > 0 else None,
            "maxdd": float((nav / nav.cummax() - 1).min()), "n": len(r)}


def excess_stats(r, b):
    x = (pd.Series(r) - pd.Series(b)).dropna()
    if len(x) < 6:
        return {}
    se = x.std() / math.sqrt(len(x))
    return {"meanPerPeriod": x.mean(), "t": x.mean() / se if se > 0 else None, "beatPct": float((x > 0).mean()), "n": len(x)}


class Fwd:
    """Rendements à venir par groupe, calculés une fois par durée de détention (somme et nombre de sociétés cotées)."""
    def __init__(self, Wf, groups):
        self.Wf, self.cols = Wf, [s for s in groups if s in Wf.columns]
        self.gm = pd.Series({s: groups[s] for s in self.cols})
        self.cache = {}

    def get(self, step):
        if step not in self.cache:
            F = (self.Wf[self.cols].shift(-step) / self.Wf[self.cols] - 1).clip(-0.6, 1.5)  # borné : une erreur de cours restante ne fait pas le résultat
            ok = F.notna()
            self.cache[step] = (F.fillna(0).T.groupby(self.gm).sum().T, ok.T.groupby(self.gm).sum().T, F.mean(axis=1))
        return self.cache[step]


def simulate(Wf, G, groups, signal, top, step, cost=COST, start=56, P=None, cap_now=None, picks=False, fwd=None, rng=None, keep=None):
    """Tous les `step` semaines : les `top` groupes de meilleur signal (ou tirés au hasard si rng), sociétés à poids égaux,
    frais sur la rotation ; keep : un groupe détenu n'est vendu que s'il sort des `keep` premiers (moins de rotation). Renvoie les rendements par période : portefeuille, univers à poids égaux, STOXX 600,
    et leaders / challengers si picks."""
    fwd = fwd or Fwd(Wf, groups)
    Sg, Cg, EW = fwd.get(step)
    S = G[signal] if signal else None
    bench = Wf[BENCH].ffill() if BENCH in Wf.columns else None
    rows, prev, prevp = [], set(), {"lead": set(), "chal": set()}
    for t in range(start, len(Wf) - step, step):
        if rng is not None:
            avail = G["composite"].iloc[t].dropna().index
            if len(avail) < top:
                continue
            topg = list(rng.choice(avail, top, replace=False))
        else:
            sig = S.iloc[t].dropna()
            if sig.empty:
                continue
            ranking = list(sig.sort_values(ascending=False).index)
            if keep:
                held = [g for g in ranking[:keep] if g in prev]
                topg = (held + [g for g in ranking if g not in held])[:max(top, len(held))][:top] if len(held) <= top else held[:top]
            else:
                topg = ranking[:top]
        cnt = Cg.iloc[t].reindex(topg).fillna(0)
        n = cnt.sum()
        if n <= 0:
            continue
        r = Sg.iloc[t].reindex(topg).fillna(0).sum() / n
        turn = 1 - cnt[[g for g in topg if g in prev]].sum() / n
        prev = set(topg)
        row = {"date": Wf.index[t], "top": float(r - 2 * cost * turn), "universeEW": float(EW.iloc[t]),
               "stoxx": float(bench.iloc[t + step] / bench.iloc[t] - 1) if bench is not None else np.nan}
        if picks:
            f = (Wf.iloc[t + step] / Wf.iloc[t] - 1).clip(-0.6, 1.5)
            lc = [leader_challenger(P, groups, g, cap_now, Wf, t) for g in topg]
            for key, names in (("lead", [a for a, _ in lc if a]), ("chal", [b for _, b in lc if b])):
                names = [x for x in names if pd.notna(f.get(x))]
                if not names:
                    row["leaders" if key == "lead" else "challengers"] = 0.0
                    continue
                tn = 1 - len(set(names) & prevp[key]) / len(names)
                prevp[key] = set(names)
                row["leaders" if key == "lead" else "challengers"] = float(f[names].mean() - 2 * cost * tn)
        rows.append(row)
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def deflated_sharpe(x, trial_srs):
    """Probabilité que le Sharpe (par période) de x soit réel, compte tenu du nombre d'essais (Bailey et López de Prado, 2014)."""
    from statistics import NormalDist
    nd, g = NormalDist(), 0.5772156649
    x = pd.Series(x).dropna()
    sr, T = x.mean() / x.std(), len(x)
    sk, ku = x.skew(), x.kurt() + 3
    N = len(trial_srs)
    sr0 = math.sqrt(np.var(trial_srs, ddof=1)) * ((1 - g) * nd.inv_cdf(1 - 1 / N) + g * nd.inv_cdf(1 - 1 / (N * math.e))) if N > 1 else 0
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr ** 2))
    return nd.cdf(z), sr0


def block_bootstrap(x, n=4000, block=6, seed=7):
    x = pd.Series(x).dropna().values
    if len(x) < 2 * block:
        return None
    rng = np.random.default_rng(seed)
    k = int(math.ceil(len(x) / block))
    means = [np.concatenate([x[s:s + block] for s in rng.integers(0, len(x) - block, k)])[:len(x)].mean() for _ in range(n)]
    return {"p5": float(np.percentile(means, 5)), "p50": float(np.percentile(means, 50)), "p95": float(np.percentile(means, 95)),
            "pNeg": float(np.mean(np.array(means) <= 0))}


def placebo(Wf, G, groups, top, step, fwd, n=500, seed=11, cost=0.0):
    """Groupes tirés au hasard à chaque période : distribution de l'écart à l'univers obtenue par chance (sans frais)."""
    rng = np.random.default_rng(seed)
    return np.array([(lambda R: (R["top"] - R["universeEW"]).mean())(simulate(Wf, G, groups, None, top, step, cost=cost, fwd=fwd, rng=rng)) for _ in range(n)])


def crisis(R, a, b):
    x = R.loc[(R.index >= a) & (R.index <= b)]
    if x.empty:
        return None
    c = lambda s: float((1 + x[s]).prod() - 1)
    return {"from": a, "to": b, "top": c("top"), "universeEW": c("universeEW"), "stoxx": c("stoxx"), "periods": len(x)}


def backtest(W, V, uni, est):
    t0 = time.time()
    groups = groups_of(uni)
    cap_now = {s: it.get("capEur") for s, it in uni.items()}
    Wf = W.ffill(limit=2)
    P = panels(W, W[BENCH], V, est)
    G = group_signals(P, groups)
    fwd = Fwd(Wf, groups)
    log(f"  mesures calculées ({time.time() - t0:.0f} s)")
    # 1. stratégie de référence (composite, 3 groupes, 4 semaines), leaders et challengers
    R = simulate(Wf, G, groups, "composite", 3, 4, P=P, cap_now=cap_now, picks=True, fwd=fwd)
    if R.empty or len(R) < 12:
        return None, R, G, P
    res = {"periods": len(R), "from": R.index[0], "to": R.index[-1], "stepWeeks": 4, "topGroups": 3, "cost": COST,
           "perf": {k: perf(R[k], 4) for k in R.columns}, "vsUniverse": {k: excess_stats(R[k], R["universeEW"]) for k in ("top", "leaders", "challengers")},
           "vsStoxx": {k: excess_stats(R[k], R["stoxx"]) for k in ("top", "leaders", "challengers", "universeEW")},
           "challengerVsLeader": excess_stats(R["challengers"], R["leaders"])}
    mid = R.index[len(R) // 2]
    res["halves"] = {k: [excess_stats(R.loc[:mid, k], R.loc[:mid, "universeEW"]), excess_stats(R.loc[mid:, k], R.loc[mid:, "universeEW"])] for k in ("top", "leaders", "challengers")}
    res["halvesSplit"] = mid
    # 2. stress test : toutes les variantes essayées sont déclarées (6 signaux × 2 tailles × 2 durées = 24 essais)
    grid, xs = [], {}
    for sig in SIGNALS:
        if sig not in G or G[sig].notna().sum().sum() == 0:
            continue
        for top in (3, 6):
            for step in (4, 13):
                Rg = simulate(Wf, G, groups, sig, top, step, fwd=fwd)
                if Rg.empty:
                    continue
                x = Rg["top"] - Rg["universeEW"]
                key = f"{sig}|{top}|{step}"
                xs[key] = (x, step)
                st = excess_stats(Rg["top"], Rg["universeEW"])
                grid.append({"signal": sig, "top": top, "step": step, "from": Rg.index[0], "periods": len(Rg),
                             "cagr": perf(Rg["top"], step).get("cagr"), "cagrEW": perf(Rg["universeEW"], step).get("cagr"),
                             "excessPerYear": x.mean() * PER_YEAR / step, "t": st.get("t"), "beatPct": st.get("beatPct"),
                             "maxdd": perf(Rg["top"], step).get("maxdd")})
    # règle de conservation fixée à l'avance (entrer dans les 3 premiers, sortir au-delà du 8e) : 2 essais de plus, déclarés
    for sig in ("composite", "mom12"):
        Rg = simulate(Wf, G, groups, sig, 3, 4, fwd=fwd, keep=8)
        if Rg.empty:
            continue
        x = Rg["top"] - Rg["universeEW"]
        xs[f"{sig}+conservation|3|4"] = (x, 4)
        st = excess_stats(Rg["top"], Rg["universeEW"])
        grid.append({"signal": sig + "+conservation", "top": 3, "step": 4, "from": Rg.index[0], "periods": len(Rg),
                     "cagr": perf(Rg["top"], 4).get("cagr"), "cagrEW": perf(Rg["universeEW"], 4).get("cagr"),
                     "excessPerYear": x.mean() * PER_YEAR / 4, "t": st.get("t"), "beatPct": st.get("beatPct"), "maxdd": perf(Rg["top"], 4).get("maxdd")})
    best = max(grid, key=lambda g: g["t"] if g["t"] is not None else -9)
    bx, bstep = xs[f"{best['signal']}|{best['top']}|{best['step']}"]
    dsr, sr0 = deflated_sharpe(bx, [x.mean() / x.std() for x, _ in xs.values() if x.std() > 0])
    stress = {"trials": len(grid), "grid": grid, "best": best, "deflatedSharpe": dsr, "sharpeByChance": sr0 * math.sqrt(PER_YEAR / bstep),
              "bootstrapComposite": block_bootstrap(R["top"] - R["universeEW"])}
    # frais doublés sur la référence
    R2 = simulate(Wf, G, groups, "composite", 3, 4, cost=2 * COST, fwd=fwd)
    stress["doubleCost"] = excess_stats(R2["top"], R2["universeEW"])
    # krachs
    stress["crises"] = [c for c in (crisis(R, "2020-02-01", "2020-05-01"), crisis(R, "2022-01-01", "2022-10-15")) if c]
    # placebo : groupes au hasard
    pl = placebo(Wf, G, groups, 3, 4, fwd, n=PLACEBO_N)
    R0 = simulate(Wf, G, groups, "composite", 3, 4, cost=0.0, fwd=fwd)
    actual = float((R0["top"] - R0["universeEW"]).mean())  # brut de frais, comme les tirages
    stress["placebo"] = {"n": len(pl), "actual": actual, "p5": float(np.percentile(pl, 5)), "p95": float(np.percentile(pl, 95)),
                         "pctBelow": float((pl < actual).mean())}
    res["stress"] = stress
    log(f"  stress test : {len(grid)} essais ({time.time() - t0:.0f} s)")
    return res, R, G, P


def basket(W, cols):
    cols = [c for c in cols if c in W.columns]
    if not cols:
        return None, []
    r = W[cols].ffill(limit=2).pct_change(fill_method=None)
    return (1 + r.mean(axis=1, skipna=True).fillna(0)).cumprod(), cols


def lead_lag(W, step=4, alias=None):
    """Le baromètre américain d'un thème annonce-t-il la chaîne européenne ? Corrélations décalées et règle simple."""
    alias = alias or {}
    out = []
    spx, stx = W[US_BENCH].ffill(), W[BENCH].ffill()
    for th in THEMES:
        us, usc = basket(W, th["us"])
        eu, euc = basket(W, [alias.get(s, s) for s in th["eu"]])
        if us is None or eu is None or len(euc) < 2:
            continue
        idx = list(range(0, len(W) - step, step))
        usx = pd.Series([us.iloc[i + step] / us.iloc[i] - spx.iloc[i + step] / spx.iloc[i] for i in idx], index=W.index[idx])
        eux = pd.Series([eu.iloc[i + step] / eu.iloc[i] - stx.iloc[i + step] / stx.iloc[i] for i in idx], index=W.index[idx])
        corr = {f"t+{k}": float(usx.corr(eux.shift(-k))) for k in range(0, 4)}
        rule, always, stxr = [], [], []
        for i in idx:
            if i < 13:
                continue
            sig = us.iloc[i] / us.iloc[i - 13] - spx.iloc[i] / spx.iloc[i - 13] > 0
            e, s = eu.iloc[i + step] / eu.iloc[i] - 1, stx.iloc[i + step] / stx.iloc[i] - 1
            rule.append(e if sig else s)
            always.append(e)
            stxr.append(s)
        out.append({"theme": th["key"], "name": th["name"], "us": usc, "eu": euc, "corr": corr,
                    "rule": perf(rule, step), "alwaysEU": perf(always, step), "stoxx": perf(stxr, step), "ruleVsAlways": excess_stats(rule, always)})
    return out


def ai_case(W, G, P, uni):
    """Cas de l'IA : dates de détection après le lancement de ChatGPT (30/11/2022) et rendements ensuite."""
    groups = groups_of(uni)
    cap_now = {s: it.get("capEur") for s, it in uni.items()}
    Wf = W.ffill(limit=2)
    bench = W[BENCH].ffill()
    start = Wf.index.searchsorted(pd.Timestamp("2022-11-30"))
    spx = W[US_BENCH].ffill()
    us, _ = basket(W, THEMES[0]["us"])
    us_date = None
    for t in range(max(start, 16), len(W)):
        if all(us.iloc[k] / us.iloc[k - 13] - spx.iloc[k] / spx.iloc[k - 13] > 0 for k in range(t - 3, t + 1)):
            us_date = W.index[t]
            break
    targets = {}
    for key in ("ASML.AS", "SU.PA", "IFX.DE", "PRY.MI"):
        if key in groups:
            targets.setdefault(groups[key], key)
    out = {"chatgpt": "2022-11-30", "usBarometerConfirmed": us_date, "groups": []}
    for grp, ex in targets.items():
        tr = G["trending"][grp] if grp in G["trending"].columns else None
        hits = [t for t in range(start, len(Wf)) if tr is not None and bool(tr.iloc[t])]
        first = hits[0] if hits else None
        rec = {"group": grp, "example": ex, "firstTrending": Wf.index[first] if first is not None else None}
        if first is not None:
            lead, chal = leader_challenger(P, groups, grp, cap_now, Wf, first)
            end = min(first + 52, len(Wf) - 1)
            r = lambda s, a, b: float(Wf.iloc[b][s] / Wf.iloc[a][s] - 1) if s and pd.notna(Wf.iloc[a][s]) and pd.notna(Wf.iloc[b][s]) else None
            rec.update({"leader": lead, "challenger": chal, "weeksAfterChatGPT": first - start,
                        "leader12m": r(lead, first, end), "challenger12m": r(chal, first, end), "stoxx12m": float(bench.iloc[end] / bench.iloc[first] - 1),
                        "leaderToNow": r(lead, first, len(Wf) - 1), "challengerToNow": r(chal, first, len(Wf) - 1),
                        "stoxxToNow": float(bench.iloc[-1] / bench.iloc[first] - 1), "leaderFromChatGPT": r(lead, start, len(Wf) - 1)})
        out["groups"].append(rec)
    return out


def run_backtest():
    uni = read_json(UNIVERSE, {}).get("items", {})
    est = read_json(ESTIMATES, {})
    W, V = load_weekly()
    res, R, G, P = backtest(W, V, uni, est)
    if res is None:
        log("Test historique : historique trop court, rien n'est écrit")
        return
    res["leadLag"] = lead_lag(W, alias=read_json(UNIVERSE, {}).get("themeAlias"))
    res["aiCase"] = ai_case(W, G, P, uni)
    old = read_json(BACKTEST, {})
    if old.get("trends"):
        res["trends"] = old["trends"]  # test Google Trends : conservé (lancé à part)
    res["generatedAt"] = datetime.now(timezone.utc).isoformat()
    res["universe"] = {"n": len(uni), "minCapEur": MIN_CAP_EUR,
                       "bias": "univers d'aujourd'hui appliqué au passé : les sociétés disparues ou devenues petites manquent (biais du survivant) ; "
                               "comparer à l'univers à poids égaux, qui a le même biais, plutôt qu'au STOXX 600"}
    write_json(BACKTEST, res, indent=1)
    print(report(res))


# --------------------------------------------------------------------------- Google Trends (expérimental)
def trends_test():
    """Recherches Google (monde, 5 ans, hebdomadaire) : la hausse de l'intérêt annonce-t-elle la chaîne européenne du thème ?"""
    try:
        from pytrends.request import TrendReq
    except Exception:
        log("Google Trends : pytrends non installé")
        return
    W, _ = load_weekly()
    stx = W[BENCH].ffill()
    py = TrendReq(hl="en-US", tz=0, timeout=(10, 30))  # sans « retries » : incompatible avec urllib3 2 ; nouvel essai géré ici
    out = []
    for th in THEMES:
        kw = th.get("trends")
        rec = {"theme": th["key"], "keyword": kw}
        try:
            df = None
            for attempt in range(3):
                try:
                    py.build_payload([kw], timeframe="today 5-y", geo="")
                    df = py.interest_over_time()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(30 * (attempt + 1))
            s = df[kw].astype(float)
            s.index = pd.to_datetime(s.index).to_period("W-FRI").to_timestamp("W-FRI")
            s = s.groupby(level=0).last().reindex(W.index).ffill(limit=1)
            eu, euc = basket(W, [(read_json(UNIVERSE, {}).get("themeAlias") or {}).get(x, x) for x in th["eu"]])
            step = 4
            idx = [i for i in range(4, len(W) - step, step) if pd.notna(s.iloc[i]) and pd.notna(s.iloc[i - 4])]
            chg = pd.Series([math.log((s.iloc[i] + 1) / (s.iloc[i - 4] + 1)) for i in idx], index=W.index[idx])
            ex = pd.Series([eu.iloc[i + step] / eu.iloc[i] - stx.iloc[i + step] / stx.iloc[i] for i in idx], index=W.index[idx])
            exb = pd.Series([eu.iloc[i] / eu.iloc[i - step] - stx.iloc[i] / stx.iloc[i - step] for i in idx], index=W.index[idx])
            rec.update({"n": len(idx), "corrNext": float(chg.corr(ex)), "corrSame": float(chg.corr(exb)), "last": float(s.dropna().iloc[-1]),
                        "change3m": float(s.dropna().iloc[-1] / max(1.0, s.dropna().iloc[-14]) - 1) if s.notna().sum() > 14 else None})
        except Exception as e:
            rec["error"] = str(e)[:120]
        out.append(rec)
        time.sleep(8)
    res = read_json(BACKTEST, {})
    res["trends"] = {"at": date.today().isoformat(), "themes": out}
    write_json(BACKTEST, res, indent=1)
    for r in out:
        log(f"  Google Trends {r['keyword']:16s} " + (f"corrélation avec le mois suivant {r['corrNext']:+.2f}, même mois {r['corrSame']:+.2f} ({r['n']} périodes)" if "corrNext" in r else "indisponible : " + r.get("error", "")))


def report(res):
    p = lambda v: "   n/d" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:+6.1f} %"
    f2 = lambda v: "n/d" if v is None else f"{v:.2f}"
    L = ["=" * 78, "SECTEURS EN TENDANCE — TEST HISTORIQUE ET STRESS TEST", "=" * 78,
         f"{res['periods']} périodes de {res['stepWeeks']} semaines, {str(res['from'])[:10]} → {str(res['to'])[:10]}, {res['topGroups']} meilleurs groupes, frais {res['cost'] * 100:.1f} % par aller simple",
         f"Univers : {res['universe']['n']} sociétés ; " + res["universe"]["bias"], "", "Performance annualisée (référence : note composite) :"]
    for k, v in res["perf"].items():
        if v:
            L.append(f"  {k:12s} CAGR {p(v['cagr'])}  vol {p(v['vol'])}  Sharpe {f2(v['sharpe'])}  pire baisse {p(v['maxdd'])}")
    L.append("\nÉcart par période face à l'univers à poids égaux :")
    for k, v in res["vsUniverse"].items():
        if v:
            L.append(f"  {k:12s} {p(v['meanPerPeriod'])}, t = {f2(v['t'])}, bat l'univers {v['beatPct'] * 100:.0f} % du temps")
    v = res["challengerVsLeader"]
    if v:
        L.append(f"  challenger − leader : {p(v['meanPerPeriod'])}, t = {f2(v['t'])}")
    S = res["stress"]
    L.append(f"\nSTRESS TEST — {S['trials']} essais déclarés (signal × nombre de groupes × durée de détention) :")
    L.append(f"  {'signal':22s} {'grp':>3s} {'sem':>3s} {'depuis':>10s} {'CAGR':>8s} {'univers':>8s} {'écart/an':>9s} {'t':>6s} {'pire baisse':>11s}")
    for g in sorted(S["grid"], key=lambda g: -(g["t"] or -9)):
        L.append(f"  {g['signal']:22s} {g['top']:>3d} {g['step']:>3d} {str(g['from'])[:10]:>10s} {p(g['cagr'])} {p(g['cagrEW'])} {p(g['excessPerYear']):>9s} {f2(g['t']):>6s} {p(g['maxdd']):>11s}")
    b = S["best"]
    L.append(f"  Meilleur essai : {b['signal']}, {b['top']} groupes, {b['step']} semaines (t = {f2(b['t'])}) ; Deflated Sharpe = {S['deflatedSharpe']:.2f} (exigé ≥ 0,95) ; "
             f"Sharpe obtenu par chance avec {S['trials']} essais ≈ {S['sharpeByChance']:.2f}")
    bb = S.get("bootstrapComposite")
    if bb:
        L.append(f"  Bootstrap (composite) : écart moyen par période entre {p(bb['p5'])} et {p(bb['p95'])} dans 90 % des cas ; probabilité ≤ 0 : {bb['pNeg'] * 100:.0f} %")
    pl = S["placebo"]
    L.append(f"  Placebo (groupes au hasard, {pl['n']} tirages, sans frais) : écart entre {p(pl['p5'])} et {p(pl['p95'])} ; la note composite ({p(pl['actual'])} brut) fait mieux que {pl['pctBelow'] * 100:.0f} % des tirages")
    dc = S.get("doubleCost")
    if dc:
        L.append(f"  Frais doublés : {p(dc['meanPerPeriod'])} par période, t = {f2(dc['t'])}")
    for c in S["crises"]:
        L.append(f"  Krach {c['from']} → {c['to']} : 3 meilleurs secteurs {p(c['top'])}, univers {p(c['universeEW'])}, STOXX 600 {p(c['stoxx'])}")
    L.append("\nBaromètre américain → chaîne européenne :")
    for x in res["leadLag"]:
        c = x["corr"]
        L.append(f"  {x['name']:34s} corrélation t+0 {c['t+0']:+.2f} · t+1 {c['t+1']:+.2f} · t+2 {c['t+2']:+.2f} · t+3 {c['t+3']:+.2f}")
        if x["rule"] and x["alwaysEU"]:
            L.append(f"  {'':34s} règle CAGR {p(x['rule']['cagr'])}, pire baisse {p(x['rule']['maxdd'])} | toujours investi {p(x['alwaysEU']['cagr'])}, {p(x['alwaysEU']['maxdd'])}")
    a = res["aiCase"]
    L.append(f"\nCas de l'IA (ChatGPT le {a['chatgpt']}) : baromètre américain confirmé le {str(a['usBarometerConfirmed'])[:10]}")
    for g in a["groups"]:
        if g.get("firstTrending") is not None:
            L.append(f"  {g['group']:38s} en tendance le {str(g['firstTrending'])[:10]} · leader {g['leader']} {p(g['leader12m'])} sur 12 mois, challenger {g['challenger']} {p(g['challenger12m'])}, STOXX {p(g['stoxx12m'])}")
    return "\n".join(L)


# --------------------------------------------------------------------------- tableau de bord (classement du jour)
def daily_closes(tickers):
    """Clôtures journalières sur un an, en devise locale, ajustées (lots de 80 titres) : DataFrame dates × titres."""
    import yfinance as yf
    frames = []
    tick = sorted(set(tickers))
    for i in range(0, len(tick), 80):
        batch = tick[i:i + 80]
        for attempt in range(3):
            try:
                df = yf.download(batch, period="1y", interval="1d", auto_adjust=True, progress=False, threads=True, group_by="column")
                break
            except Exception as e:
                log(f"  cours journaliers, lot {i} : erreur {str(e)[:80]}, nouvel essai")
                df = None
                time.sleep(5)
        if df is None or df.empty:
            continue
        frames.append(df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": batch[0]}))
        time.sleep(1)
    if not frames:
        return pd.DataFrame()
    X = pd.concat(frames, axis=1, sort=True)
    X = X.loc[:, ~X.columns.duplicated()]
    X.index = pd.to_datetime(X.index).tz_localize(None).normalize()
    X = X[~X.index.duplicated(keep="last")].sort_index()
    return X.where(X > 0)


def companies(uni, extra, stock, W, groups, out_groups, themes, fetch_daily=True):
    """Fiche de chaque société cotée de l'UE / l'EEE : celles de l'univers des secteurs (≥ 500 M€, chiffres complets)
    et toutes les autres du catalogue (chiffres de base). Cours en devise locale : un an journalier, cinq ans hebdomadaire.
    Écrit 32 petits fichiers (une fiche n'en charge qu'un) et une liste de recherche."""
    rank = {g["key"]: g for g in out_groups}
    roles = {}
    for g in out_groups:
        for k in ("leader", "challenger"):
            if g.get(k):
                roles.setdefault(g[k]["symbol"], []).append([k, "g", g["key"]])
    for th in themes:
        for k in ("leader", "challenger"):
            if th.get(k):
                roles.setdefault(th[k]["symbol"], []).append([k, "t", th["key"]])
        for m in th.get("members") or []:
            roles.setdefault(m["symbol"], []).append(["member", "t", th["key"]])
    cat = read_json(CATALOG, {}).get("items", {})
    by_name = {name_key(it.get("name")): sym for sym, it in uni.items()}
    # une société du catalogue déjà dans l'univers sous une autre cotation (même nom) n'est pas répétée
    cat_only = {sym: it for sym, it in cat.items() if sym not in uni and sym not in extra and name_key(it.get("name")) not in by_name}
    syms = sorted(set(uni) | set(extra) | set(cat_only))
    # hebdomadaire 5 ans, remis en devise locale (le moteur des secteurs travaille en euros)
    Wl = W.iloc[-262:].copy()
    for cur, pair in FX_PAIRS.items():
        if pair in Wl.columns:
            cols = [c for c in syms if c in Wl.columns and str((uni.get(c) or extra.get(c) or {}).get("currency") or "").upper() == cur]
            if cols:
                Wl[cols] = Wl[cols].mul(Wl[pair].ffill(), axis=0)
    D = pd.DataFrame()
    if fetch_daily:
        t0 = time.time()
        D = daily_closes(syms)
        log(f"Cours journaliers des fiches : {D.shape[1]} titres, {D.shape[0]} séances, {time.time() - t0:.0f} s")
        miss = [x for x in cat_only if x not in Wl.columns]
        if miss:
            t0 = time.time()
            W2, _ = download_weekly(miss, years=5)  # cours bruts en devise locale
            if not W2.empty:
                W2 = clean_prices(W2.where(W2 > 0))
                Wl = Wl.join(W2.reindex(Wl.index, method="nearest", tolerance=pd.Timedelta(days=3)), how="left")
            log(f"Cours hebdomadaires du catalogue : {W2.shape[1] if not W2.empty else 0} titres, {time.time() - t0:.0f} s")
    sig = lambda v: None if v is None or not np.isfinite(v) else float(f"{v:.5g}")
    items, index = {}, []
    for sym in syms:
        it = uni.get(sym) or extra.get(sym) or cat_only.get(sym) or {}
        base = stock(sym) if (sym in uni or sym in extra) else None
        base = base or {"symbol": sym, "name": it.get("name"), "country": it.get("hq") or it.get("country"), "capEur": it.get("capEur"),
                        "pea": (it.get("hq") or it.get("country")) in EU_EEA, "isin": it.get("isin")}
        g = groups.get(sym)
        gi = rank.get(g) or {}
        rec = dict(base, sector=it.get("sector"), industry=it.get("industry"), exchange=it.get("exchange"), currency=it.get("currency"),
                   grossMargin=it.get("grossMargin"), revenue=it.get("revenue"), reco=it.get("reco"), insiderPct=it.get("insiderPct"),
                   turnoverEur=it.get("turnoverEur"), group=g, groupRank=gi.get("rank"), groupTrending=gi.get("trending"), groupEmerging=gi.get("emerging"),
                   roles=roles.get(sym) or [], basic=sym in cat_only)
        if sym in Wl.columns and Wl[sym].notna().sum() >= 20:
            rec["w"] = [sig(v) for v in Wl[sym].tolist()]
        if sym in D.columns and D[sym].notna().sum() >= 20:
            rec["d"] = [sig(v) for v in D[sym].tolist()]
        items[sym] = rec
        cap = rec.get("capEur")
        index.append([sym, rec.get("name"), rec.get("country"), round(cap / 1e6) if cap else None, rec.get("sector"), g,
                      "t" if gi.get("trending") else "e" if gi.get("emerging") else "", 1 if rec.get("pea") else 0, rec.get("isin")])
    gen = datetime.now(timezone.utc).isoformat()
    common = {"format": "euro-signal-sector-companies", "generatedAt": gen, "groups": len(out_groups),
              "wDates": [min(d.date(), date.today()).isoformat() for d in Wl.index], "dDates": [d.strftime("%Y-%m-%d") for d in D.index]}
    CO_DIR.mkdir(parents=True, exist_ok=True)
    shards = [dict(common, shard=k, items={}) for k in range(CO_SHARDS)]
    for sym, rec in items.items():
        shards[shard_of(sym)]["items"][sym] = rec
    for k, sh in enumerate(shards):
        write_json(CO_DIR / f"{k}.json", sh)
    write_json(CO_INDEX, {"format": "euro-signal-societes", "generatedAt": gen, "n": len(index), "shards": CO_SHARDS, "dir": "data/societes",
                          "cols": ["symbol", "name", "country", "capMEur", "sector", "group", "trend", "pea", "isin"], "rows": index})
    if OUT_CO.exists():
        OUT_CO.unlink()
    size = sum(f.stat().st_size for f in CO_DIR.glob("*.json")) // 1024
    log(f"Fiches sociétés : {len(items)} dont {len(cat_only)} hors univers des secteurs ({sum(1 for v in items.values() if 'd' in v)} avec un an de cours, "
        f"{sum(1 for v in items.values() if 'w' in v)} avec cinq ans), {size} Ko en {CO_SHARDS} fichiers ; liste de recherche {CO_INDEX.stat().st_size // 1024} Ko")


def daily_rows(tickers):
    import yfinance as yf
    def one(s):
        try:
            h = with_retry(lambda: yf.Ticker(s).history(period="1y", interval="1d", auto_adjust=False), tries=2)
            return s, [[i.strftime("%Y-%m-%d"), *(round(float(v), 4) if v == v else None for v in (r["Open"], r["High"], r["Low"], r["Close"])),
                        int(r["Volume"]) if r["Volume"] == r["Volume"] else None] for i, r in h.iterrows() if r["Close"] == r["Close"] and r["Close"] > 0]
        except Exception:
            return s, None
    with ThreadPoolExecutor(THREADS) as ex:
        return {s: rows for s, rows in ex.map(one, tickers) if rows}


def dashboard(fetch_daily=True):
    U = read_json(UNIVERSE, {})
    uni = U.get("items", {})
    alias, extra = U.get("themeAlias") or {}, U.get("themeExtra") or {}
    est = read_json(ESTIMATES, {})
    W, V = load_weekly()
    groups = groups_of(uni)
    cap_now = {s: it.get("capEur") for s, it in uni.items()}
    P = panels(W, W[BENCH], V, est)
    G = group_signals(P, groups)
    Wf = W.ffill(limit=2)
    t = len(W) - 1
    rb = revision_breadth(est, groups) if est else {}
    def stock(s):
        if not s:
            return None
        it, e = uni.get(s) or extra.get(s) or {}, est.get(s) or {}
        r = e.get("rev") or {}
        recent = (date.today() - timedelta(days=200)).isoformat()
        sur = [x for x in (e.get("surprises") or []) if x[0] >= recent][-1:] or [None]
        return {"symbol": s, "name": it.get("name"), "country": it.get("country"), "pea": it.get("pea"), "isin": it.get("isin"),
                "capEur": it.get("capEur"), "revGrowth": it.get("revGrowth"), "opMargin": it.get("opMargin"), "fwdPE": it.get("fwdPE"),
                "analysts": it.get("analysts"), "upside": it.get("upside"), "instPct": it.get("instPct"),
                "revUp30": r.get("up30"), "revDown30": r.get("down30"), "lastSurprise": sur[0],
                "rs6": P["rs6"].iloc[t].get(s), "rs3": P["rs3"].iloc[t].get(s), "volume": P["volume"].iloc[t].get(s) if "volume" in P else None}
    row = lambda k, g: G[k].iloc[t].get(g) if k in G else None
    out_groups = []
    for grp in G["rank"].iloc[t].dropna().sort_values().index:
        lead, chal = leader_challenger(P, groups, grp, cap_now, Wf, t)
        mem = sorted([s for s, g in groups.items() if g == grp and pd.notna(P["rs6"].iloc[t].get(s))], key=lambda s: -P["rs6"].iloc[t][s])
        prev = G["rank"].iloc[t - 8].get(grp) if t >= 8 else None
        sector = next((uni[s].get("sector") for s in mem if uni.get(s)), None)
        rank = int(row("rank", grp))
        out_groups.append({"key": grp, "sector": sector, "n": int(row("n", grp)), "rs6": row("rs6", grp), "rs3": row("rs3", grp), "mom12": row("mom12", grp),
                           "breadth": row("breadth", grp), "highs": row("highs", grp), "score": row("composite", grp), "rank": rank,
                           "rank8w": int(prev) if prev is not None and pd.notna(prev) else None, "trending": bool(row("trending", grp)),
                           "emerging": bool(prev is not None and pd.notna(prev) and prev - rank >= max(5, len(G["rank"].columns) // 6) and (row("rs3", grp) or 0) > 0),
                           "volume": row("volume", grp), "surprise": row("surprise", grp),
                           "revisions": (rb.get(grp) or {}).get("breadth"), "revisionsN": (rb.get(grp) or {}).get("n"),
                           "leader": stock(lead), "challenger": stock(chal), "top": [stock(s) for s in mem[:5]]})
    spx, bench = W[US_BENCH].ffill(), W[BENCH].ffill()
    themes = []
    for th in THEMES:
        eu_t = list(dict.fromkeys(alias.get(s, s) for s in th["eu"]))
        us, usc = basket(W, th["us"])
        eu, euc = basket(W, eu_t)
        if us is None or eu is None:
            continue
        rsx = lambda a, b, k: float(a.iloc[-1] / a.iloc[-1 - k] - b.iloc[-1] / b.iloc[-1 - k])
        mem = [s for s in euc if (s in uni or s in extra) and pd.notna(P["rs6"].iloc[t].get(s))]
        size = sorted(mem, key=lambda s: -(cap_now.get(s) or 0))
        lead = size[0] if size else None
        chal = max(size[1:4], key=lambda s: P["rs6"].iloc[t][s]) if len(size) > 1 else None
        revs = [(est.get(s) or {}).get("rev") for s in mem]
        revs = [r for r in revs if r and r.get("up30") is not None and r.get("down30") is not None]
        themes.append({"key": th["key"], "name": th["name"], "us": usc, "eu": euc, "missing": [s for s in eu_t if s not in euc],
                       "usRs13": rsx(us, spx, 13), "usRs26": rsx(us, spx, 26), "euRs13": rsx(eu, bench, 13), "euRs26": rsx(eu, bench, 26),
                       "revisions": (sum(r["up30"] > r["down30"] for r in revs) - sum(r["down30"] > r["up30"] for r in revs)) / len(revs) if len(revs) >= 3 else None,
                       "leader": stock(lead), "challenger": stock(chal), "members": [stock(s) for s in sorted(mem, key=lambda s: -P["rs6"].iloc[t][s])]})
    picks = set()
    for x in out_groups[:8] + themes:
        for k in ("leader", "challenger"):
            if x.get(k):
                picks.add(x[k]["symbol"])
    bt = read_json(BACKTEST, None)
    keys = ("from", "to", "periods", "vsUniverse", "vsStoxx", "challengerVsLeader", "halves", "halvesSplit", "aiCase", "perf", "leadLag", "stress", "trends", "generatedAt")
    payload = {"format": "euro-signal-sectors", "generatedAt": datetime.now(timezone.utc).isoformat(),
               "asOf": str(min(W.index[-1].date(), date.today())),  # semaine en cours : étiquetée au vendredi, affichée à la date du jour
               "universe": {"n": len(uni), "minCapEur": MIN_CAP_EUR}, "estimatesAt": max((v.get("fetched", "") for v in est.values()), default=None),
               "groups": out_groups, "themes": themes, "daily": daily_rows(sorted(picks)) if fetch_daily else {},
               "backtest": {k: bt.get(k) for k in keys} if bt else None}
    write_json(OUT, payload)
    try:
        companies(uni, extra, stock, W, groups, out_groups, themes, fetch_daily)
    except Exception as e:  # la fiche des sociétés ne doit jamais empêcher le classement du jour
        log(f"Fiches sociétés non écrites : {str(e)[:200]}")
    log(f"Secteurs : {len(out_groups)} groupes, {sum(x['trending'] for x in out_groups)} en tendance, {len(themes)} thèmes, {len(picks)} leaders / challengers")


# --------------------------------------------------------------------------- données simulées (vérification hors ligne)
def synthetic(seed=3, start="2018-10-05", end="2026-10-09"):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="W-FRI")
    T = len(dates)
    inds = [("Semiconductor Equipment & Materials", "Technology"), ("Semiconductors", "Technology"), ("Electrical Equipment & Parts", "Industrials"),
            ("Banks - Regional", "Financial Services"), ("Utilities - Regulated Electric", "Utilities"), ("Aerospace & Defense", "Industrials"),
            ("Drug Manufacturers - General", "Healthcare"), ("Auto Manufacturers", "Consumer Cyclical"), ("Software - Infrastructure", "Technology")]
    mkt = rng.normal(0.0015, 0.022, T)
    uni, cols, vols, est = {}, {}, {}, {}
    names = {"Semiconductor Equipment & Materials": ["ASML.AS", "ASM.AS", "BESI.AS", "AIXA.DE", "SOI.PA"], "Electrical Equipment & Parts": ["SU.PA", "LR.PA", "PRY.MI", "NEX.PA", "ENR.DE"],
             "Semiconductors": ["IFX.DE", "STMPA.PA", "TPRO.MI", "WAF.DE", "NOD.OL"], "Aerospace & Defense": ["RHM.DE", "HO.PA", "SAF.PA", "LDO.MI", "HAG.DE"],
             "Software - Infrastructure": ["YSN.DE", "WITH.HE", "FSECURE.HE", "YUBICO.ST", "ALLIX.PA"]}
    for k, (ind, sec) in enumerate(inds):
        boom = np.zeros(T)
        if ind in ("Semiconductor Equipment & Materials", "Electrical Equipment & Parts", "Semiconductors"):
            boom[(dates > "2023-02-01") & (dates < "2024-08-01")] = 0.008
        if ind == "Aerospace & Defense":
            boom[(dates > "2022-03-01")] = 0.006
        for j, s in enumerate(names.get(ind, [f"X{k}{j}.PA" for j in range(6)])):
            r = mkt * rng.uniform(0.7, 1.4) + boom * (1.3 if j == 1 else 1.0) + rng.normal(0, 0.03, T)
            cols[s] = 50 * np.exp(np.cumsum(r))
            vols[s] = rng.uniform(1e5, 1e6) * np.exp(rng.normal(0, 0.3, T)) * (1 + 3 * (r > 0) * (boom > 0))
            uni[s] = {"symbol": s, "name": s, "country": "FR", "hq": "FR", "sector": sec, "industry": ind,
                      "capEur": float(10 ** rng.uniform(9, 11.5)) * (3 if j == 0 else 1), "pea": True, "currency": "EUR"}
            qd = [d for d in dates[::13]][-12:]
            est[s] = {"rev": {"up30": int(rng.integers(0, 5)), "down30": int(rng.integers(0, 5))},
                      "surprises": [[str(d.date()), float(rng.normal(2 if ind in names else 0, 5))] for d in qd], "fetched": "2026-10-09"}
    us_boom = np.zeros(T)
    us_boom[(dates > "2022-12-15") & (dates < "2024-07-01")] = 0.012
    for s in sorted({x for th in THEMES for x in th["us"]}):
        cols[s] = 100 * np.exp(np.cumsum(mkt + us_boom + rng.normal(0, 0.03, T)))
    cols[BENCH] = 400 * np.exp(np.cumsum(mkt))
    cols[US_BENCH] = 3000 * np.exp(np.cumsum(mkt * 1.1))
    SEC.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(cols, index=dates).to_csv(WEEKLY, compression="gzip", float_format="%.5g")
    pd.DataFrame(vols, index=dates).to_csv(WEEKLY_VOL, compression="gzip", float_format="%.4g")
    write_json(UNIVERSE, {"generatedAt": datetime.now(timezone.utc).isoformat(), "items": uni})
    write_json(ESTIMATES, est)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--universe-if-older", type=int, default=None, help="reconstruit l'univers s'il a plus de N jours")
    ap.add_argument("--estimates", action="store_true")
    ap.add_argument("--prices", action="store_true")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--trends", action="store_true")
    ap.add_argument("--dashboard", action="store_true")
    ap.add_argument("--no-daily", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--weekly", action="store_true", help="une fois par semaine : univers, révisions, cours, test historique, Google Trends")
    a = ap.parse_args()
    if a.weekly:
        if universe_age() < 7:
            log(f"Secteurs : univers de {universe_age()} jour(s), mise à jour hebdomadaire non due")
            return 0
        a.universe = a.estimates = a.prices = a.backtest = a.trends = True
    if a.synthetic:
        synthetic()
    rebuilt = False
    if a.universe or (a.universe_if_older is not None and universe_age() >= a.universe_if_older):
        build_universe()
        rebuilt = True
    if a.estimates or rebuilt:
        refresh_estimates()
    if a.prices:
        fetch_prices()
    if a.backtest:
        run_backtest()
    if a.trends:
        try:
            trends_test()
        except Exception as e:  # expérimental : ne bloque jamais le reste
            log(f"Google Trends : {str(e)[:120]}")
    if a.dashboard:
        if not a.synthetic and (a.weekly or catalog_age() >= 7):
            try:
                screen_catalog()
            except Exception as e:  # le classement du jour ne dépend pas du catalogue
                log(f"Catalogue non mis à jour : {str(e)[:160]}")
        dashboard(fetch_daily=not a.no_daily and not a.synthetic)
    return 0


if __name__ == "__main__":
    sys.exit(main())
