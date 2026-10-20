"""
Euro Signal — cours quotidiens via Yahoo Finance (yfinance), exécuté par GitHub Actions.

- Univers : tous les émetteurs dont data/latest.json contient une déclaration portant sur des actions.
- Ticker : correspondance manuelle de run.py, sinon recherche Yahoo par ISIN (préférence Euronext Paris),
  mise en cache dans data/tickers.json (un échec est réessayé après 7 jours). Secours : listes officielles des bourses
  (Euronext, Nasdaq Nordic ; ISIN → symbole, data/backup-isins.json) pour un ISIN introuvable ou un cours figé.
- Historique : 2 ans quotidiens. Yahoo fournit des cours déjà ajustés des divisions d'actions ; on les
  remet en cours bruts et on transmet la liste des divisions, pour que le moteur ajuste lui-même
  le prix payé par les dirigeants.
- Écrit data/prices.json (non versionné : régénéré à chaque exécution).
"""
import json
import math
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yahoo  # noqa: E402  (lien Yahoo robuste : nouvelles tentatives, compteurs)

yahoo.configure()

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LATEST = DATA / "latest.json"
TICKERS = DATA / "tickers.json"
OUT = DATA / "prices.json"
BENCH = "^FCHI"  # CAC 40, indice de référence de l'étude d'événements
MARKET = "^STOXX"  # STOXX Europe 600 : force relative et tendance du marché européen
EU_SUFFIXES = (".PA", ".AS", ".BR", ".MI", ".MC", ".DE", ".LS", ".IR", ".VI", ".HE", ".ST", ".OL", ".CO")
EU_ALL = EU_SUFFIXES + (".F", ".HM", ".SG", ".DU", ".MU", ".BE", ".HA")  # bourses régionales allemandes en dernier recours
HOME = {"FR": ".PA", "DE": ".DE", "IT": ".MI", "ES": ".MC", "NL": ".AS", "BE": ".BR", "PT": ".LS", "IE": ".IR", "AT": ".VI", "FI": ".HE", "LU": ".PA", "SE": ".ST", "NO": ".OL", "DK": ".CO"}
UA = {"User-Agent": "Mozilla/5.0 (euro-signal personal)"}
# Corrections vérifiées (revue du 2026-10-08) : priorité absolue sur la recherche Yahoo
OVERRIDES = {
    "DE0005785604": "FRE.DE",   # Fresenius (et non 1FRE.MI, segment étranger de Milan)
    "DE000A2YNT30": "ACT.DE",   # AlzChem
    "IT0005037210": "TNXT.MI",  # Tinexta
    "ES0177542018": "IAG.MC",   # International Airlines Group (et non Londres)
    "ES0105375002": "EAT.MC",   # AmRest (et non Varsovie)
}
REGIONAL = (".F", ".HM", ".SG", ".DU", ".MU", ".BE", ".HA")


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def manual_map():
    try:
        sys.path.insert(0, str(ROOT))
        from run import ISIN_TO_TICKER  # correspondances déjà vérifiées dans insider-pea
        return dict(ISIN_TO_TICKER)
    except Exception:
        return {}


def search_yahoo(isin):
    quotes = []
    try:
        quotes = yf.Search(isin, max_results=8).quotes or []
    except Exception:
        try:
            r = requests.get("https://query2.finance.yahoo.com/v1/finance/search", params={"q": isin, "quotesCount": 8, "newsCount": 0}, headers=UA, timeout=20)
            quotes = r.json().get("quotes", []) if r.ok else []
        except Exception:
            quotes = []
    eq = [q for q in quotes if q.get("quoteType") == "EQUITY" and q.get("symbol")]
    if not eq:
        return None
    home = HOME.get(isin[:2], ".PA")
    # Cotation du pays d'origine d'abord (prix déclarés en euros), puis grandes places européennes, puis le reste
    eq.sort(key=lambda q: (not q["symbol"].endswith(home), not q["symbol"].endswith(EU_SUFFIXES), not q["symbol"].endswith(EU_ALL)))
    q = eq[0]
    return {"ticker": q["symbol"], "exchange": q.get("exchDisp") or q.get("exchange"), "name": q.get("longname") or q.get("shortname")}


