"""
Euro Signal — historique long des déclarations de dirigeants (France, Suède), exécuté par GitHub Actions
(workflow « history.yml », séparé de la mise à jour du soir).

Sources publiques officielles, gratuites, sans licence de tiers :
  France : base BDIF de l'AMF, « Déclarations des dirigeants » (API publique du site, un PDF par déclaration).
           La base BDIF actuelle commence en février 2021.
  Suède  : registre Insynshandel de Finansinspektionen (export CSV officiel), depuis juillet 2016 (règlement MAR).

Rattrapage progressif : chaque exécution avance dans le temps pendant au plus --minutes, enregistre où elle
s'est arrêtée (data/history/state.json) et reprend au même endroit la fois suivante. Une fois à jour, elle
relit seulement les nouvelles déclarations.

Puis, pour chaque achat (historique + archive du tableau de bord), résultat à 20, 60 et 120 séances après la
publication, en euros, comparé au STOXX Europe 600 sur les mêmes dates. Cours de clôture ajustés des divisions
seulement (pas des dividendes), comme l'indice : comparaison prix contre prix.

Fichiers (compressés, lus par euro_signal/build.mjs) :
  data/history/amf.json.gz       déclarations France (format commun des collecteurs)
  data/history/fi.json.gz        déclarations Suède (actions uniquement)
  data/history/outcomes.json.gz  « ISIN|date de publication » -> [entrée, r20, r60, r120, b20, b60, b120, sortie120]
  data/history/tickers.json      correspondance ISIN -> ticker Yahoo propre à l'historique
  data/history/state.json        curseurs de reprise et compteurs (aucune donnée personnelle de l'utilisateur)
"""
import argparse
import csv
import gzip
import io
import json
import math
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from europe_insiders import FI_URL, UA, decode, fi_parse, iso_date, norm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HIST = DATA / "history"
STATE = HIST / "state.json"
FILES = {"AMF": HIST / "amf.json.gz", "FI": HIST / "fi.json.gz"}
OUTCOMES = HIST / "outcomes.json.gz"
HTICKERS = HIST / "tickers.json"

FI_START = date(2016, 7, 1)
FR_START = date(2021, 2, 1)
BDIF_LIST = "https://bdif.amf-france.org/back/api/v1/informations"
BDIF_DOC = "https://bdif.amf-france.org/back/api/v1/documents/"
BENCH = "^STOXX"
HORIZONS = (20, 60, 120)
FX_CODES = ("SEK", "NOK", "DKK", "GBP", "USD", "CHF", "PLN")


# --------------------------------------------------------------------------- utilitaires
def load_json(path, default):
    try:
        if str(path).endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if str(path).endswith(".gz"):
        # mtime=0 : fichier identique octet pour octet si le contenu ne change pas (pas de commit inutile)
        with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=9) as f:
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    else:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def get(url, params=None, timeout=90, tries=(0, 8, 25)):
    last = None
    for wait in tries:
        if wait:
            time.sleep(wait)
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200 and r.content:
                return r
            last = RuntimeError(f"HTTP {r.status_code}")
            if r.status_code in (400, 404):
                break
        except requests.RequestException as e:
            last = e
    raise last


class Clock:
    def __init__(self, minutes):
        self.end = time.time() + minutes * 60

    def left(self):
        return self.end - time.time()


# --------------------------------------------------------------------------- France : PDF de l'AMF
def strip_accents_map(s):
    """Texte en majuscules sans accents + table de correspondance vers les positions du texte d'origine."""
    out, idx = [], []
    for i, ch in enumerate(s):
        for c in unicodedata.normalize("NFD", ch):
            if unicodedata.category(c) != "Mn":
                out.append(c.upper())
                idx.append(i)
    return "".join(out), idx


