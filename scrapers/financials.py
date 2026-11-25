"""
Euro Signal — comptes annuels (4 derniers exercices) : compte de résultat, bilan, flux de trésorerie (Yahoo Finance), et depuis le
25/11/2026 les 6 derniers trimestres ou semestres quand Yahoo les donne (« quarters »).

Sert à l'« Analyse des comptes » (tendances sur 4 ans, F-score de Piotroski) des sociétés suivies, et aux exclusions
et au départage du classement tendance + comptes pour les sociétés liquides du catalogue (clé « @TICKER »). Les trimestres ne
servent qu'à la lecture des comptes par l'IA (scrapers/comptes_ia.py) : aucune règle du classement ne les utilise.
Chaque société est relue au plus tous les 30 jours (cache dans data/financials.json, conservé d'un soir à l'autre), en commençant
par celles qui viennent de publier leurs résultats (relues 3 jours après, puis chaque semaine pendant 5 semaines tant que Yahoo n'a
pas les nouveaux comptes) et celles où un dirigeant a acheté récemment. « newAt » : date où une période plus récente que toutes
celles déjà connues est apparue (une nouvelle publication, pas un premier relevé des trimestres) ; elle déclenche les emails de la
lecture des comptes. Durée plafonnée : le reste est complété les soirs suivants. Une donnée absente reste absente (jamais devinée).
"""
import json
import math
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "financials.json"
REFRESH_DAYS = 30
RETRY_EMPTY_DAYS = 7  # société sans comptes chez Yahoo : nouvel essai une semaine plus tard
SCHEMA = 4  # version des postes collectés : une société lue avec une version plus ancienne est relue en priorité (3 : écarts d'acquisition et incorporels ; 4 : trimestres)
QKEEP = 6  # trimestres ou semestres gardés : le dernier se compare au même trimestre un an plus tôt
Q_RETRY_DAYS = 90  # société sans trimestres chez Yahoo (Paris, Bruxelles, Amsterdam, Dublin le plus souvent) : nouvel essai tous les 3 mois
POST_FIRST, POST_EVERY, POST_DAYS = 3, 7, 35  # après des résultats : relue 3 jours plus tard, puis chaque semaine pendant 5 semaines
NEW_MAX_AGE = 130  # période close depuis plus longtemps : comptes anciens apparus chez Yahoo, pas une nouvelle publication
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
# postes gardés pour les trimestres (lecture des comptes) : moins que pour les exercices, le fichier reste léger
Q_FIELDS = ("revenue", "grossProfit", "operatingIncome", "ebit", "netIncome", "ebitda", "interestExpense", "totalAssets", "currentAssets",
            "currentLiabilities", "totalDebt", "cash", "equity", "shares", "cfo", "capex", "fcf")


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


def quarters_of(ticker):
    """Trimestres (ou semestres, selon la société) des 18 derniers mois : compte de résultat, bilan, flux de trésorerie. Une période
    sans au moins deux postes est ignorée. Liste vide : Yahoo n'en a pas pour cette société."""
    t = yf.Ticker(ticker)
    qs = {}
    table(t.quarterly_income_stmt, INCOME, qs)
    table(t.quarterly_balance_sheet, BALANCE, qs)
    table(t.quarterly_cashflow, CASH, qs)
    rows = [{k: q[k] for k in ("date",) + Q_FIELDS if k in q} for q in sorted(qs.values(), key=lambda q: q["date"])]
    return [q for q in rows if len(q) > 2][-QKEEP:]


def periods(v):
    """Dates de fin des exercices et des trimestres connus d'une société."""
    v = v if isinstance(v, dict) else {}
    return ({str(y.get("date")) for y in v.get("years") or [] if isinstance(y, dict) and y.get("date")}
            | {str(q.get("date")) for q in v.get("quarters") or [] if isinstance(q, dict) and q.get("date")})


def new_period(old, new, today):
    """Fin de la période apparue ce soir quand c'est une nouvelle publication : plus récente que tout ce qui était connu, de même
    nature (un premier relevé des trimestres n'en est pas une : seuls comptent les exercices tant que la société n'avait pas de
    trimestres) et close depuis moins de NEW_MAX_AGE jours. Sinon None."""
    if not isinstance(old, dict) or old.get("schema", 1) < 4 or old.get("ticker") != new.get("ticker"):
        return None
    known = periods(old)
    if not known:
        return None
    top = max(known)
    cand = [str(y.get("date")) for y in new.get("years") or [] if str(y.get("date")) > top]
    if old.get("quarters"):
        cand += [str(q.get("date")) for q in new.get("quarters") or [] if str(q.get("date")) > top]
    if not cand:
        return None
    d = max(cand)
    try:
        return d if (today - date.fromisoformat(d)).days <= NEW_MAX_AGE else None
    except ValueError:
        return None


def results_dates(pairs, today):
    """Dernière publication de résultats connue ce soir (date passée, depuis moins de POST_DAYS + 5 jours), par clé des comptes :
    relevé des résultats des sociétés suivies (data/events.json, étape 4 du calcul du soir) et relevé hebdomadaire du catalogue
    (data/sectors/estimates.json : dates passées et dates des surprises de résultats, par symbole)."""
    ts, lo = today.isoformat(), (today - timedelta(days=POST_DAYS + 5)).isoformat()
    ev = load(DATA / "events.json", {}).get("items")
    ev = ev if isinstance(ev, dict) else {}
    est = load(DATA / "sectors" / "estimates.json", {})
    out = {}
    for k, tk in pairs.items():
        ds = []
        e = ev.get(k)
        if isinstance(e, dict):
            ds += [x.get("date") for x in e.get("earnings") or [] if isinstance(x, dict)]
        s = est.get(tk)
        if isinstance(s, dict):
            ds += list(s.get("past") or [])
            ds += [x[0] for x in s.get("surprises") or [] if isinstance(x, (list, tuple)) and x]
        ds = [d for d in ds if isinstance(d, str) and len(d) == 10 and lo <= d <= ts and valid(d)]
        if ds:
            out[k] = max(ds)
    return out