LEGAL = re.compile(r"\b(s\.?a\.?|s\.?e\.?|ag|se|n\.?v\.?|nv|spa|s\.p\.a\.?|ab|publ|plc|oyj|abp|asa|a/s|sca|gmbh|kgaa|co|holding|holdings|group|groupe|ser\.?|b|the|aktiebolag|aktiebolaget)\b", re.I)


def clean_name(n):
    n = unicodedata.normalize("NFKD", str(n or "")).encode("ascii", "ignore").decode()  # Enagás = Enagas
    n = re.sub(r"[(),.&'’\-]", " ", n.lower())
    return " ".join(w for w in LEGAL.sub(" ", n).split() if len(w) > 1)


def search_by_name(isin, name, paid):
    """Secours quand Yahoo ne connaît pas l'ISIN : recherche par nom, uniquement sur la bourse du pays d'origine,
    gardée seulement si le nom correspond et si le cours est cohérent avec le prix payé par le dirigeant."""
    home = HOME.get(isin[:2])
    q0 = clean_name(name)
    if not home or len(q0) < 3:
        return None
    try:
        quotes = yf.Search(q0, max_results=10).quotes or []
    except Exception:
        return None
    want = set(q0.split())
    for q in quotes:
        sym = q.get("symbol") or ""
        if q.get("quoteType") != "EQUITY" or not sym.endswith(home):
            continue
        got = set(clean_name(q.get("longname") or q.get("shortname")).split())
        if not got or len(want & got) / len(want | got) < 0.5:
            continue
        if paid:
            try:
                h = yf.Ticker(sym).history(period="1y", interval="1d", auto_adjust=False)
                closes = {i.strftime("%Y-%m-%d"): float(v) for i, v in h["Close"].items() if v == v and v > 0}
            except Exception:
                closes = {}
            d, price = paid
            ref = [closes[k] for k in sorted(closes) if k <= d][-1:] or list(closes.values())[-1:]
            if not ref or not (0.6 <= price / ref[0] <= 1.6):
                continue
        return {"ticker": sym, "exchange": q.get("exchDisp") or q.get("exchange"), "name": q.get("longname") or q.get("shortname")}
    return None


def taken(cache, isin, found):
    """Ticker déjà attribué à un autre ISIN (ancienne ligne, droits, ISIN mal saisi) : pas de doublon de société."""
    return bool(found) and any(k != isin and (v or {}).get("ticker") == found["ticker"] for k, v in cache.items())


def resolve(isin, cache, manual, today, name=None, paid=None):
    """Recherche Yahoo par ISIN d'abord (fait foi) ; la table manuelle d'insider-pea ne sert qu'en secours."""
    if isin in OVERRIDES:
        return {"ticker": OVERRIDES[isin], "method": "correction vérifiée"}
    c = cache.get(isin)
    if manual.get(isin) and c and not c.get("ticker"):
        return {"ticker": manual[isin], "method": "correspondance insider-pea (secours)"}
    home = HOME.get(isin[:2])
    if c and c.get("ticker") and home in (".ST", ".OL", ".CO") and not str(c["ticker"]).endswith(home) and not c.get("nordicHome"):
        # sociétés nordiques d'abord trouvées sur une bourse régionale allemande (en euros, peu liquide) : nouvelle recherche, une fois
        found = search_yahoo(isin)
        if found and found["ticker"].endswith(home):
            c = dict(found, method="recherche Yahoo par ISIN (cotation d'origine)", resolvedAt=today.isoformat())
        c["nordicHome"] = today.isoformat()
        cache[isin] = c
        time.sleep(0.3)
        return c
    if c and c.get("ticker") and not (not str(c["ticker"]).endswith(EU_SUFFIXES) and not c.get("checkedHome")):
        return c
    if c and c.get("ticker"):  # cotation hors grandes places européennes : une nouvelle recherche, une seule fois
        found = search_yahoo(isin) or c
        found.update({"checkedHome": today.isoformat(), "method": found.get("method") or "recherche Yahoo par ISIN"})
        cache[isin] = found
        time.sleep(0.3)
        return found
    if c and not c.get("ticker") and name and (not c.get("nameTried") or c["nameTried"] < (today - timedelta(days=30)).isoformat()):  # introuvable par ISIN : recherche par nom, chaque mois
        found = search_by_name(isin, name, paid)
        if found and not taken(cache, isin, found):
            found.update({"method": "recherche Yahoo par nom (vérifiée par le prix payé)" if paid else "recherche Yahoo par nom", "resolvedAt": today.isoformat()})
            cache[isin] = found
            time.sleep(0.3)
            return found
        c["nameTried"] = today.isoformat()
    if c and not c.get("ticker") and c.get("triedAt", "") > (today - timedelta(days=7)).isoformat():
        return None
    found = search_yahoo(isin)
    if not found and isin[2] == "O":  # « O » saisi à la place d'un zéro dans la déclaration (ex. ESO130960018)
        found = search_yahoo(isin[:2] + "0" + isin[3:])
        if taken(cache, isin, found):
            found = None
    if found:
        found.update({"method": "recherche Yahoo par ISIN", "resolvedAt": today.isoformat()})
        cache[isin] = found
        time.sleep(0.3)
        return found
    found = search_by_name(isin, name, paid) if name else None
    if found and not taken(cache, isin, found):
        found.update({"method": "recherche Yahoo par nom (vérifiée par le prix payé)" if paid else "recherche Yahoo par nom", "resolvedAt": today.isoformat()})
        cache[isin] = found
        time.sleep(0.3)
        return found
    cache[isin] = {"ticker": None, "triedAt": today.isoformat(), "nameTried": today.isoformat() if name else None}
    return {"ticker": manual[isin], "method": "correspondance insider-pea (secours)"} if manual.get(isin) else None