# Libellés du formulaire de déclaration AMF (sans accents, majuscules) ; la valeur va jusqu'au libellé suivant
FR_LABELS = [
    ("who", r"NOM\s*/\s*FONCTION DE LA PERSONNE EXERCANT DES RESPONSABILITES DIRIGEANTES OU DE LA PERSONNE ETROITEMENT LIEE\s*:"),
    ("notif", r"NOTIFICATION INITIALE\s*/\s*MODIFICATION\s*:"),
    ("issuerBlock", r"COORDONNEES DE L.EMETTEUR"),
    ("issuer", r"\bNOM\s*:"),
    ("lei", r"\bLEI\s*:"),
    ("detail", r"DETAIL DE LA TRANSACTION"),
    ("instrument", r"DESCRIPTION DE L.INSTRUMENT FINANCIER\s*:"),
    ("isin", r"CODE D.IDENTIFICATION DE L.INSTRUMENT FINANCIER\s*:"),
    ("nature", r"NATURE DE LA TRANSACTION\s*:"),
    ("txDate", r"DATE DE LA TRANSACTION\s*:"),
    ("place", r"LIEU DE LA TRANSACTION\s*:"),
    ("unitPrice", r"PRIX UNITAIRE\s*:"),
    ("unitVolume", r"(?<!AGREGEES\s)VOLUME\s*:"),
    ("aggregated", r"INFORMATIONS AGREGEES"),
    ("aggPrice", r"\bPRIX\s*:"),
    ("options", r"TRANSACTION LIEE A L.EXERCICE DE PROGRAMME DE STOCK[- ]OPTIONS\s*:"),
    ("received", r"DATE DE RECEPTION DE LA NOTIFICATION\s*:"),
    ("comment", r"COMMENTAIRES?\s*:"),
]
_SP = r"\s+"
FR_LABEL_RE = re.compile("|".join("(?P<%s>%s)" % (k, p.replace(" ", _SP)) for k, p in FR_LABELS))


def fr_tokens(text):
    up, idx = strip_accents_map(text)
    toks = []
    for m in FR_LABEL_RE.finditer(up):
        toks.append((m.lastgroup, m.start(), m.end()))
    out = []
    for i, (k, a, b) in enumerate(toks):
        nxt = toks[i + 1][1] if i + 1 < len(toks) else len(up)
        oa = idx[b] if b < len(idx) else len(text)
        ob = idx[nxt] if nxt < len(idx) else len(text)
        val = re.sub(r"\s+", " ", text[oa:ob]).strip(" :;-–")
        out.append((k, val))
    return out


NUM_RE = re.compile(r"-?\d[\d\s  .,]*\d|\d")


def first_number(s):
    m = NUM_RE.search(s or "")
    return m.group(0).replace(" ", "").replace(" ", "").replace(" ", "") if m else None


def fr_currency(s):
    s = (s or "").upper()
    if "EUR" in s or "€" in s:
        return "EUR"
    m = re.search(r"\b([A-Z]{3})\b", s)
    return m.group(1) if m and m.group(1) not in ("UTC", "MTV", "XPAR") else None


def fr_parse_pdf_text(text, meta):
    """Texte d'une déclaration AMF -> liste d'enregistrements (une ligne par transaction déclarée)."""
    toks = fr_tokens(text)
    who = next((v for k, v in toks if k == "who"), "")
    issuer = None
    seen_block = False
    for k, v in toks:
        if k == "issuerBlock":
            seen_block = True
        elif k == "issuer" and seen_block and not issuer:
            issuer = v
    person, role = who, None
    if "," in who:
        person, role = who.split(",", 1)
        person, role = person.strip(), role.strip()
    # « X, personne morale liée à Y, Président » : la fonction est celle du dirigeant Y (le moteur détecte « liée à »)
    txs, cur = [], None
    in_agg = False
    for k, v in toks:
        if k == "detail":
            if cur:
                txs.append(cur)
            cur, in_agg = {}, False
            continue
        if cur is None:
            continue
        if k == "aggregated":
            in_agg = True
        elif k in ("instrument", "isin", "nature", "txDate", "place", "options"):
            cur.setdefault(k, v)
        elif k == "unitPrice" and not in_agg:
            cur.setdefault("unitPrice", v)
            cur["lines"] = cur.get("lines", 0) + 1
        elif k == "unitVolume":
            cur.setdefault("aggVolume" if in_agg else "unitVolume", v)
        elif k == "aggPrice" and in_agg:
            cur.setdefault("aggPrice", v)
    if cur:
        txs.append(cur)
    recs = []
    for i, t in enumerate(txs):
        ins = (t.get("instrument") or "").strip()
        nins = norm(ins)
        if "action" in nins and not re.search(r"droit|bon |bons|obligation|option|warrant|certificat|convertible", nins):
            ins = "Action"
        isin = (re.search(r"[A-Z]{2}[A-Z0-9]{9}\d", (t.get("isin") or "").upper().replace(" ", "")) or [None])[0]
        nature = (t.get("nature") or "").strip()
        if norm(t.get("options") or "").startswith("oui"):
            nature += " (stock options)"
        price_s = t.get("aggPrice") or t.get("unitPrice")
        vol_s = t.get("aggVolume") or t.get("unitVolume")
        tx = iso_date(re.sub(r"\s*;.*$", "", t.get("txDate") or "")) or iso_date(t.get("txDate"))
        recs.append({
            "registry": "AMF", "country": "FR", "id": f"{meta['numero']}-{i + 1}" if len(txs) > 1 else meta["numero"],
            "published": meta.get("published"), "issuer": issuer or meta.get("issuer"), "person": person or None, "role": role,
            "isin": isin, "instrument": ins or None, "nature": nature or None, "txDate": tx, "currency": fr_currency(price_s),
            "quantity": first_number(vol_s), "price": first_number(price_s), "url": meta.get("url"), "numberLocale": "auto",
            "linkedTo": None,
        })
    return recs


