"""
Euro Signal — déclarations de dirigeants hors France (exécuté par GitHub Actions).

  Belgique : FSMA, liste « transaction-search » puis une fiche HTML par déclaration.
             robots.txt de la FSMA : Crawl-delay 30 s, respecté ici (une requête toutes les 30 s).
             Collecte incrémentale : au plus FSMA_MAX_DETAILS fiches par exécution, le reste au soir suivant.
  Pays-Bas : AFM, export CSV officiel du registre « Transacties leidinggevenden MAR 19 ».

Chaque exécution écrit :
  data/insiders-eu.json      déclarations accumulées (format commun) et état de chaque source
  data/diagnostics/*.json    court échantillon brut de chaque source, pour vérifier et ajuster les formats

Une source qui échoue est marquée « echec » : Euro Signal bloque alors les alertes des titres concernés
au lieu de conclure qu'il n'y a eu aucune opération.
"""
import csv
import io
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "insiders-eu.json"
DIAG = DATA / "diagnostics"
UA = {"User-Agent": "EuroSignal/1.0 (outil personnel de veille ; github.com/Letmetry51/insider-pea)", "Accept-Language": "en,fr;q=0.8,nl;q=0.6"}
WINDOW_DAYS = 120          # profondeur de la collecte (fenêtre de 3 mois + marge)
KEEP_DAYS = 800            # conservation pour l'étude d'événements
FSMA_BASE = "https://www.fsma.be"
FSMA_DELAY = 30            # Crawl-delay du robots.txt de la FSMA
FSMA_MAX_DETAILS = 36      # ≈ 18 min par exécution
AFM_CSV = "https://www.afm.nl/export.aspx?type=0ee836dc-5520-459d-bcf4-a4a689de6614&format=csv"
AFM_XML = "https://www.afm.nl/export.aspx?type=0ee836dc-5520-459d-bcf4-a4a689de6614&format=xml"

MONTHS = {"jan": 1, "feb": 2, "fev": 2, "fév": 2, "mar": 3, "mrt": 3, "apr": 4, "avr": 4, "may": 5, "mai": 5, "mei": 5, "jun": 6, "juin": 6,
          "jul": 7, "juil": 7, "aug": 8, "aou": 8, "aoû": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "déc": 12}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def iso_date(s):
    """Convertit 06/10/2026, 06-10-2026, 2026-10-06, '06 Oct 2026', '6 oktober 2026' en AAAA-MM-JJ (sinon None)."""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
        if m:
            d, mo, y = map(int, m.groups())
        else:
            m = re.match(r"(\d{1,2})\s+([A-Za-zéûè]{3,})\.?\s+(\d{4})", s)
            if not m:
                return None
            d, mon, y = int(m.group(1)), m.group(2).lower()[:4], int(m.group(3))
            mo = MONTHS.get(mon[:4]) or MONTHS.get(mon[:3])
            if not mo:
                return None
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def load_state():
    try:
        st = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    st.setdefault("records", {})
    st.setdefault("sources", {})
    st.setdefault("seen", {})
    return st


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def diag(name, obj):
    obj["at"] = now_iso()
    save_json(DIAG / f"{name}.json", obj)


# --------------------------------------------------------------------------- FSMA (Belgique)
class Polite:
    """Une requête au plus toutes les `delay` secondes sur un même site."""
    def __init__(self, delay):
        self.delay, self.last = delay, 0.0

    def get(self, url, **kw):
        wait = self.last + self.delay - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            return requests.get(url, headers=UA, timeout=40, **kw)
        finally:
            self.last = time.time()


FSMA_LABELS = ["Date of publication", "Notifying person", "Declarer Type", "Issuer", "Instrument Type", "Instrument ISIN Code",
               "Transaction Type", "Transaction Place", "Transaction Date", "Transaction Currency", "Transaction Quantity",
               "Transaction Price", "Transaction Amount", "Closely associated person of", "Closely associated with", "Position", "Function"]
TX_LEVEL = {"Instrument Type", "Instrument ISIN Code", "Transaction Type", "Transaction Place", "Transaction Date",
            "Transaction Currency", "Transaction Quantity", "Transaction Price", "Transaction Amount", "Transaction Type Specifications"}
FSMA_LABELS = ["Transaction Type Specifications"] + FSMA_LABELS


