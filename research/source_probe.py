"""Sources de cours de secours (si Yahoo coupe l'accès) : lesquelles répondent depuis GitHub Actions, et donnent-elles le
même dernier cours que Yahoo ? Petit échantillon par bourse, quelques requêtes par source, rien n'est gardé hors du rapport.

Sources essayées (téléchargements publics de leurs sites, sans clé) :
- Euronext : liste des actions (symbole, ISIN, marché) et historique d'un titre (Paris, Amsterdam, Bruxelles, Milan,
  Lisbonne, Oslo, Dublin) ;
- Stooq : historique CSV ;
- Nasdaq Nordic : historique (Stockholm, Helsinki, Copenhague) ;
- Google Finance : dernier cours de la page du titre.

  python source_probe.py        (GitHub Actions : workflow « Recherche (à la demande) », script source_probe.py)
Résultat : out/source_probe.txt
"""
import csv
import datetime as dt
import glob
import io
import json
import os
import re
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
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
        r = requests.get(url, headers=dict(UA, **kw.pop("headers", {})), timeout=25, **kw)
        return r
    except Exception as e:
        log("   ✗ réseau :", type(e).__name__, str(e)[:80])
        return None


# --- référence : dernier cours Yahoo connu (catalogue du soir), par symbole Yahoo
ref, ddates = {}, []
for f in glob.glob(os.path.join(DATA, "societes", "*.json")):
    sh = json.load(open(f))
    if len(sh.get("dDates") or []) > len(ddates):
        ddates = sh["dDates"]
    for s, x in (sh.get("items") or {}).items():
        d = x.get("d") or []
        k = max((i for i, v in enumerate(d) if v), default=None)
        if k is not None:
            ref[s] = (k, d[k])
inst = json.load(open(os.path.join(DATA, "euro-signal.json"))).get("inst", {})
isin_of = {x.get("ticker"): i for i, x in inst.items() if x.get("ticker")}


def refval(sym):
    r = ref.get(sym)
    return (ddates[r[0]] if r and r[0] < len(ddates) else None, r[1] if r else None)


def near(a, b):
    return a and b and abs(a / b - 1) < 0.02


SUF = ["PA", "AS", "BR", "MI", "LS", "OL", "IR", "DE", "MC", "ST", "HE", "CO", "VI"]
idx = json.load(open(os.path.join(DATA, "societes-index.json")))
cap = {r[0]: (r[3] or 0) for r in idx.get("rows") or []}
sample = {}
for s in sorted(ref, key=lambda s: -cap.get(s, 0)):  # les plus grosses capitalisations de chaque bourse
    suf = s.rsplit(".", 1)[-1] if "." in s else ""
    if suf in SUF and len(sample.setdefault(suf, [])) < 3:
        sample[suf].append(s)
log("Échantillon :", {k: v for k, v in sample.items()})
score = {}


def tally(src, ok):
    a = score.setdefault(src, [0, 0])
    a[0] += bool(ok)
    a[1] += 1


# --- 1. Euronext : liste des actions (symbole → ISIN, MIC)
log("\n== Euronext : liste des actions")
enx = {}
r = get("https://live.euronext.com/en/pd_es/data/stocks/download",
        params={"mics": "dm_all_stock", "initialLetter": "", "fe_type": "csv", "fe_decimal_separator": ".",
                "fe_date_format": "d/m/Y"})