def pdf_text(content):
    from pypdf import PdfReader  # dépendance installée par le workflow d'historique uniquement
    reader = PdfReader(io.BytesIO(content))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def bdif_list(d0, d1):
    """Déclarations de dirigeants publiées entre d0 et d1 (dates d'information), toutes pages."""
    out, frm = [], 0
    while True:
        r = get(BDIF_LIST, {"TypesInformation": "DD", "From": frm, "Size": 100, "DateDebut": d0.isoformat(), "DateFin": d1.isoformat()})
        body = r.json()
        res = body.get("result") or []
        for x in res:
            docs = [d for d in (x.get("documents") or []) if d.get("path") and str(d.get("path")).lower().endswith(".pdf")]
            soc = next((s.get("raisonSociale") for s in (x.get("societes") or []) if s.get("role") == "SocieteConcernee"), None) or \
                next((s.get("raisonSociale") for s in (x.get("societes") or [])), None)
            if docs and x.get("numero"):
                out.append({"numero": x["numero"], "published": str(x.get("datePublication") or x.get("dateInformation") or "")[:10],
                            "issuer": soc, "url": BDIF_DOC + docs[0]["path"]})
        total = body.get("total") or 0
        frm += len(res)
        if not res or frm >= total:
            break
        time.sleep(0.4)
    return out


def month_end(d):
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def collect_fr(st, clock, recs):
    s = st.setdefault("AMF", {})
    cur = date.fromisoformat(s.get("cursor") or FR_START.isoformat())
    done = set(s.get("doneInMonth") or [])
    stop_at = date.today() - timedelta(days=1)
    pdf_fail = s.get("pdfFail", 0)
    by_id = {r["id"]: r for r in recs}
    added = 0
    while cur <= stop_at and clock.left() > 120:
        end = min(month_end(cur), stop_at)
        try:
            items = bdif_list(cur, end)
        except Exception as e:
            print(f"AMF : liste {cur} inaccessible ({e}) : reprise au prochain passage")
            s["lastError"] = f"{cur}: {str(e)[:120]}"
            break
        complete = True
        for it in items:
            if it["numero"] in done:
                continue
            if clock.left() < 120:
                complete = False
                break
            try:
                txt = pdf_text(get(it["url"], timeout=60).content)
                rows = fr_parse_pdf_text(txt, it)
                if not rows:
                    pdf_fail += 1
                for r in rows:
                    by_id[r["id"]] = r
                    added += 1
            except Exception as e:
                pdf_fail += 1
                if pdf_fail % 50 == 1:
                    print(f"  AMF : PDF {it['numero']} illisible ({type(e).__name__})")
            done.add(it["numero"])
            time.sleep(0.25)
        if not complete:
            s["doneInMonth"] = sorted(done)
            break
        print(f"AMF : {cur.strftime('%Y-%m')} : {len(items)} déclarations")
        # mois terminé ; le mois en cours reste ouvert (nouvelles déclarations) et sera relu au prochain passage
        if end >= stop_at:
            s["doneInMonth"] = sorted(done)
            break
        cur = end + timedelta(days=1)
        done = set()
        s["doneInMonth"] = []
        s["cursor"] = cur.isoformat()
    s.update({"pdfFail": pdf_fail, "records": len(by_id), "lastRun": date.today().isoformat(),
              "upToDate": cur >= stop_at.replace(day=1)})
    print(f"AMF : {added} lignes ajoutées, {len(by_id)} au total, {pdf_fail} PDF non lus depuis le début")
    return list(by_id.values())


