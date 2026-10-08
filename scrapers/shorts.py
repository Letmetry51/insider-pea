"""
Euro Signal — positions vendeuses nettes publiées (règlement européen sur la vente à découvert, seuil 0,5 % du capital).

Un dirigeant qui achète pendant que des fonds parient sur la baisse : signal à croiser (conviction contre le consensus
vendeur, ou au contraire avertissement). Chaque régulateur publie ses propres fichiers :
  FR  AMF (data.gouv.fr, historique depuis 2012)       IT  Consob (xlsx, actuelles + historiques)
  ES  CNMV (xls, actuelles + historiques)              NL  AFM (csv, actuelles + historiques)
  BE  FSMA (csv, actuelles + historiques)              DE  Bundesanzeiger (csv, session requise)
Sortie : data/shorts.json = { generated_at, sources: {pays: {status, n, note}}, items: {ISIN: [{holder, pct, from, to, country}]} }
« from » = date de la position, « to » = date de la notification suivante du même fonds (ou de fin de publication) ;
to = null tant que la position est en vigueur. Seules les 3 dernières années sont gardées.
En cas d'échec d'une source, ses positions de la veille sont conservées (statut « echec »).
"""
import csv
import io
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "shorts.json"
DIAG = DATA / "diagnostics" / "shorts.json"
UA = {"User-Agent": "Mozilla/5.0 (Euro Signal; suivi personnel des déclarations publiques)"}
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
           "Accept": "text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8",
           "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
KEEP_FROM = (date.today() - timedelta(days=3 * 365)).isoformat()
STALE_OPEN = (date.today() - timedelta(days=365)).isoformat()  # sans nouvelle déclaration depuis un an : position présumée close

SOURCES = {
    "FR": {"name": "AMF", "urls": ["https://www.data.gouv.fr/api/1/datasets/r/c2539d1c-8531-4937-9cba-3bd8e9786cc5"],
           "dataset": "https://www.data.gouv.fr/api/1/datasets/62738e33f1be79935d3e5553/"},
    "IT": {"name": "Consob", "page": "https://www.consob.it/web/area-pubblica/pnc",
           "urls": ["https://www.consob.it/documents/11973/395154/PncPubbl.xlsx/fbefe0a2-795b-bad3-9369-beccbeb14f27"]},
    "ES": {"name": "CNMV", "urls": ["https://www.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xls"]},
    "NL": {"name": "AFM", "urls": ["https://www.afm.nl/export.aspx?type=8a46a4ef-f196-4467-a7ab-1ae1cb58f0e7&format=csv",
                                   "https://www.afm.nl/export.aspx?type=3ca31b3d-23d9-4fa2-b846-29c7e3f0e5ff&format=csv"]},
    "BE": {"name": "FSMA", "urls": ["https://www.fsma.be/en/de-shortselling?page&_format=csv",
                                    "https://www.fsma.be/en/de-shortselling-history?page&_format=csv"]},
    "DE": {"name": "Bundesanzeiger", "page": "https://www.bundesanzeiger.de/pub/de/nlp"},
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9%]+", " ", s).strip()