if r is not None:
    log("   HTTP", r.status_code, len(r.content), "octets", r.headers.get("content-type"))
    try:
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "replace")), delimiter=";"))
        head = next((i for i, x in enumerate(rows) if x and x[0].strip().lower() == "name"), None)
        if head is not None:
            h = [c.strip().lower() for c in rows[head]]
            for x in rows[head + 1:]:
                if len(x) >= len(h):
                    rec = dict(zip(h, x))
                    enx.setdefault(rec.get("symbol", "").strip(), []).append(rec)
            log("   actions listées :", sum(len(v) for v in enx.values()), "· colonnes :", h)
            # dernier cours de toutes les actions Euronext en un seul fichier : comparé au catalogue (Yahoo)
            SX = {"paris": "PA", "amsterdam": "AS", "brussels": "BR", "milan": "MI", "lisbon": "LS", "oslo": "OL", "dublin": "IR"}
            ok = bad = 0
            ex = []
            for sym, recs in enx.items():
                for rec in recs:
                    mk = (rec.get("market") or "").lower()
                    suf = next((v for k, v in SX.items() if k in mk), None)
                    if not suf or (sym + "." + suf) not in ref:
                        continue
                    try:
                        last = float((rec.get("closing price") or rec.get("last price") or "").replace(",", ""))
                    except ValueError:
                        continue
                    rd, rv = refval(sym + "." + suf)
                    if rd and (rec.get("closing price datetime") or "")[:10] not in (rd, rd[8:10] + "/" + rd[5:7] + "/" + rd[:4]):
                        continue  # pas la même séance que le catalogue : comparaison sans objet
                    if near(last, rv):
                        ok += 1
                    else:
                        bad += 1
                        if len(ex) < 5:
                            ex.append((sym + "." + suf, last, rec.get("closing price datetime"), rd, rv))
            log(f"   cours de clôture du fichier comparé au catalogue (Yahoo), même séance : {ok} identiques à 2 % près, {bad} différents")
            log("   exemple de ligne :", next(iter(enx.values()))[0])
            for e in ex:
                log("      écart :", e)
            tally("Euronext (liste, dernier cours)", ok > 10 * max(bad, 1) if ok else False)
        else:
            log("   en-tête introuvable, début :", r.text[:200].replace("\n", " | "))
    except Exception as e:
        log("   lecture impossible :", e)
MIC = {"PA": ["XPAR", "ALXP", "XMLI"], "AS": ["XAMS"], "BR": ["XBRU", "ALXB"], "MI": ["MTAA", "EXGM"], "LS": ["XLIS"],
       "OL": ["XOSL", "MERK"], "IR": ["XMSM"]}
log("\n== Euronext : historique d'un titre")
for suf, syms in sample.items():
    if suf not in MIC:
        continue
    for s in syms:
        base = s.rsplit(".", 1)[0]
        def mic_of(mk):
            mk = (mk or "").lower()
            g = "growth" in mk
            for k, v in (("paris", "ALXP" if g else "XPAR"), ("amsterdam", "XAMS"), ("brussels", "ALXB" if g else "XBRU"),
                         ("milan", "EXGM" if g else "MTAA"), ("lisbon", "XLIS"), ("oslo", "MERK" if g else "XOSL"),
                         ("dublin", "XMSM")):
                if k in mk:
                    return v
            return None
        cands = [(c.get("isin"), mic_of(c.get("market"))) for c in enx.get(base, []) if mic_of(c.get("market"))]
        if not cands and isin_of.get(s):
            cands = [(isin_of[s], m) for m in MIC[suf]]
        rd, rv = refval(s)
        got = None
        for isin, mic in cands[:3]:
            if not isin:
                continue
            u = f"https://live.euronext.com/en/ajax/AwlHistoricalPrice/getFullDownloadAjax/{isin}-{mic}"
            end = dt.date.today()
            r = get(u, params={"format": "csv", "decimal_separator": ".", "date_form": "d/m/Y", "op": "",
                               "adjusted": "Y", "base100": "", "startdate": str(end - dt.timedelta(days=20)),
                               "enddate": str(end)})
            if r is not None and r.status_code == 200 and r.text.strip():
                rows = [x for x in csv.reader(io.StringIO(r.text), delimiter=";") if x]
                data = [x for x in rows if re.match(r"\d\d/\d\d/\d{4}", x[0] or "")]
                if data:
                    d0 = max(data, key=lambda x: (x[0][6:], x[0][3:5], x[0][:2]))
                    try:
                        got = (f"{d0[0][6:]}-{d0[0][3:5]}-{d0[0][:2]}", float(d0[4] if len(d0) > 4 else d0[1]))
                    except ValueError:
                        got = (d0[0], d0[1:6])
                    log(f"   {s:10s} {isin}-{mic} → {got} · Yahoo {rd} {rv}")
                    break
            time.sleep(0.5)
        if not got:
            log(f"   {s:10s} ✗ (candidats {cands[:2]})")
        tally("Euronext", got and isinstance(got[1], float) and near(got[1], rv))

# --- 2. Stooq
log("\n== Stooq")
SQ = {"PA": "fr", "AS": "nl", "BR": "be", "MI": "it", "LS": "pt", "OL": "no", "IR": "ie", "DE": "de", "MC": "es",
      "ST": "se", "HE": "fi", "CO": "dk", "VI": "at"}