# --------------------------------------------------------------------------- Suède : export Finansinspektionen
SHARE_FI = ("share", "aktie", "shares", "aktier")


def fi_fetch(a, b):
    r = get(FI_URL.format(frm=a.isoformat(), to=b.isoformat()), timeout=120)
    txt, _ = decode(r.content)
    first = txt.split("\n")[0]
    delim = max([";", ",", "\t", "|"], key=lambda c: first.count(c))
    rr = list(csv.reader(io.StringIO(txt), delimiter=delim))
    if len(rr) - 1 >= 990 and (b - a).days >= 1:  # plafond de 1 000 lignes : tranche coupée en deux
        mid = a + (b - a) // 2
        h1, r1 = fi_fetch(a, mid)
        time.sleep(1)
        h2, r2 = fi_fetch(mid + timedelta(days=1), b)
        return h1 or h2, r1 + r2
    return (rr[0] if rr else []), rr[1:]


def compact_fi(r):
    for k in ("url", "via", "collectedAt", "place", "amount"):
        r.pop(k, None)
    return r


def collect_fi(st, clock, recs):
    s = st.setdefault("FI", {})
    cur = date.fromisoformat(s.get("cursor") or FI_START.isoformat())
    stop_at = date.today() - timedelta(days=1)
    by_id = {r["id"]: r for r in recs}
    added, chunks = 0, 0
    while cur <= stop_at and clock.left() > 90:
        b = min(stop_at, cur + timedelta(days=13))
        try:
            h, rows = fi_fetch(cur, b)
        except Exception as e:
            print(f"FI : tranche {cur} inaccessible ({type(e).__name__}) : reprise au prochain passage")
            s["lastError"] = f"{cur}: {str(e)[:120]}"
            break
        if h:
            _, colmap, rs = fi_parse(h, rows, "0000-00-00")
            if not all(f in colmap for f in ("isin", "nature", "txDate", "price")):
                print("FI : colonnes non reconnues", h[:12])
                s["lastError"] = "colonnes non reconnues"
                break
            for r in rs:
                if norm(r.get("instrument")) in SHARE_FI:
                    by_id[r["id"]] = compact_fi(r)
                    added += 1
        chunks += 1
        if chunks % 20 == 0:
            print(f"FI : {b} atteint, {len(by_id)} lignes")
        # la dernière tranche (jusqu'à hier) sera relue au prochain passage : déclarations publiées tardivement
        if b >= stop_at:
            cur = max(cur, stop_at - timedelta(days=13))
            break
        cur = b + timedelta(days=1)
        s["cursor"] = cur.isoformat()
        time.sleep(1.5)
    s.update({"records": len(by_id), "lastRun": date.today().isoformat(), "upToDate": cur >= stop_at - timedelta(days=14)})
    s["cursor"] = cur.isoformat()
    print(f"FI : {added} lignes lues, {len(by_id)} au total")
    return list(by_id.values())


# --------------------------------------------------------------------------- résultats des achats
BUY_WORDS = re.compile(r"acquisition|souscription|achat|purchase|subscription|forvarv|teckning|kop\b|buy", re.I)
NOT_BUY = re.compile(r"stock option|option programme|share option|gratuit|free|tilldelning|allotment|grant|attribution|exercice|exercise|lan\b|loan|pledge|pant|gava|gift|arv|inherit", re.I)


def is_buy_like(r):
    n = norm(r.get("nature"))
    return bool(BUY_WORDS.search(n)) and not NOT_BUY.search(n)