def fsma_label(line):
    """Libellé exact (seul sur sa ligne ou suivi de « : »). Évite que « Transaction Type Specifications »
    soit pris pour un second « Transaction Type », ce qui coupait une transaction en deux."""
    low = line.lower()
    for lab in FSMA_LABELS:
        l2 = lab.lower()
        if low == l2:
            return lab, ""
        if low.startswith(l2 + ":"):
            return lab, line[len(lab) + 1:].strip()
    return None, None


def fsma_parse_detail(html):
    """Lit les paires libellé/valeur d'une fiche FSMA ; une fiche peut contenir plusieurs transactions."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    lines = [l.strip() for l in main.get_text("\n").split("\n")]
    lines = [l for l in lines if l]
    found = []  # (label, value) dans l'ordre
    for i, l in enumerate(lines):
        lab, rest = fsma_label(l)
        if not lab:
            continue
        val = rest if rest else (lines[i + 1] if i + 1 < len(lines) else "")
        if val and fsma_label(val)[0] is None:
            found.append((lab, val.strip()))
    head, txs, cur = {}, [], {}
    for lab, val in found:
        if lab in TX_LEVEL:
            if lab in cur:  # même libellé déjà vu : transaction suivante
                txs.append(cur)
                cur = {}
            cur[lab] = val
        else:
            head.setdefault(lab, val)
    if cur:
        txs.append(cur)
    return head, txs


def fsma_list(polite, since):
    """Liens des fiches publiées depuis `since`, en essayant les formats de date du filtre."""
    url = FSMA_BASE + "/en/transaction-search"
    tried, links = [], {}
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", None):
        params = {"order": "field_ct_date_time", "sort": "desc"}
        if fmt:
            params.update({"date[min]": since.strftime(fmt), "date[max]": date.today().strftime(fmt)})
        page_links, first_text = {}, ""
        for page in range(0, 40):
            params["page"] = page
            r = polite.get(url, params=params)
            if r.status_code != 200:
                tried.append({"format": fmt, "page": page, "status": r.status_code})
                break
            soup = BeautifulSoup(r.text, "html.parser")
            if page == 0:
                first_text = soup.get_text(" ", strip=True)[:2500]
            new, oldest = 0, None
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/manager-transaction/" not in href:
                    continue
                full = href if href.startswith("http") else FSMA_BASE + href
                row = a.find_parent("tr") or a.find_parent("li") or a.parent
                d = None
                for m in re.finditer(r"\d{1,2}/\d{1,2}/\d{4}", row.get_text(" ") if row else ""):
                    d = iso_date(m.group(0))
                    break
                if full not in page_links:
                    page_links[full] = d
                    new += 1
                if d:
                    oldest = d if not oldest or d < oldest else oldest
            tried.append({"format": fmt, "page": page, "status": 200, "links": new, "oldest": oldest})
            if new == 0 or (oldest and oldest < since.isoformat()):
                break
        if page_links:
            links = page_links
            break
    return links, tried, first_text


def fsma_collect(st):
    src = st["sources"].get("FSMA", {})
    src.update({"name": "FSMA", "countries": ["BE"], "kind": "déclarations", "via": "fsma.be (fiches officielles, 1 requête / 30 s)", "lastAttempt": date.today().isoformat()})
    polite = Polite(FSMA_DELAY)
    since = date.today() - timedelta(days=WINDOW_DAYS)
    seen = set(st["seen"].get("FSMA", []))
    try:
        links, tried, first_text = fsma_list(polite, since)
    except Exception as e:
        src.update({"status": "echec", "note": "liste inaccessible : " + type(e).__name__})
        st["sources"]["FSMA"] = src
        diag("fsma", {"error": repr(e)[:300]})
        return
    todo = [u for u, d in links.items() if u not in seen and (not d or d >= since.isoformat())]
    todo.sort(key=lambda u: links[u] or "", reverse=True)  # les plus récentes d'abord
    done, parsed_sample, errors = 0, None, 0
    for u in todo[:FSMA_MAX_DETAILS]:
        try:
            r = polite.get(u)
            if r.status_code != 200:
                errors += 1
                continue
            head, txs = fsma_parse_detail(r.text)
            nid = re.sub(r"[^A-Za-z0-9_-]", "_", u.rstrip("/").split("/")[-1])
            if parsed_sample is None:
                parsed_sample = {"url": u, "head": head, "transactions": txs, "text": BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)[:2500]}
            for k, tx in enumerate(txs or [{}]):
                rec = {
                    "registry": "FSMA", "country": "BE", "id": f"{nid}-{k}", "url": u, "via": "fsma.be",
                    "published": iso_date(head.get("Date of publication")) or links.get(u), "issuer": head.get("Issuer"),
                    "person": head.get("Notifying person"), "role": head.get("Declarer Type") or head.get("Position") or head.get("Function"),
                    "linkedTo": head.get("Closely associated person of") or head.get("Closely associated with"),
                    "isin": tx.get("Instrument ISIN Code"), "instrument": tx.get("Instrument Type"),
                    "nature": " — ".join(v for v in (tx.get("Transaction Type"), tx.get("Transaction Type Specifications")) if v) or None,
                    "txDate": iso_date(tx.get("Transaction Date")), "place": tx.get("Transaction Place"), "currency": tx.get("Transaction Currency"),
                    "quantity": tx.get("Transaction Quantity"), "price": tx.get("Transaction Price"), "amount": tx.get("Transaction Amount"),
                    "numberLocale": "eu", "collectedAt": date.today().isoformat(),
                }
                st["records"][f"FSMA:{rec['id']}"] = rec
            seen.add(u)
            done += 1
        except Exception:
            errors += 1
    backlog = len(todo) - done
    st["seen"]["FSMA"] = sorted(seen)[-5000:]
    ok = bool(links) and errors <= max(2, done // 3)
    src.update({"status": ("ok" if backlog == 0 else "partiel") if ok else "echec", "rows": len(links), "fetched": done, "backlog": backlog,
                "note": None if ok and backlog == 0 else (f"rattrapage en cours : {backlog} fiche(s) restante(s)" if ok else "liste vide ou fiches illisibles")})
    if ok:
        src["lastSuccess"] = date.today().isoformat()
    st["sources"]["FSMA"] = src
    diag("fsma", {"listAttempts": tried, "listText": first_text, "detailSample": parsed_sample, "links": len(links), "fetched": done, "backlog": backlog, "errors": errors})
    print(f"FSMA : {len(links)} fiches listées, {done} lues, {backlog} en attente, {errors} erreur(s)")


# --------------------------------------------------------------------------- AFM (Pays-Bas)
AFM_COLS = {
    "txDate": ["transactiedatum", "datum transactie", "transactie", "transaction date", "date of transaction", "datum"],
    "published": ["datum melding", "meldingsdatum", "publicatiedatum", "datum publicatie", "notification date", "date of notification"],
    "issuer": ["uitgevende instelling", "issuing institution", "issuer", "uitgevende instelling naam"],
    "person": ["meldingsplichtige", "notifying party", "notifying person", "naam meldingsplichtige"],
    "role": ["functie", "positie", "position", "hoedanigheid"],
    "isin": ["isin", "isin code", "isin-code"],
    "nature": ["soort transactie", "aard van de transactie", "aard transactie", "type transactie", "nature of the transaction", "transactiesoort"],
    "instrument": ["soort financieel instrument", "financieel instrument", "type instrument", "instrument", "soort instrument"],
    "price": ["prijs", "koers", "price"],
    "quantity": ["aantal", "volume", "quantity", "hoeveelheid"],
    "amount": ["totaal", "bedrag", "totale waarde", "totaalbedrag", "amount"],
    "currency": ["valuta", "munteenheid", "currency"],
    "place": ["plaats van de transactie", "handelsplatform", "plaats", "venue"],
    "id": ["kenmerk", "meldingsnummer", "id", "referentie"],
    "url": ["link", "url", "details"],
}


csv.field_size_limit(10 ** 9)  # certains champs de l'export AFM dépassent la limite par défaut (131 072)


def decode(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or raw[:1000].count(b"\x00") > 200:
        try:
            return raw.decode("utf-16"), "utf-16"
        except Exception:
            pass
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            txt = raw.decode(enc)
            if txt.count("\x00") < 5:
                return txt, enc
        except Exception:
            continue
    return raw.decode("latin-1", "replace"), "latin-1?"


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def afm_collect(st):
    src = st["sources"].get("AFM", {})
    src.update({"name": "AFM", "countries": ["NL"], "kind": "déclarations", "via": "afm.nl (export CSV officiel)", "lastAttempt": date.today().isoformat()})
    d = {}
    try:
        r = requests.get(AFM_CSV, headers=UA, timeout=60)
        d["status"], d["contentType"], d["bytes"] = r.status_code, r.headers.get("content-type"), len(r.content)
        if r.status_code != 200 or not r.content:
            raise RuntimeError(f"HTTP {r.status_code}")
        txt, enc = decode(r.content)
        d["encoding"] = enc
        sample = txt[:4000]
        d["head"] = txt[:600]
        d["rawStart"] = r.content[:24].hex()
        delim = max([";", ",", "\t", "|"], key=lambda c: sample.split("\n")[0].count(c))
        rows = list(csv.reader(io.StringIO(txt), delimiter=delim))
        headers = [h.strip() for h in rows[0]] if rows else []
        d.update({"delimiter": delim, "headers": headers, "sampleRows": rows[1:4], "rowCount": max(0, len(rows) - 1)})
        nh = [norm(h) for h in headers]
        colmap = {}
        for field, syns in AFM_COLS.items():
            for s in syns:  # correspondance exacte d'abord, puis partielle
                if s in nh and nh.index(s) not in colmap.values():
                    colmap[field] = nh.index(s)
                    break
            if field not in colmap:
                for j, h in enumerate(nh):
                    if j not in colmap.values() and any(f" {s} " in f" {h} " for s in syns if len(s) > 4):
                        colmap[field] = j
                        break
        d["columnMap"] = {k: headers[v] for k, v in colmap.items()}
        since = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()
        kept = 0
        for k, row in enumerate(rows[1:]):
            get = lambda f: (row[colmap[f]].strip() if f in colmap and colmap[f] < len(row) else None)
            tx = iso_date(get("txDate"))
            pub = iso_date(get("published")) or tx
            if not tx or (pub or tx) < since:
                continue
            rid = get("id") or f"{tx}-{norm(get('issuer'))[:30]}-{norm(get('person'))[:30]}-{get('price') or ''}-{get('quantity') or ''}"
            rec = {"registry": "AFM", "country": "NL", "id": re.sub(r"[^A-Za-z0-9_.:-]", "_", rid)[:150], "url": get("url") or "https://www.afm.nl/nl-nl/sector/registers/meldingenregisters/transacties-leidinggevenden-mar19-",
                   "via": "afm.nl", "published": pub, "issuer": get("issuer"), "person": get("person"), "role": get("role"), "isin": get("isin"),
                   "instrument": get("instrument") or "Aandelen", "nature": get("nature"), "txDate": tx, "currency": get("currency"),
                   "quantity": get("quantity"), "price": get("price"), "amount": get("amount"), "place": get("place"), "numberLocale": "auto",
                   "collectedAt": date.today().isoformat()}
            st["records"][f"AFM:{rec['id']}"] = rec
            kept += 1
        complete = all(f in colmap for f in ("isin", "nature", "txDate"))
        src.update({"status": "ok" if complete else "partiel", "rows": d["rowCount"], "kept": kept,
                    "note": None if complete else "export sans ISIN, nature ou date reconnue : format à adapter (voir data/diagnostics/afm.json)"})
        src["lastSuccess"] = date.today().isoformat() if complete else src.get("lastSuccess")
        print(f"AFM : {d['rowCount']} lignes, {kept} dans la fenêtre, colonnes reconnues : {sorted(colmap)}")
    except Exception as e:
        src.update({"status": "echec", "note": "export inaccessible : " + str(e)[:120]})
        d["error"] = repr(e)[:300]
        print("AFM : échec", e)
    try:  # échantillon de l'export XML, souvent plus détaillé, pour adaptation éventuelle
        rx = requests.get(AFM_XML, headers=UA, timeout=60)
        tx, _ = decode(rx.content[:6000])
        d["xmlSample"] = tx[:3000]
    except Exception as e:
        d["xmlError"] = repr(e)[:200]
    st["sources"]["AFM"] = src
    diag("afm", d)


def main():
    st = load_state()
    for name, fn in (("AFM", afm_collect), ("FSMA", fsma_collect)):
        try:
            fn(st)
        except Exception as e:  # une source en panne n'arrête pas les autres
            st["sources"].setdefault(name, {})["status"] = "echec"
            st["sources"][name]["note"] = "erreur inattendue : " + type(e).__name__
            print(name, "erreur", e)
    cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    st["records"] = {k: v for k, v in st["records"].items() if (v.get("txDate") or "9999") >= cutoff}
    st["generated_at"] = now_iso()
    save_json(OUT, st)
    print(f"Déclarations hors France conservées : {len(st['records'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
