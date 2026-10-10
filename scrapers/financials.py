"""
Euro Signal — comptes annuels (4 derniers exercices) : compte de résultat, bilan, flux de trésorerie (Yahoo Finance).

Sert à l'« Analyse des comptes » (tendances sur 4 ans, F-score de Piotroski) des sociétés suivies.
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
SCHEMA = 2  # version des postes collectés : une société lue avec une version plus ancienne est relue en priorité
BUDGET_S = 20 * 60  # au plus 20 minutes par soir

# Lignes Yahoo (plusieurs libellés possibles selon les sociétés) → nos champs
INCOME = {"revenue": ["Total Revenue", "Operating Revenue"], "grossProfit": ["Gross Profit"], "operatingIncome": ["Operating Income", "Total Operating Income As Reported"],
          "ebit": ["EBIT"], "sga": ["Selling General And Administration", "Selling And Marketing Expense"], "depreciation": ["Reconciled Depreciation", "Depreciation And Amortization In Income Statement", "Depreciation Amortization Depletion"],
          "netIncome": ["Net Income Common Stockholders", "Net Income", "Net Income From Continuing Operation Net Minority Interest"],
          "ebitda": ["EBITDA", "Normalized EBITDA"], "interestExpense": ["Interest Expense", "Interest Expense Non Operating"]}
BALANCE = {"totalAssets": ["Total Assets"], "currentAssets": ["Current Assets"], "currentLiabilities": ["Current Liabilities"],
           "totalDebt": ["Total Debt"], "longTermDebt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
           "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], "equity": ["Stockholders Equity", "Common Stock Equity"],
           "shares": ["Ordinary Shares Number", "Share Issued"],
           # Altman (Z'') et Beneish (M-score)
           "retainedEarnings": ["Retained Earnings"], "totalLiabilities": ["Total Liabilities Net Minority Interest", "Total Liabilities"],
           "receivables": ["Accounts Receivable", "Receivables", "Gross Accounts Receivable"], "ppe": ["Net PPE", "Net Property Plant And Equipment"]}
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


def statements(ticker):
    t = yf.Ticker(ticker)
    years = {}
    table(t.income_stmt, INCOME, years)
    table(t.balance_sheet, BALANCE, years)
    table(t.cashflow, CASH, years)
    rows = [y for y in sorted(years.values(), key=lambda y: y["date"]) if len(y) > 3][-5:]
    currency = None
    try:
        currency = (t.info or {}).get("financialCurrency")
    except Exception:
        pass
    return {"years": rows, "currency": currency}


def load(path, default):
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def main():
    t0 = time.time()
    today = datetime.now(timezone.utc).date()
    prices = load(DATA / "prices.json", {}).get("items", {})
    pairs = {isin: p.get("ticker") for isin, p in prices.items() if isinstance(p, dict) and p.get("ticker")}
    if not pairs:
        print("Comptes : pas de liste de titres (cours absents), rien à faire")
        return 0
    cache = load(OUT, {})
    items = cache.get("items") if isinstance(cache.get("items"), dict) else {}
    # Priorité : sociétés avec un achat de dirigeant dans le tableau de bord, puis les autres
    dash = load(DATA / "euro-signal.json", {})
    buyers = {i for i, l in (dash.get("tx") or {}).items() if any(isinstance(t, dict) and t.get("type") == "achat" for t in (l or []))}
    order = sorted(pairs, key=lambda i: (i not in buyers, (items.get(i) or {}).get("schema", 1) >= SCHEMA, i))
    fresh_before = (today - timedelta(days=REFRESH_DAYS)).isoformat()
    done = failed = 0
    for isin in order:
        old = items.get(isin) or {}
        if old.get("asOf", "") > fresh_before and old.get("ticker") == pairs[isin] and old.get("schema", 1) >= SCHEMA:
            continue
        if time.time() - t0 > BUDGET_S:
            break
        try:
            st = statements(pairs[isin])
            if st["years"]:
                items[isin] = {"ticker": pairs[isin], "asOf": today.isoformat(), "schema": SCHEMA, **st}
                done += 1
            else:
                items[isin] = {"ticker": pairs[isin], "asOf": today.isoformat(), "schema": SCHEMA, "years": [], "currency": None}
                failed += 1
        except Exception:
            failed += 1
        time.sleep(0.3)
    items = {i: v for i, v in items.items() if i in pairs}  # titres disparus de la liste : retirés
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pending = sum(1 for i in pairs if (items.get(i) or {}).get("asOf", "") <= fresh_before or (items.get(i) or {}).get("schema", 1) < SCHEMA)
    print(f"Comptes annuels : {done} société(s) mises à jour, {failed} sans données, {pending} à compléter les soirs suivants ; {sum(1 for v in items.values() if v.get('years'))} disponibles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