def local_by_name(isin, name, cache, names):
    """Secours sans réseau : même nom (sans accents ni forme juridique) dans le catalogue de toutes les sociétés cotées
    (data/societes-index.json) ou parmi les sociétés déjà suivies, sur la bourse du pays d'origine. Sert surtout aux
    nouveaux ISIN d'une société déjà suivie (regroupement d'actions, actions nouvelles, ISIN mal saisi) : le calcul
    réunit ensuite les deux ISIN en un seul dossier."""
    home = HOME.get(isin[:2])
    key = clean_name(name)
    if not home or len(key) < 3:
        return None
    for r in load(DATA / "societes-index.json", {}).get("rows", []):
        if r and str(r[0]).endswith(home) and clean_name(r[1]) == key:
            return {"ticker": r[0], "name": r[1], "method": "catalogue des sociétés cotées (même nom)"}
    for other, c in cache.items():
        if other != isin and str((c or {}).get("ticker") or "").endswith(home) and clean_name(names.get(other) or (c or {}).get("name")) == key:
            return {"ticker": c["ticker"], "name": c.get("name"), "method": "même société qu'un autre ISIN suivi"}
    return None


def coherent(h, paid):
    """Le cours de la cotation trouvée colle au prix déclaré par le dirigeant (sinon : autre titre, droits, bons)."""
    if not paid:
        return True
    d, price = paid
    ref = [r[4] for r in h["rows"] if r[0] <= d][-1:] or [h["rows"][-1][4]]
    return bool(ref and ref[0] and 0.6 <= price / ref[0] <= 1.6)


def home_candidate(isin, ticker):
    """Cotation du pays d'origine quand Yahoo propose une place secondaire (bourse régionale allemande, segment étranger)."""
    home = HOME.get(isin[:2])
    if not home or not ticker or ticker.endswith(home):
        return None
    base = ticker.rsplit(".", 1)[0]
    secondary = ticker.endswith(REGIONAL) or (ticker.endswith(".MI") and base.startswith("1")) or not ticker.endswith(EU_SUFFIXES)
    if not secondary:
        return None  # grande place européenne (ex. Ferrari à Milan, Airbus à Paris) : cotation principale, on la garde
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", base):
        return None  # symbole = ISIN : pas de code exploitable
    if ticker.endswith(".MI") and base.startswith("1") and len(base) > 2:
        base = base[1:]  # « 1FRE.MI » : segment des valeurs étrangères de Milan
    return base + home


def fresh_enough(h, today):
    return bool(h and len(h["rows"]) >= 200 and h["rows"][-1][0] >= (today - timedelta(days=7)).isoformat())


def frozen(h, today):
    """Cours figé chez Yahoo : dernière séance vieille de plus de 10 jours (titre retiré, cotation changée)."""
    return bool(h and h.get("rows") and h["rows"][-1][0] < (today - timedelta(days=10)).isoformat())