def pct_of(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if x == x else None
    s = str(v).strip().replace("%", "").replace("\xa0", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    s = s.replace(",", ".")
    try:
        x = float(s)
    except ValueError:
        return None
    return x if x == x else None


def day_of(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (int, float)) and 20000 < v < 80000:  # numéro de série Excel
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    s = str(v).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return "%s-%s-%s" % m.groups()
    m = re.match(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
    return None


# Colonnes reconnues par mots-clés (fichiers en français, anglais, italien, espagnol, néerlandais, allemand)
COLS = {
    "isin": [r"\bisin\b"],
    "holder": [r"holder", r"detentore", r"detenteur", r"titular", r"houder", r"positionsinhaber", r"tenedor"],
    "pct": [r"net short position", r"posizione netta", r"position courte nette", r"posicion corta", r"posicion neta", r"netto short", r"^position$", r"^ratio$", r"positie", r"%", r"pourcentage"],
    "date": [r"position date", r"data della posizione", r"date de debut", r"date de la position", r"fecha", r"positiedatum", r"^datum$", r"date de position", r"^date$"],
    "end": [r"date de fin", r"end date", r"fin de publication"],
}


def map_header(row):
    h = [norm(c) for c in row]
    out = {}
    for key, pats in COLS.items():
        for pat in pats:
            for k, c in enumerate(h):
                if k in out.values():
                    continue
                if re.search(pat, c) and not (key == "holder" and ("isin" in c or c.startswith("lei") or " lei" in c)) and not (key == "pct" and ("date" in c or "data" in c or "fecha" in c or "datum" in c)):
                    out[key] = k
                    break
            if key in out:
                break
    if key_ok(out):
        if "date" not in out:  # « date » générique en dernier recours
            for k, c in enumerate(h):
                if "date" in c or "datum" in c or "data" in c or "fecha" in c:
                    if k not in out.values():
                        out["date"] = k
                        break
        return out
    return None


def key_ok(m):
    return "isin" in m and "pct" in m and "holder" in m


def rows_to_records(rows, country, diag):
    """rows : liste de lignes (listes). Trouve la ligne d'en-tête, renvoie des notifications."""
    hdr, idx = None, None
    for k, r in enumerate(rows[:40]):
        m = map_header(r)
        if m:
            hdr, idx = k, m
            break
    if hdr is None:
        diag.append({"country": country, "error": "en-tête introuvable", "first": [list(map(str, r))[:8] for r in rows[:3]]})
        return []
    diag.append({"country": country, "header": [str(c) for c in rows[hdr]][:12], "mapped": idx})
    out, body = [], rows[hdr + 1:]
    # Échelle décidée pour toute la colonne : un fichier où toutes les valeurs sont < 0,3 est en fraction (0,0062 = 0,62 %).
    # Valeur par valeur, une notification « passée sous 0,5 % » à 0,10 % deviendrait 10 %.
    vals = [pct_of(r[idx["pct"]]) for r in body if idx["pct"] < len(r)]
    vals = [v for v in vals if v is not None and v > 0]
    scale = 100.0 if vals and max(vals) < 0.3 else 1.0
    for r in body:
        try:
            isin = str(r[idx["isin"]] or "").strip().upper()
        except IndexError:
            continue
        if not ISIN_RE.match(isin):
            continue
        p = pct_of(r[idx["pct"]] if idx["pct"] < len(r) else None)
        p = p * scale if p is not None else None
        d = day_of(r[idx["date"]]) if "date" in idx and idx["date"] < len(r) else None
        e = day_of(r[idx["end"]]) if "end" in idx and idx["end"] < len(r) else None
        if p is None or p < 0 or p > 50:
            continue
        out.append({"isin": isin, "holder": str(r[idx["holder"]] or "").strip()[:80], "pct": round(p, 2), "date": d, "end": e, "country": country})
    return out


def decode(b):
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16", "replace")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1", "replace")


def parse_bytes(b, country, diag):
    if b[:4] == b"PK\x03\x04":  # xlsx
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
        recs = []
        for ws in wb.worksheets:
            recs += rows_to_records([list(r) for r in ws.iter_rows(values_only=True)], country, diag)
        return recs
    if b[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # xls (Excel 97-2003)
        import xlrd
        book = xlrd.open_workbook(file_contents=b)
        recs = []
        for sh in book.sheets():
            rows = []
            for i in range(sh.nrows):
                row = []
                for j, c in enumerate(sh.row(i)):
                    if c.ctype == xlrd.XL_CELL_DATE:
                        try:
                            row.append(datetime(*xlrd.xldate_as_tuple(c.value, book.datemode)))
                        except Exception:
                            row.append(c.value)
                    else:
                        row.append(c.value)
                rows.append(row)
            recs += rows_to_records(rows, country, diag)
        return recs
    text = decode(b)
    if text.lstrip().startswith("<"):
        raise ValueError("page HTML reçue au lieu d'un fichier")
    sample = text[:5000]
    delim = max([";", ",", "\t", "|"], key=lambda d: sample.count(d))
    csv.field_size_limit(10 ** 7)
    return rows_to_records(list(csv.reader(io.StringIO(text), delimiter=delim)), country, diag)


LAST = {}


def fetch(url, session=None, headers=None):
    r = (session or requests).get(url, headers=headers or UA, timeout=90, allow_redirects=True)
    LAST.update({"url": url[:160], "status": r.status_code, "type": r.headers.get("content-type", "")[:80], "head": r.content[:24].hex()})
    r.raise_for_status()
    return r.content


def consob_urls(src):
    urls = list(src["urls"])
    try:
        html = fetch(src["page"]).decode("utf-8", "replace")
        for m in re.finditer(r'href="([^"]*PncPubbl\.xlsx[^"]*)"', html):
            u = m.group(1)
            urls.insert(0, u if u.startswith("http") else "https://www.consob.it" + u)
    except Exception:
        pass
    return list(dict.fromkeys(urls))


def amf_urls(src):
    urls = list(src["urls"])
    try:
        ds = json.loads(fetch(src["dataset"]))
        res = sorted(ds.get("resources") or [], key=lambda r: r.get("last_modified") or "", reverse=True)
        for r in res:
            if r.get("url"):
                urls.insert(0, r["url"])
                break
    except Exception:
        pass
    return list(dict.fromkeys(urls))


def bundesanzeiger(src, diag):
    s = requests.Session()
    html = fetch(src["page"], s).decode("utf-8", "replace")
    m = re.search(r'href="([^"]*csv[^"]*)"', html, re.I)
    if not m:
        raise ValueError("lien CSV introuvable")
    u = m.group(1).replace("&amp;", "&")
    if not u.startswith("http"):
        u = "https://www.bundesanzeiger.de" + (u if u.startswith("/") else "/pub/de/" + u.lstrip("./"))
    return parse_bytes(fetch(u, s), "DE", diag)


def intervals(recs):
    """Notifications → positions datées : chaque notification vaut jusqu'à la suivante du même fonds sur le même titre."""
    by = {}
    for r in recs:
        if not r["date"]:
            continue
        by.setdefault((r["isin"], norm(r["holder"])), {})[r["date"]] = r  # doublons (actuelles + historiques) fusionnés
    items = {}
    for (isin, _), d in by.items():
        seq = [d[k] for k in sorted(d)]
        for k, r in enumerate(seq):
            to = seq[k + 1]["date"] if k + 1 < len(seq) else r.get("end")
            if not to and r["date"] < STALE_OPEN:
                to = (datetime.fromisoformat(r["date"]) + timedelta(days=365)).date().isoformat()
            if r["pct"] < 0.5 or r["pct"] > 25 or (to and to < KEEP_FROM):
                continue
            items.setdefault(isin, []).append({"holder": r["holder"], "pct": r["pct"], "from": r["date"], "to": to, "country": r["country"]})
    return items


def main():
    prev = {}
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        if not isinstance(prev, dict):
            prev = {}
    except Exception:
        pass
    diag, all_items, sources = [], {}, {}
    for cc, src in SOURCES.items():
        recs, note = [], None
        try:
            if cc == "DE":
                recs = bundesanzeiger(src, diag)
            else:
                urls = consob_urls(src) if cc == "IT" else amf_urls(src) if cc == "FR" else src["urls"]
                errors = []
                for k, u in enumerate(urls):
                    try:
                        try:
                            got = parse_bytes(fetch(u), cc, diag)
                        except Exception as e1:
                            diag.append({"country": cc, "error": type(e1).__name__ + " : " + str(e1)[:100], "response": dict(LAST)})
                            got = parse_bytes(fetch(u, headers=BROWSER), cc, diag)  # second essai avec un en-tête de navigateur
                        recs += got
                        if cc in ("IT", "FR") and got:
                            break  # premier fichier valide suffit (variantes du même fichier)
                    except Exception as e:
                        errors.append(type(e).__name__)
                        diag.append({"country": cc, "error": type(e).__name__ + " : " + str(e)[:100], "response": dict(LAST)})
                if not recs and errors:
                    raise RuntimeError("/".join(errors))
            if not recs:
                raise RuntimeError("fichier vide ou colonnes non reconnues")
            it = intervals(recs)
            if cc == "DE":  # fichier des positions en vigueur seulement : une position disparue est close à la date du jour
                today = date.today().isoformat()
                now = {(isin, norm(p["holder"]), p["from"]) for isin, lst in it.items() for p in lst}
                for isin, lst in (prev.get("items") or {}).items():
                    for p in lst if isinstance(lst, list) else []:
                        if not isinstance(p, dict) or p.get("country") != "DE":
                            continue
                        if (isin, norm(p.get("holder")), p.get("from")) in now:
                            continue
                        q = dict(p)
                        if not q.get("to"):
                            q["to"] = today
                        if q["to"] >= KEEP_FROM:
                            it.setdefault(isin, []).append(q)
            for isin, lst in it.items():
                all_items.setdefault(isin, []).extend(lst)
            open_n = sum(1 for lst in it.values() for p in lst if not p["to"])
            sources[cc] = {"name": src["name"], "status": "ok", "notifications": len(recs), "open": open_n, "issuers": len(it), "lastSuccess": date.today().isoformat()}
        except Exception as e:
            note = type(e).__name__ + " : " + str(e)[:120]
            old = (prev.get("sources") or {}).get(cc) or {}
            sources[cc] = {"name": src["name"], "status": "echec", "note": note, "lastSuccess": old.get("lastSuccess")}
            for isin, lst in (prev.get("items") or {}).items():  # positions de la veille conservées pour ce pays
                keep = [p for p in (lst if isinstance(lst, list) else []) if isinstance(p, dict) and p.get("country") == cc]
                if keep:
                    all_items.setdefault(isin, []).extend(keep)
        print("Positions vendeuses %s (%s) : %s" % (cc, src["name"], sources[cc]["status"] + (" — %d notifications, %d positions en vigueur" % (sources[cc]["notifications"], sources[cc]["open"]) if sources[cc]["status"] == "ok" else " — " + note)))
    DATA.mkdir(exist_ok=True)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": sources, "items": all_items}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        DIAG.parent.mkdir(parents=True, exist_ok=True)
        DIAG.write_text(json.dumps(diag[:40], ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
