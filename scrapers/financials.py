"""
Euro Signal — comptes annuels (4 derniers exercices) : compte de résultat, bilan, flux de trésorerie (Yahoo Finance).

Sert à l'« Analyse des comptes » (tendances sur 4 ans, F-score de Piotroski) des sociétés suivies, et aux exclusions
et au départage du classement tendance + comptes pour les sociétés liquides du catalogue (clé « @TICKER »).
Les comptes ne changent qu'une fois par an : chaque société est relue au plus tous les 30 jours (cache dans
data/financials.json, conservé d'un soir à l'autre), en commençant par celles où un dirigeant a acheté récemment.
Durée plafonnée : le reste est complété les soirs suivants. Une donnée absente reste absente (jamais devinée).
"""
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "financials.json"
REFRESH_DAYS = 30
RETRY_EMPTY_DAYS = 7  # société sans comptes chez Yahoo : nouvel essai une semaine plus tard
SCHEMA = 3  # version des postes collectés : une société lue avec une version plus ancienne est relue en priorité (3 : écarts d'acquisition et incorporels)
CAT_MIN_TURNOVER_EUR = 1e6  # même seuil de liquidité que le classement
BUDGET_S = 18 * 60  # au plus 18 minutes par soir (l'étape est coupée à 20)
STREAK_RESET, STREAK_STOP = 15, 40  # réponses vides de suite : nouveau jeton Yahoo, puis arrêt

# Lignes Yahoo (plusieurs libellés possibles selon les sociétés) → nos champs
INCOME = {"revenue": ["Total Revenue", "Operating Revenue"], "grossProfit": ["Gross Profit"], "operatingIncome": ["Operating Income", "Total Operating Income As Reported"],
          "ebit": ["EBIT"], "sga": ["Selling General And Administration", "Selling And Marketing Expense"], "depreciation": ["Reconciled Depreciation", "Depreciation And Amortization In Income Statement", "Depreciation Amortization Depletion"],
          "netIncome": ["Net Income Common Stockholders", "Net Income", "Net Income From Continuing Operation Net Minority Interest"],
          "ebitda": ["EBITDA", "Normalized EBITDA"], "interestExpense": ["Interest Expense", "Interest Expense Non Operating"]}
BALANCE = {"totalAssets": ["Total Assets"], "currentAssets": ["Current Assets"], "currentLiabilities": ["Current Liabilities"],
           "totalDebt": ["Total Debt"], "longTermDebt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
           "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], "equity": ["Common Stock Equity", "Stockholders Equity"],  # part du groupe revenant aux actions ordinaires (hors actions de préférence)
           "shares": ["Ordinary Shares Number", "Share Issued"],
           # Altman (Z'') et Beneish (M-score)
           "retainedEarnings": ["Retained Earnings"], "totalLiabilities": ["Total Liabilities Net Minority Interest", "Total Liabilities"],
           "receivables": ["Accounts Receivable", "Receivables", "Gross Accounts Receivable"], "ppe": ["Net PPE", "Net Property Plant And Equipment"],
           # valeur comptable tangible : capitaux propres hors écarts d'acquisition (goodwill) et autres incorporels
           "intangibles": ["Goodwill And Other Intangible Assets"], "goodwill": ["Goodwill"], "otherIntangibles": ["Other Intangible Assets"]}
CASH = {"cfo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], "capex": ["Capital Expenditure"], "fcf": ["Free Cash Flow"]}


def num(v):
    try:
        x = float(v)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def table(df, spec, years):
    if df is None or getattr(df, "empty", True):
        return
    for col in df.columns:
        d = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)[:10]
        y = years.setdefault(d, {"date": d})
        for key, names in spec.items():
            if y.get(key) is not None:
                continue
            for n in names:
                if n in df.index:
                    v = num(df.loc[n, col])
                    if v is not None:
                        y[key] = v
                        break


KNOWN_CUR = {}  # symbole → devise des comptes déjà connue (fiches Yahoo du catalogue) : évite t.info, 3 requêtes sur 6 par société


def known_currencies():
    """Devise des comptes d'après les fiches Yahoo déjà lues par le catalogue (data/sectors/info_cache.json)."""
    out = {}
    for sym, inf in (load(DATA / "sectors" / "info_cache.json", {}) or {}).items():
        c = inf.get("financialCurrency") if isinstance(inf, dict) else None
        if isinstance(c, str) and 2 <= len(c) <= 4:
            out[sym] = c
    return out


def statements(ticker):
    t = yf.Ticker(ticker)
    years = {}
    table(t.income_stmt, INCOME, years)
    table(t.balance_sheet, BALANCE, years)
    table(t.cashflow, CASH, years)
    for y in years.values():
        gw, oi = y.pop("goodwill", None), y.pop("otherIntangibles", None)
        if y.get("intangibles") is None and (gw is not None or oi is not None):
            y["intangibles"] = (gw or 0) + (oi or 0)
    rows = [y for y in sorted(years.values(), key=lambda y: y["date"]) if len(y) > 3][-5:]
    currency = KNOWN_CUR.get(ticker) if rows else None
    if rows and not currency:
        try:
            currency = (t.info or {}).get("financialCurrency")
        except Exception:
            pass
    return {"years": rows, "currency": currency}


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