def try_exchange(isin, table, paid, today, current=None, fetch=None):
    """Cotation de la liste officielle de la bourse (Euronext, Nasdaq Nordic : data/backup-isins.json, relevée la veille par
    backup_prices.py), si elle diffère de la cotation actuelle : retenue quand Yahoo en a deux ans de cours frais qui collent
    au prix déclaré par le dirigeant. → (symbole, historique) ou (None, None)."""
    ex = (table.get(isin) or [None])[0] if isinstance(table, dict) else None
    if not ex or ex == current:
        return None, None
    try:
        h = (fetch or history)(ex, "5y")
    except Exception:
        h = None
    return (ex, h) if h and fresh_enough(h, today) and coherent(h, paid) else (None, None)


DAILY_DAYS = 731  # cours journaliers gardés pour le moteur (2 ans, inchangé) ; au-delà, une clôture par semaine


def history(ticker, period="2y"):
    """Cours journaliers. Avec period="5y" : les 2 dernières années restent journalières (« rows », seules lues par le moteur)
    et les 5 ans complets sont résumés en une clôture par semaine (« weekly », vue 5 ans des fiches)."""
    t = yf.Ticker(ticker)
    h = t.history(period=period, interval="1d", auto_adjust=False, actions=True)
    if h is None or h.empty:
        return None
    currency = None
    try:
        currency = (t.history_metadata or {}).get("currency")
    except Exception:
        pass
    splits = []
    if "Stock Splits" in h.columns:
        for idx, v in h["Stock Splits"].items():
            if v and not math.isnan(v) and v > 0 and v != 1:
                splits.append({"date": idx.strftime("%Y-%m-%d"), "ratio": float(v)})
    rows = []
    for idx, r in h.iterrows():
        c = r.get("Close")
        if c is None or math.isnan(c) or c <= 0:
            continue
        d = idx.strftime("%Y-%m-%d")
        f = 1.0
        for s in splits:
            if s["date"] > d:
                f *= s["ratio"]  # retour au cours brut publié ce jour-là

        def px(x):
            return None if x is None or math.isnan(x) or x <= 0 else round(float(x) * f, 6)

        vol = r.get("Volume")
        rows.append([d, px(r.get("Open")), px(r.get("High")), px(r.get("Low")), px(c), None if vol is None or math.isnan(vol) else round(float(vol) / f)])
    # Dividendes (montant brut par action au jour du détachement) : Euro Signal ajuste les cours passés comme pour une
    # division, sinon un gros dividende exceptionnel ressemble à un krach (fausse décote, fausse vente panique).
    dividends = []
    if "Dividends" in h.columns:
        for idx, v in h["Dividends"].items():
            if v and not math.isnan(v) and v > 0:
                d = idx.strftime("%Y-%m-%d")
                f = 1.0
                for sp in splits:
                    if sp["date"] > d:
                        f *= sp["ratio"]
                dividends.append({"date": d, "amount": round(float(v) * f, 6)})
    weekly = []
    if period != "2y" and rows:
        last_week = {}
        for r in rows:  # dernière clôture de chaque semaine (cours bruts publiés, comme « rows »)
            y, w, _ = date.fromisoformat(r[0]).isocalendar()
            last_week[(y, w)] = [r[0], r[4]]
        weekly = [last_week[k] for k in sorted(last_week)]
        cut = (date.fromisoformat(rows[-1][0]) - timedelta(days=DAILY_DAYS)).isoformat()
        rows = [r for r in rows if r[0] >= cut]
    return {"rows": rows, "splits": splits, "dividends": dividends, "currency": currency, "weekly": weekly}