def valid(d):
    try:
        date.fromisoformat(d)
        return True
    except ValueError:
        return False


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
    res = results_dates(pairs, today)

    def post_due(i):
        """Résultats publiés il y a 3 à 35 jours et nouveaux comptes pas encore vus depuis : relue 3 jours après, puis chaque semaine."""
        v, d = items.get(i) or {}, res.get(i)
        if not d or not v.get("years") or v.get("ticker") != pairs[i] or str(v.get("newAt") or "") >= d:
            return False
        age = (today - date.fromisoformat(d)).days
        a = str(v.get("asOf") or "")
        return POST_FIRST <= age <= POST_DAYS and (a < (date.fromisoformat(d) + timedelta(days=POST_FIRST)).isoformat() or a <= week_ago)
    post = {i for i in pairs if post_due(i)}
    order = sorted(pairs, key=lambda i: ((items.get(i) or {}).get("triedAt", "") > week_ago, i not in post, i not in buyers,
                                         (items.get(i) or {}).get("schema", 1) >= SCHEMA, i))
    q_before = (today - timedelta(days=Q_RETRY_DAYS)).isoformat()
    fresh_before = (today - timedelta(days=REFRESH_DAYS)).isoformat()
    retry_before = (today - timedelta(days=RETRY_EMPTY_DAYS)).isoformat()
    done = failed = kept = streak = fresh_pub = 0
    streak_new = []  # sociétés notées « sans comptes » pendant la série de réponses vides en cours
    # titres absents de la liste du soir : gardés tant que leurs comptes ont moins de REFRESH_DAYS + 30 jours (liste incomplète un soir :
    # cours absents, catalogue en panne), retirés ensuite (sortis de la cote ou du périmètre). Jusqu'au 04/11/2026, retirés dès le
    # premier soir, et le garde-fou ne comptait que la liste du soir : des centaines de comptes effacés puis relus pendant des semaines
    keep_after = (today - timedelta(days=REFRESH_DAYS + 30)).isoformat()

    def keep(i, v):
        return i in pairs or (isinstance(v, dict) and str(v.get("asOf") or "") >= keep_after)
    avail_before = sum(1 for i, v in items.items() if isinstance(v, dict) and v.get("years") and keep(i, v))
    stopped = False
    for isin in order:
        old = items.get(isin) or {}
        if isin not in post and old.get("asOf", "") > (fresh_before if old.get("years") else retry_before) and old.get("ticker") == pairs[isin] and old.get("schema", 1) >= SCHEMA:
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
            same = old.get("ticker") == pairs[isin]
            # trimestres : relus sauf si Yahoo n'en avait pas il y a moins de 3 mois ; erreur ce soir : ceux déjà connus sont gardés
            if not (same and old.get("quarters") == [] and str(old.get("qAt") or "") > q_before):
                try:
                    st["quarters"], st["qAt"] = quarters_of(pairs[isin]), today.isoformat()
                except Exception:
                    pass
            if "quarters" not in st and same and isinstance(old.get("quarters"), list):
                st["quarters"], st["qAt"] = old["quarters"], old.get("qAt")
            rec = {"ticker": pairs[isin], "asOf": today.isoformat(), "schema": SCHEMA, **st}
            nw = new_period(old, rec, today)
            if nw:  # nouvelle publication : lue par l'IA et signalée par email (scrapers/comptes_ia.py)
                rec["newAt"], rec["newPer"] = today.isoformat(), nw
                fresh_pub += 1
            elif same and old.get("newAt"):
                rec["newAt"], rec["newPer"] = old["newAt"], old.get("newPer")
            items[isin] = rec
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
    items = {i: v for i, v in items.items() if keep(i, v)}
    avail = sum(1 for v in items.values() if v.get("years"))
    if avail < avail_before * 0.8:  # garde-fou : jamais de fichier qui perd plus de 20 % des comptes disponibles
        print(f"Comptes annuels : {avail} disponibles contre {avail_before} avant, fichier précédent conservé")
        return 0
    tmp = OUT.with_name(OUT.name + ".tmp")  # écriture atomique : une étape coupée par son délai ne laisse pas un fichier à moitié écrit
    tmp.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    if stopped:
        print(f"Comptes annuels : Yahoo ne renvoie plus de comptes ({STREAK_STOP} réponses vides de suite), arrêt pour ce soir")
    pending = sum(1 for i in pairs if (items.get(i) or {}).get("asOf", "") <= fresh_before or (items.get(i) or {}).get("schema", 1) < SCHEMA)
    print(f"Comptes annuels : {done} société(s) mises à jour, {failed} sans données (dont {kept} anciens comptes conservés), {pending} à compléter les soirs suivants ; {sum(1 for v in items.values() if v.get('years'))} disponibles")
    print(f"Trimestres : {sum(1 for v in items.values() if v.get('quarters'))} sociétés ; résultats récents à relire : {len(post)} ; "
          f"nouveaux comptes vus ce soir : {fresh_pub}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