for suf, syms in sample.items():
    for s in syms[:2]:
        base = s.rsplit(".", 1)[0].lower().replace("-", ".")
        q = f"{base}.{SQ.get(suf, suf.lower())}"
        r = get("https://stooq.com/q/d/l/", params={"s": q, "i": "d"})
        rd, rv = refval(s)
        ok = False
        if r is not None:
            t = r.text.strip().splitlines()
            if len(t) > 1 and t[0].lower().startswith("date"):
                last = t[-1].split(",")
                try:
                    ok = near(float(last[4]), rv)
                except (ValueError, IndexError):
                    pass
                log(f"   {s:10s} {q:12s} → {last[:5]} · Yahoo {rd} {rv}")
            else:
                log(f"   {s:10s} {q:12s} ✗ HTTP {r.status_code} : {r.text[:80]!r}")
        tally("Stooq", ok)
        time.sleep(0.5)

# --- 3. Nasdaq Nordic (recherche du titre, puis historique)
log("\n== Nasdaq Nordic")
for suf in ("ST", "HE", "CO"):
    for s in sample.get(suf, [])[:2]:
        base = s.rsplit(".", 1)[0].replace("-", " ")
        rd, rv = refval(s)
        ok = False
        r = get("https://api.nasdaq.com/api/nordic/search", params={"searchText": base},
                headers={"Accept": "application/json"})
        if r is None or r.status_code != 200:
            log(f"   {s:10s} ✗ recherche HTTP {getattr(r, 'status_code', '?')}")
            tally("Nasdaq Nordic", False)
            continue
        try:
            js = r.json()
            grp = (js.get("data") or [{}])
            inst_ = next((i for g in grp for i in (g.get("instruments") or []) if (i.get("symbol") or "").upper() == base.upper()), None)
            oid = inst_.get("orderbookId") if inst_ else None
            log(f"   {s:10s} recherche → {oid} ({(inst_ or {}).get('fullName')})")
            if oid:
                end = dt.date.today()
                h = get(f"https://api.nasdaq.com/api/nordic/instruments/{oid}/chart/download",
                        params={"assetClass": "SHARES", "fromDate": str(end - dt.timedelta(days=20)), "toDate": str(end)},
                        headers={"Accept": "application/json"})
                if h is not None and h.status_code == 200:
                    j = h.json()
                    rows = ((j.get("data") or {}).get("charts") or {}).get("rows") or []
                    last = rows[0] if rows else None
                    log(f"      historique → {str(last)[:160]} · Yahoo {rd} {rv}")
                    try:
                        ok = near(float(str(last.get("closePrice")).replace(",", "")), rv)
                    except Exception:
                        pass
                else:
                    log(f"      historique ✗ HTTP {getattr(h, 'status_code', '?')} {getattr(h, 'text', '')[:100]!r}")
        except Exception as e:
            log(f"   {s:10s} réponse illisible : {str(e)[:80]}")
        tally("Nasdaq Nordic", ok)
        time.sleep(0.5)

# --- 4. Google Finance (dernier cours affiché sur la page du titre)
log("\n== Google Finance")
GX = {"PA": "EPA", "AS": "AMS", "BR": "EBR", "MI": "BIT", "LS": "ELI", "OL": "OSL", "DE": "ETR", "MC": "BME", "ST": "STO",
      "HE": "HEL", "CO": "CPH", "VI": "VIE"}
for suf, syms in sample.items():
    if suf not in GX:
        continue
    s = syms[0]
    base = s.rsplit(".", 1)[0]
    rd, rv = refval(s)
    r = get(f"https://www.google.com/finance/quote/{base}:{GX[suf]}", params={"hl": "en"})
    ok = False
    if r is not None and r.status_code == 200:
        m = re.search(r'data-last-price="([0-9.]+)"', r.text)
        log(f"   {s:10s} → {m.group(1) if m else '✗ prix introuvable'} · Yahoo {rd} {rv}")
        ok = bool(m) and near(float(m.group(1)), rv)
    else:
        log(f"   {s:10s} ✗ HTTP {getattr(r, 'status_code', '?')}")
    tally("Google Finance", ok)
    time.sleep(1)

log("\n== Bilan : cours identiques à Yahoo à 2 % près")
for k, (a, n) in score.items():
    log(f"   {k:16s} {a}/{n}")
open(os.path.join(OUT, "source_probe.txt"), "w").write("\n".join(lines) + "\n")