def buy_keys(hist_recs):
    keys = set()
    for r in hist_recs:
        if r.get("isin") and is_buy_like(r):
            keys.add((r["isin"], (r.get("published") or r.get("txDate") or "")[:10]))
    st = load_json(DATA / "euro-signal-state.json", {})
    for isin, lst in (st.get("txArchive") or {}).items():
        for t in lst or []:
            if t.get("type") == "achat" and (t.get("pubDate") or t.get("txDate")):
                keys.add((isin, (t.get("pubDate") or t.get("txDate"))[:10]))
    return {k for k in keys if k[1] and re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", k[0])}


def yahoo_closes(ticker, start):
    import yfinance as yf
    t = yf.Ticker(ticker)
    h = t.history(start=start, interval="1d", auto_adjust=False, actions=False)
    if h is None or h.empty:
        return None, None
    cur = None
    try:
        cur = (t.history_metadata or {}).get("currency")
    except Exception:
        pass
    out = []
    for idx, row in h.iterrows():
        c = row.get("Close")  # clôture ajustée des divisions seulement (comme l'indice, sans dividendes)
        if c is not None and not math.isnan(c) and c > 0:
            out.append((idx.strftime("%Y-%m-%d"), float(c)))
    return out, cur


def asof(series, d):
    """Dernière valeur connue à la date d (séries triées)."""
    lo, hi = 0, len(series) - 1
    if hi < 0 or series[0][0] > d:
        return None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if series[mid][0] <= d:
            lo = mid
        else:
            hi = mid - 1
    return series[lo][1]


def outcome(closes, pub, bench, fxs):
    i = next((k for k, (d, _) in enumerate(closes) if d > pub), None)
    if i is None:
        return None
    e_d, e_p = closes[i]
    fx0 = fxs(e_d)
    b0 = asof(bench, e_d)
    if fx0 is None or not b0:
        return None
    res = [e_d]
    rets, brs, exit120 = [], [], None
    for h in HORIZONS:
        j = i + h
        if j < len(closes):
            d, p = closes[j]
            fx1, b1 = fxs(d), asof(bench, d)
            r = (p / fx1) / (e_p / fx0) - 1 if fx1 else None
            if r is not None and abs(r) > 4:  # cours aberrant (regroupement non ajusté…) : écarté
                r = None
            rets.append(None if r is None else round(r, 4))
            brs.append(round(b1 / b0 - 1, 4) if b1 else None)
            if h == 120:
                exit120 = d
        else:
            rets.append(None)
            brs.append(None)
    return res + rets + brs + [exit120]


def compute_outcomes(hist_recs, clock, st):
    import yfinance as yf  # noqa: F401
    from prices import search_yahoo
    s = st.setdefault("outcomes", {})
    outs = load_json(OUTCOMES, {})
    tick = load_json(HTICKERS, {})
    live = load_json(DATA / "tickers.json", {})
    keys = buy_keys(hist_recs)
    today = date.today().isoformat()
    todo = {}
    for isin, pub in keys:
        o = outs.get(f"{isin}|{pub}")
        if o and o[3] is not None:
            continue  # résultat à 120 séances déjà connu
        if o and o[-1] == today:
            continue
        todo.setdefault(isin, []).append(pub)
    print(f"Résultats : {len(keys)} achats, {sum(len(v) for v in todo.values())} à calculer sur {len(todo)} titres")
    if not todo:
        s.update({"buys": len(keys), "known": sum(1 for k in keys if f'{k[0]}|{k[1]}' in outs), "lastRun": today})
        return
    start_all = min(min(v) for v in todo.values())
    bench, _ = yahoo_closes(BENCH, (date.fromisoformat(start_all) - timedelta(days=10)).isoformat())
    if not bench:
        print("STOXX 600 indisponible : résultats reportés")
        return
    fxser = {}
    for c in FX_CODES:
        try:
            ser, _ = yahoo_closes(f"EUR{c}=X", (date.fromisoformat(start_all) - timedelta(days=10)).isoformat())
            if ser:
                fxser[c] = ser
        except Exception:
            pass
    done_t, nores = 0, 0
    for isin in sorted(todo, key=lambda k: -len(todo[k])):
        if clock.left() < 60:
            print("Résultats : temps écoulé, suite au prochain passage")
            break
        info = tick.get(isin)
        if info is None:
            lv = live.get(isin) or {}
            info = {"ticker": lv.get("ticker")} if lv.get("ticker") else (search_yahoo(isin) or {"ticker": None})
            info["at"] = today
            tick[isin] = info
            time.sleep(0.3)
        elif not info.get("ticker") and info.get("at", "") < (date.today() - timedelta(days=30)).isoformat():
            info = search_yahoo(isin) or {"ticker": None}
            info["at"] = today
            tick[isin] = info
        if not info.get("ticker"):
            nores += 1
            continue
        pubs = sorted(todo[isin])
        try:
            closes, cur = yahoo_closes(info["ticker"], (date.fromisoformat(pubs[0]) - timedelta(days=10)).isoformat())
        except Exception:
            closes, cur = None, None
        if not closes:
            nores += 1
            continue
        unit = 1.0
        if cur in ("GBp", "GBX"):
            cur, unit = "GBP", 100.0
        cur = (cur or "EUR").upper()
        if cur == "EUR":
            fxs = lambda d: 1.0
        elif cur in fxser:
            ser = fxser[cur]
            fxs = lambda d, ser=ser, unit=unit: (lambda v: v * unit if v else None)(asof(ser, d))
        else:
            nores += 1
            continue
        for pub in pubs:
            o = outcome(closes, pub, bench, fxs)
            if o:
                outs[f"{isin}|{pub}"] = o + [today] if o[3] is None else o
        done_t += 1
        time.sleep(0.15)
    save_json(OUTCOMES, outs)
    save_json(HTICKERS, tick)
    s.update({"buys": len(keys), "known": sum(1 for k in keys if f'{k[0]}|{k[1]}' in outs), "noPrice": nores, "lastRun": today})
    print(f"Résultats : {done_t} titres traités, {nores} sans cours, {s['known']} achats avec résultat")


# --------------------------------------------------------------------------- sondage (vérification des formats)
def probe():
    print("=== AMF : liste février 2021 ===")
    items = bdif_list(date(2021, 2, 1), date(2021, 2, 5))
    print(len(items), "déclarations ; exemple", items[:2])
    for d0 in (date(2021, 2, 15), date(2023, 6, 1), date(2024, 2, 1)):
        it = bdif_list(d0, d0 + timedelta(days=2))
        for x in it[:2]:
            txt = pdf_text(get(x["url"]).content)
            print(f"\n--- {x['numero']} ({x['issuer']}) ---\n{txt[:2500]}\n--- analyse ---")
            print(json.dumps(fr_parse_pdf_text(txt, x), ensure_ascii=False, indent=1))
    print("\n=== FI : juillet 2016 et mars 2019 ===")
    for a in (date(2016, 7, 1), date(2019, 3, 1)):
        h, rows = fi_fetch(a, a + timedelta(days=6))
        _, colmap, rs = fi_parse(h, rows, "0000-00-00")
        print(a, len(rows), "lignes ; colonnes", sorted(colmap), "\n", h, "\n", rows[:2], "\n", rs[:1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=150)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--skip", default="", help="sources à sauter : AMF,FI,OUT")
    a = ap.parse_args()
    if a.probe:
        probe()
        return 0
    clock = Clock(a.minutes)
    skip = set(x.strip().upper() for x in a.skip.split(",") if x.strip())
    st = load_json(STATE, {})
    recs = {k: load_json(p, []) for k, p in FILES.items()}
    # Suède d'abord (export rapide), puis France (un PDF par déclaration), puis résultats ; temps partagé
    if "FI" not in skip:
        sub = Clock(min(a.minutes * 0.45, clock.left() / 60))
        recs["FI"] = collect_fi(st, sub, recs["FI"])
        save_json(FILES["FI"], sorted(recs["FI"], key=lambda r: (r.get("published") or "", r["id"])))
        save_json(STATE, st)
    if "AMF" not in skip:
        sub = Clock(min(a.minutes * 0.45, clock.left() / 60))
        recs["AMF"] = collect_fr(st, sub, recs["AMF"])
        save_json(FILES["AMF"], sorted(recs["AMF"], key=lambda r: (r.get("published") or "", r["id"])))
        save_json(STATE, st)
    if "OUT" not in skip:
        compute_outcomes(recs["FI"] + recs["AMF"], clock, st)
    st["generated_at"] = datetime.now(timezone.utc).isoformat()
    save_json(STATE, st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