def main():
    today = datetime.utcnow().date()
    latest = load(LATEST, None)
    if not latest:
        print("data/latest.json absent : aucun cours collecté")
        return 0
    isins, names, paid = set(), {}, {}
    prev_items = (load(OUT, {}) or {}).get("items") or {}
    carried_n = 0

    def num(v, loc=None):
        if isinstance(v, (int, float)):
            return float(v)
        v = str(v or "").replace("\u202f", "").replace(" ", "")
        if loc == "en":
            v = v.replace(",", "")
        elif "," in v and "." in v:
            v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
        else:
            v = v.replace(",", ".")
        try:
            return float(v)
        except ValueError:
            return None

    def note(isin, name, d, price):
        if name and isin not in names:
            names[isin] = name
        if price and price > 0 and d and (isin not in paid or d > paid[isin][0]):
            paid[isin] = (str(d)[:10], price)
    for t in latest.get("transactions", []):
        isin = str(t.get("isin") or "").upper()
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin) and str(t.get("instrument") or "").strip().lower() in ("action", "actions"):
            isins.add(isin)
            note(isin, t.get("company_name"), t.get("date") if str(t.get("date") or "") <= today.isoformat() else None, num(t.get("price")))
    # Déclarations hors France (FSMA, AFM) : mêmes besoins de cours
    eu = load(DATA / "insiders-eu.json", {}).get("records", {})
    share_words = {"share", "shares", "aandeel", "aandelen", "aktie", "aktien", "azioni", "acciones", "action", "actions", "ordinary shares", ""}
    for r in eu.values():
        isin = str(r.get("isin") or "").upper().replace(" ", "")
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin) and str(r.get("instrument") or "").strip().lower() in share_words:
            isins.add(isin)
            note(isin, r.get("issuer"), r.get("txDate") if str(r.get("txDate") or "") <= today.isoformat() else None, num(r.get("price"), r.get("numberLocale")))
    cache = load(TICKERS, {})
    manual = manual_map()
    exch = (load(DATA / "backup-isins.json", {}) or {}).get("isins") or {}  # listes officielles des bourses (veille)
    items, unresolved = {}, []
    by_exchange = 0
    print(f"Cours Yahoo : {len(isins)} émetteurs")
    for n, isin in enumerate(sorted(isins), 1):
        info = resolve(isin, cache, manual, today, names.get(isin), paid.get(isin))
        if not info:
            ex, h = try_exchange(isin, exch, paid.get(isin), today)
            if ex:  # introuvable chez Yahoo par ISIN ou par nom, mais coté (liste officielle de la bourse)
                cache[isin] = {"ticker": ex, "method": "liste officielle de la bourse", "resolvedAt": today.isoformat()}
                items[isin] = {"ticker": ex, "exchange": None, "name": names.get(isin), "currency": h["currency"], "rows": h["rows"], "splits": h["splits"], "dividends": h.get("dividends") or [], "weekly": h.get("weekly") or [], "method": "liste officielle de la bourse"}
                by_exchange += 1
                print(f"  [{n}/{len(isins)}] {isin} {ex} : {len(h['rows'])} séances (liste officielle de la bourse)")
                time.sleep(0.2)
                continue
            try:
                loc = local_by_name(isin, names.get(isin), cache, names)
            except Exception:  # secours : ne doit jamais arrêter la collecte des cours
                loc = None
            h = None
            if loc:
                try:
                    h = history(loc["ticker"], "5y")
                except Exception:
                    h = None
            if not (h and coherent(h, paid.get(isin))):
                unresolved.append(isin)
                continue
            items[isin] = {"ticker": loc["ticker"], "exchange": None, "name": loc.get("name"), "currency": h["currency"], "rows": h["rows"], "splits": h["splits"], "dividends": h.get("dividends") or [], "weekly": h.get("weekly") or [], "method": loc["method"]}
            print(f"  [{n}/{len(isins)}] {isin} {loc['ticker']} : {len(h['rows'])} séances ({loc['method']})")
            time.sleep(0.2)
            continue
        cand = home_candidate(isin, info["ticker"]) if info.get("method") != "correction vérifiée" else None
        c0 = cache.get(isin) or {}
        if cand and c0.get("homeTried") != cand:
            try:
                hh = history(cand, "5y")
            except Exception:
                hh = None
            if isinstance(cache.get(isin), dict):
                cache[isin]["homeTried"] = cand
            same = True
            if hh:  # contrôle anti-homonyme : même ordre de grandeur de cours (après conversion) que la place secondaire
                try:
                    ho = history(info["ticker"])
                    fx = {"EUR": 1, "GBp": 0.0117, "GBX": 0.0117, "GBP": 1.17, "PLN": 0.23, "ZAc": 0.00051, "ZAR": 0.051, "USD": 0.92, "CHF": 1.06, "SEK": 0.087, "DKK": 0.134, "NOK": 0.085}
                    a, b = fx.get(hh.get("currency") or "EUR"), fx.get((ho or {}).get("currency") or "EUR")
                    if ho and ho["rows"] and a and b:
                        r = (hh["rows"][-1][4] * a) / (ho["rows"][-1][4] * b)
                        same = 0.7 <= r <= 1.4
                except Exception:
                    pass
            if same and fresh_enough(hh, today):  # place d'origine trouvée : elle remplace durablement la place secondaire
                info = {"ticker": cand, "method": "cotation du pays d'origine", "exchange": None, "name": info.get("name")}
                cache[isin] = dict(info, resolvedAt=today.isoformat(), homeTried=cand)
                items[isin] = {"ticker": cand, "exchange": None, "name": info.get("name"), "currency": hh["currency"], "rows": hh["rows"], "splits": hh["splits"], "dividends": hh.get("dividends") or [], "weekly": hh.get("weekly") or [], "method": info["method"]}
                print(f"  [{n}/{len(isins)}] {isin} {cand} : {len(hh['rows'])} séances (cotation d'origine)")
                time.sleep(0.2)
                continue
        try:
            h = yahoo.call(lambda: history(info["ticker"], "5y"), tries=3, section="cours Euro Signal")
        except Exception as e:
            print(f"  [{n}] {isin} {info['ticker']} : erreur {str(e)[:80]}")
            h = None
        if h and frozen(h, today) and info.get("method") != "correction vérifiée":
            # cours figé chez Yahoo : la liste officielle de la bourse donne peut-être la cotation à jour (place d'origine, nouveau symbole)
            ex, h2 = try_exchange(isin, exch, paid.get(isin), today, current=info["ticker"])
            if ex:
                print(f"  [{n}] {isin} {info['ticker']} figé depuis le {h['rows'][-1][0]} : {ex} (liste officielle de la bourse)")
                info = {"ticker": ex, "method": "liste officielle de la bourse (cotation à jour)", "exchange": None, "name": info.get("name")}
                cache[isin] = dict(info, resolvedAt=today.isoformat())
                h = h2
                by_exchange += 1
        if not h:
            # Yahoo muet ce soir pour ce titre : cours de la veille s'ils datent de moins de 10 jours (fichier gardé par le cache GitHub)
            old = prev_items.get(isin)
            if old and old.get("rows") and old["rows"][-1][0] >= (today - timedelta(days=10)).isoformat():
                items[isin] = dict(old, stale=True)
                carried_n += 1
                continue
            unresolved.append(isin)
            continue
        items[isin] = {"ticker": info["ticker"], "exchange": info.get("exchange"), "name": info.get("name"), "currency": h["currency"], "rows": h["rows"], "splits": h["splits"], "dividends": h.get("dividends") or [], "weekly": h.get("weekly") or [], "method": info.get("method")}
        print(f"  [{n}/{len(isins)}] {isin} {info['ticker']} : {len(h['rows'])} séances")
        time.sleep(0.2)
    bench = None
    try:
        b = history(BENCH)
        if b:
            bench = {"ticker": BENCH, "rows": b["rows"]}
    except Exception as e:
        print("Indice de référence indisponible :", e)
    market = None
    try:
        m = history(MARKET)
        if m:
            market = {"ticker": MARKET, "rows": m["rows"]}
    except Exception as e:
        print("Indice européen indisponible :", e)
    if market is None and bench:
        market = bench  # repli : CAC 40
    # Taux de change (unités de devise pour 1 euro, dernière clôture) : convertit montants et liquidité des sociétés hors zone euro
    fx = {}
    for cur in ("SEK", "NOK", "DKK", "CHF", "GBP", "USD", "PLN", "CZK", "HUF", "ISK"):
        try:
            f = history("EUR" + cur + "=X")
            closes = [r[4] for r in (f or {}).get("rows", []) if r and r[4]]
            if closes and closes[-1] > 0:
                fx[cur] = closes[-1]
        except Exception:
            pass
    if "GBP" in fx:
        fx["GBp"] = fx["GBP"] * 100  # cotations londoniennes en pence
    print(f"Taux de change : {len(fx)} devises")
    OUT.write_text(json.dumps({"generated_at": datetime.utcnow().isoformat(), "items": items, "bench": bench, "market": market, "fx": fx, "unresolved": unresolved}), encoding="utf-8")
    TICKERS.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"Cours écrits : {len(items)} titres, {len(unresolved)} sans cours, {carried_n} repris de la veille, "
          f"{by_exchange} cotations trouvées grâce aux listes officielles des bourses")
    yahoo.carried("cours Euro Signal", carried_n)
    yahoo._stat("cours Euro Signal", requested=len(isins), received=len(items) - carried_n, missing=len(unresolved))
    yahoo.write_diag()
    return 0


if __name__ == "__main__":
    sys.exit(main())