def load(path, default):
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def catalogue_pairs(known, min_turnover=CAT_MIN_TURNOVER_EUR):
    """Sociétés liquides du catalogue (classement tendance + comptes) sans dossier Euro Signal : clé « @TICKER »."""
    out = {}
    for f in sorted((DATA / "societes").glob("*.json")):
        items = load(f, {}).get("items")
        for sym, x in (items if isinstance(items, dict) else {}).items():
            if not isinstance(x, dict) or sym in known:  # hors PEA compris (Suisse, Royaume-Uni, foncières) : classés aussi
                continue
            if (x.get("turnoverEur") or 0) >= min_turnover:
                out["@" + sym] = sym
    return out


def main():
    t0 = time.time()
    today = datetime.now(timezone.utc).date()
    KNOWN_CUR.update(known_currencies())
    prices = load(DATA / "prices.json", {}).get("items", {})
    pairs = {isin: p.get("ticker") for isin, p in prices.items() if isinstance(p, dict) and p.get("ticker")}
    pairs.update(catalogue_pairs(set(pairs.values())))
    if not pairs:
        print("Comptes : pas de liste de titres (cours absents), rien à faire")
        return 0
    cache = load(OUT, {})
    items = cache.get("items") if isinstance(cache.get("items"), dict) else {}
    # Priorité : sociétés avec un achat de dirigeant dans le tableau de bord, puis les autres
    dash = load(DATA / "euro-signal.json", {})
    buyers = {i for i, l in (dash.get("tx") or {}).items() if any(isinstance(t, dict) and t.get("type") == "achat" for t in (l or []))}
    week_ago = (today - timedelta(days=7)).isoformat()
    order = sorted(pairs, key=lambda i: ((items.get(i) or {}).get("triedAt", "") > week_ago, i not in buyers, (items.get(i) or {}).get("schema", 1) >= SCHEMA, i))
    fresh_before = (today - timedelta(days=REFRESH_DAYS)).isoformat()
    retry_before = (today - timedelta(days=RETRY_EMPTY_DAYS)).isoformat()
    done = failed = kept = streak = 0
    streak_new = []  # sociétés notées « sans comptes » pendant la série de réponses vides en cours
    # comptes déjà disponibles pour les titres de la liste du soir (une société sortie de la liste n'est pas une perte de données)
    avail_before = sum(1 for i, v in items.items() if v.get("years") and i in pairs)
    stopped = False
    for isin in order:
        old = items.get(isin) or {}
        if old.get("asOf", "") > (fresh_before if old.get("years") else retry_before) and old.get("ticker") == pairs[isin] and old.get("schema", 1) >= SCHEMA:
            continue
        if time.time() - t0 > BUDGET_S:
            break
        # Yahoo qui répond vide à la suite (jeton refusé, blocage passager) : nouveau jeton, puis arrêt pour ce soir
        if streak == STREAK_RESET:
            reset_yahoo_session()
            time.sleep(5)
        if streak >= STREAK_STOP:
            stopped = True
            break
        try:
            st = statements(pairs[isin])
        except Exception:
            st = {"years": []}
        if st["years"]:
            items[isin] = {"ticker": pairs[isin], "asOf": today.isoformat(), "schema": SCHEMA, **st}
            done += 1
            streak = 0
            streak_new = []
        else:
            failed += 1
            streak += 1
            # réponse vide : les comptes déjà connus sont conservés (jamais effacés par une panne de Yahoo)
            if old.get("years") and old.get("ticker") == pairs[isin]:
                old["triedAt"] = today.isoformat()  # relue en dernier pendant une semaine
                kept += 1
            else:
                if isin not in items:
                    streak_new.append(isin)
                items[isin] = {"ticker": pairs[isin], "asOf": today.isoformat(), "schema": SCHEMA, "years": [], "currency": None}
        time.sleep(0.3)
    if stopped:  # Yahoo bloqué : les sociétés de la série vide ne sont pas notées « sans comptes », elles seront relues dès le soir suivant
        for k in streak_new:
            items.pop(k, None)
    items = {i: v for i, v in items.items() if i in pairs}  # titres disparus de la liste : retirés
    avail = sum(1 for v in items.values() if v.get("years"))
    if avail < avail_before * 0.8:  # garde-fou : jamais de fichier qui perd plus de 20 % des comptes disponibles
        print(f"Comptes annuels : {avail} disponibles contre {avail_before} avant, fichier précédent conservé")
        return 0
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if stopped:
        print(f"Comptes annuels : Yahoo ne renvoie plus de comptes ({STREAK_STOP} réponses vides de suite), arrêt pour ce soir")
    pending = sum(1 for i in pairs if (items.get(i) or {}).get("asOf", "") <= fresh_before or (items.get(i) or {}).get("schema", 1) < SCHEMA)
    print(f"Comptes annuels : {done} société(s) mises à jour, {failed} sans données (dont {kept} anciens comptes conservés), {pending} à compléter les soirs suivants ; {sum(1 for v in items.values() if v.get('years'))} disponibles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
