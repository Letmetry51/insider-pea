"""
Grain Signal — collecte du matin (GitHub Actions).

Sources : Euronext (blé, colza, maïs ; via terre-net, secours Euronext live), Yahoo Finance (CBOT, canola, gaz TTF, Brent,
EUR/USD), CFTC (positions des fonds, managed money), engrais France (terre-net), prix physiques (terre-net), Banque mondiale
(Pink Sheet mensuel : urée, DAP, potasse, gaz, blé HRW).

Chaque source est indépendante : une source en panne est notée dans data/grain/collecte.json et ne bloque jamais les autres.
Aucune valeur n'est inventée : une donnée non lue reste absente (la page et le comité l'affichent comme « non trouvé »).
Les historiques bruts (cours) restent dans data/grain/prive/ : jamais publiés sur la page, gardés d'un jour à l'autre par le cache.

  python grain_signal/collect.py
"""
import csv
import io
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "data" / "grain"
PRIV = OUT / "prive"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}

MOIS = {"janv": 1, "jan": 1, "janvier": 1, "fevr": 2, "févr": 2, "fev": 2, "fév": 2, "feb": 2, "février": 2, "fevrier": 2,
        "mars": 3, "mar": 3, "avr": 4, "avril": 4, "apr": 4, "mai": 5, "may": 5, "juin": 6, "jun": 6, "juil": 7, "juillet": 7,
        "jul": 7, "aout": 8, "août": 8, "aug": 8, "sept": 9, "sep": 9, "septembre": 9, "oct": 10, "octobre": 10, "nov": 11,
        "novembre": 11, "dec": 12, "déc": 12, "décembre": 12, "decembre": 12}

status = {}


def note(source, ok, detail=""):
    status[source] = {"ok": bool(ok), "detail": str(detail)[:300], "heure": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    print(("OK    " if ok else "ÉCHEC ") + source + (" — " + str(detail)[:200] if detail else ""))


def get(url, **kw):
    last = None
    for i in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 30), **kw)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = type(e).__name__ + ": " + str(e)[:120]
        time.sleep(2 + 3 * i)
    raise RuntimeError(last or "échec")


def num(txt):
    """'613,75€/t' → 613.75 ; '1 234,5' → 1234.5 ; '-7,25 €/t' → -7.25 ; sinon None."""
    if txt is None:
        return None
    t = str(txt).replace("\xa0", " ").replace(" ", " ")
    m = re.search(r"[-+−]?\d{1,3}(?:[ .]\d{3})*(?:,\d+)?|[-+−]?\d+(?:[.,]\d+)?", t)
    if not m:
        return None
    s = m.group(0).replace("−", "-").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def maturity(label):
    """'déc. 2026', 'Déc 26', '12/2026', 'DEC 2026', 'Dec26' → '2026-12' ; sinon None."""
    t = (label or "").strip().lower().replace("\xa0", " ")
    m = re.match(r"^(\d{1,2})\s*/\s*(\d{2,4})$", t)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
    else:
        m = re.match(r"^([a-zéûè]+)\.?\s*[-/]?\s*(\d{2,4})$", t)
        if not m or m.group(1) not in MOIS:
            return None
        mo, y = MOIS[m.group(1)], int(m.group(2))
    if y < 100:
        y += 2000
    if not (1 <= mo <= 12 and 2000 <= y <= 2100):
        return None
    return f"{y}-{mo:02d}"


def tables(html):
    """Toutes les tables HTML : liste de lignes, chaque ligne = liste de textes de cellules (en-têtes compris)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tb in soup.find_all("table"):
        rows = []
        for tr in tb.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            out.append(rows)
    return out


def parse_futures(html):
    """Échéances et prix de compensation d'une page de cotations à terme (terre-net ou Euronext live)."""
    found = {}
    for rows in tables(html):
        idx = None
        for r in rows:
            low = [c.lower() for c in r]
            for key in ("compensation", "settl", "settlement"):
                hit = [i for i, c in enumerate(low) if key in c]
                if hit:
                    idx = hit[0]
                    break
            mat = maturity(r[0]) if r else None
            if not mat:
                continue
            val = None
            if idx is not None and idx < len(r):
                val = num(r[idx])
            if val is None:  # pas de colonne repérée : dernier nombre plausible de la ligne
                vals = [num(c) for c in r[1:]]
                vals = [v for v in vals if v is not None and 50 < v < 2000]
                val = vals[-1] if vals else None
            if val is not None and 50 < val < 2000 and mat not in found:
                found[mat] = val
    return found


def parse_date_fr(html, default):
    """Date de la séance : 'Mis à jour le : 6 novembre 2026' ou '06 novembre' (année supposée la plus récente)."""
    text = re.sub(r"<[^>]+>", " ", html)
    m = re.search(r"Mis à jour le\s*:?\s*(\d{1,2})\s+([a-zéûè]+)\s+(\d{4})", text, re.I)
    if m and m.group(2).lower() in MOIS:
        return date(int(m.group(3)), MOIS[m.group(2).lower()], int(m.group(1)))
    return default


def day_month(text, today):
    """'06 novembre' (titre d'une table) → date ; année : la plus récente qui ne dépasse pas aujourd'hui. Sinon None."""
    ms = list(re.finditer(r"\b(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\b",
                          text or "", re.I))
    if not ms:
        return None
    m = ms[-1]  # la date la plus proche de la table
    mo, d = MOIS[m.group(2).lower()], int(m.group(1))
    for y in (today.year, today.year - 1):
        try:
            cand = date(y, mo, d)
        except ValueError:
            return None
        if cand <= today:
            return cand
    return None


def parse_place_prices(html):
    """Tables « Place | (Échéance) | Cotation | Variation » : [{'place','echeance','prix','variation','titre'}]."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tb in soup.find_all("table"):
        # textes juste avant la table (titre et date : « 06 novembre », « standard Récolte : 2026 »…)
        before = [s.strip() for s in tb.find_all_previous(string=True, limit=25) if s.strip()]
        caption = " ".join(reversed(before))[-200:]
        head, rows = None, []
        for tr in tb.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            low = [c.lower() for c in cells]
            if any("cotation" in c for c in low) and head is None:
                head = low
                continue
            rows.append(cells)
        if not head:
            continue
        ic = next((i for i, c in enumerate(head) if c.startswith("cotation") and "précédente" not in c and "precedente" not in c), None)
        ie = next((i for i, c in enumerate(head) if "échéance" in c or "echeance" in c), None)
        iv = next((i for i, c in enumerate(head) if "variation" in c), None)
        if ic is None:
            continue
        for r in rows:
            if ic >= len(r):
                continue
            p = num(r[ic])
            if p is None:
                continue
            place = re.split(r"Contenu réservé|Abonnez|S'abonner", r[0])[0].strip()
            out.append({"place": place[:60], "echeance": (r[ie] if ie is not None and ie < len(r) else "")[:30], "prix": p,
                        "variation": num(r[iv]) if iv is not None and iv < len(r) else None, "titre": caption})
    return out


# --------------------------------------------------------------------------------------------------- stockage
def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def seed(name):
    """Premier calcul : historiques de départ (grain_signal/seed/) copiés dans data/grain/prive/."""
    dst = PRIV / name
    if not dst.exists() and (HERE / "seed" / name).exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((HERE / "seed" / name).read_bytes())
        print("Historique de départ copié :", name)
    return dst


# --------------------------------------------------------------------------------------------------- collecteurs
def collect_euronext(today):
    path = seed("euronext.csv")
    rows = read_csv(path)
    have = {(r["date"], r["product"], r["maturity"]) for r in rows}
    added = 0
    for prod, c in CFG["euronext"].items():
        got, src, err = {}, None, []
        for label, url in (("terre-net", c["terrenet"]), ("Euronext live", c["secours"])):
            try:
                html = get(url).text
                got = parse_futures(html)
                d = parse_date_fr(html, today) if label == "terre-net" else today
                if len(got) >= 2:
                    src = label
                    break
                err.append(f"{label} : {len(got)} échéance(s) lue(s)")
            except Exception as e:  # noqa: BLE001
                err.append(f"{label} : {e}")
        if not src:
            note("euronext_" + prod, False, " ; ".join(err))
            continue
        d = d.isoformat()
        for mat, v in got.items():
            key = (d, prod, mat)
            if key in have:
                for r in rows:
                    if (r["date"], r["product"], r["maturity"]) == key:
                        r["settle"] = v
            else:
                rows.append({"date": d, "product": prod, "maturity": mat, "settle": v})
                have.add(key)
                added += 1
        note("euronext_" + prod, True, f"{src}, séance du {d}, {len(got)} échéances")
    rows.sort(key=lambda r: (r["product"], r["date"], r["maturity"]))
    write_csv(path, rows, ["date", "product", "maturity", "settle"])
    print(f"Euronext : {added} nouvelles cotations, {len(rows)} au total")


def yahoo_series(tk):
    """Clôtures journalières sur 2 ans : yfinance (gère les jetons de Yahoo, comme Euro Signal), sinon accès direct."""
    errs = []
    try:
        import yfinance as yf

        h = yf.Ticker(tk).history(period="2y", interval="1d", auto_adjust=False)
        ser = {i.date().isoformat(): round(float(v), 4) for i, v in h["Close"].dropna().items()}
        if len(ser) >= 50:
            return ser, "yfinance"
        errs.append(f"yfinance : {len(ser)} séances")
    except Exception as e:  # noqa: BLE001
        errs.append(f"yfinance : {type(e).__name__} {str(e)[:80]}")
    for host in ("query2", "query1"):
        try:
            j = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{tk}?range=2y&interval=1d").json()
            res = j["chart"]["result"][0]
            ser = {}
            for t, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []):
                if c is not None:
                    ser[datetime.fromtimestamp(t, timezone.utc).date().isoformat()] = round(float(c), 4)
            if len(ser) >= 50:
                return ser, host
            errs.append(f"{host} : {len(ser)} séances")
        except Exception as e:  # noqa: BLE001
            errs.append(f"{host} : {e}")
    raise RuntimeError(" ; ".join(errs))


def collect_yahoo():
    path = PRIV / "yahoo.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out = dict(old)
    for tk, name in CFG["yahoo"].items():
        try:
            ser, src = yahoo_series(tk)
            out[tk] = {"nom": name, "serie": dict(sorted(ser.items()))}
            note("yahoo_" + tk, True, f"{len(ser)} séances, dernière {max(ser)} ({src})")
        except Exception as e:  # noqa: BLE001
            note("yahoo_" + tk, False, f"{e} (historique précédent gardé)" if tk in old else e)
        time.sleep(1)
    save_json(path, out)


def collect_cftc():
    path = PRIV / "cftc.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out = dict(old)
    for code, c in CFG["cftc"]["marches"].items():
        try:
            params = {"cftc_contract_market_code": code, "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": "170",
                      "$select": "report_date_as_yyyy_mm_dd,m_money_positions_long_all,m_money_positions_short_all,open_interest_all"}
            j = get(CFG["cftc"]["dataset"], params=params).json()
            ser = []
            for r in j:
                try:
                    ser.append({"date": r["report_date_as_yyyy_mm_dd"][:10], "long": int(float(r["m_money_positions_long_all"])),
                                "short": int(float(r["m_money_positions_short_all"])), "oi": int(float(r["open_interest_all"]))})
                except (KeyError, ValueError, TypeError):
                    continue
            if len(ser) < 20:
                raise RuntimeError(f"{len(ser)} rapports seulement")
            ser.sort(key=lambda x: x["date"])
            out[code] = {"nom": c["nom"], "serie": ser}
            note("cftc_" + code, True, f"{len(ser)} rapports, dernier {ser[-1]['date']}")
        except Exception as e:  # noqa: BLE001
            note("cftc_" + code, False, e)
    save_json(path, out)


def collect_engrais(today):
    path = seed("fert_fr.csv")
    rows = read_csv(path)
    for prod, c in CFG["engraisFrance"].items():
        try:
            html = get(c["url"]).text
            items = parse_place_prices(html)
            if not items:
                raise RuntimeError("aucun prix lu")
            p = items[0]["prix"]
            if not (100 < p < 3000):
                raise RuntimeError(f"prix invraisemblable : {p}")
            d = (day_month(items[0]["titre"], today) or today).isoformat()
            rows = [r for r in rows if not (r["date"] == d and r["product"] == prod)]
            rows.append({"date": d, "product": prod, "price": p, "source": "terre-net, " + items[0]["place"]})
            note("engrais_" + prod, True, f"{p} ({items[0]['place']}, cotation du {d})")
        except Exception as e:  # noqa: BLE001
            note("engrais_" + prod, False, e)
    rows.sort(key=lambda r: (r["date"], r["product"]))
    write_csv(path, rows, ["date", "product", "price", "source"])


def collect_physique():
    snap = {}
    for k, url in CFG["physique"].items():
        try:
            items = parse_place_prices(get(url).text)
            if not items:
                raise RuntimeError("aucun prix lu")
            snap[k] = items[:12]
            note("physique_" + k, True, f"{len(items)} places")
        except Exception as e:  # noqa: BLE001
            note("physique_" + k, False, e)
    if snap:  # historique quotidien (escourgeon et orge de printemps n'ont pas de marché à terme : leur seule série de prix)
        hp = seed("physique_hist.csv")
        hist = read_csv(hp)
        today = datetime.now(timezone.utc).date()
        for k, items in snap.items():
            for it in items:
                d = (day_month(it["titre"], today) or today).isoformat()
                key = (d, k, it["place"], it["titre"][-60:])
                hist = [h for h in hist if (h["date"], h["page"], h["place"], h["titre"]) != key]
                hist.append({"date": d, "page": k, "place": it["place"], "echeance": it["echeance"], "titre": it["titre"][-60:], "prix": it["prix"]})
        hist.sort(key=lambda h: (h["date"], h["page"], h["place"]))
        write_csv(hp, hist, ["date", "page", "place", "echeance", "titre", "prix"])
        old_path = OUT / "physique.json"
        old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {}
        old.update(snap)
        save_json(old_path, old)


WB_COLS = {"natural gas, europe": "gas_eu", "urea": "urea", "dap": "dap", "potassium chloride": "kcl", "wheat, us hrw": "wheat_hrw",
           "maize": "maize"}


def collect_banque_mondiale():
    path = seed("wb_monthly.csv")
    meta_p = PRIV / "wb_meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    last = meta.get("telecharge")
    if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days < CFG["banqueMondiale"]["joursEntreTelechargements"]:
        note("banque_mondiale", True, f"déjà téléchargé le {last[:10]}")
        return
    try:
        page = get(CFG["banqueMondiale"]["page"]).text
        m = re.search(r"https?://[^\"'\s>]*CMO-Historical-Data-Monthly\.xlsx", page)
        if not m:
            raise RuntimeError("lien du fichier mensuel introuvable sur la page")
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(get(m.group(0), timeout=90).content), read_only=True, data_only=True)
        ws = wb["Monthly Prices"]
        grid = list(ws.iter_rows(values_only=True))
        hi = next(i for i, r in enumerate(grid) if r and any(isinstance(c, str) and c.strip().lower().startswith("crude oil, brent") for c in r))
        head = [str(c or "").strip().lower().rstrip("* ").strip() for c in grid[hi]]
        idx = {}
        for i, h in enumerate(head):
            for k, v in WB_COLS.items():
                if h == k and v not in idx:
                    idx[v] = i
        if len(idx) < 5:
            raise RuntimeError(f"colonnes trouvées : {sorted(idx)}")
        rows = []
        for r in grid[hi + 1:]:
            if not r or not isinstance(r[0], str) or not re.match(r"^\d{4}M\d{2}$", r[0]):
                continue
            mo = r[0].replace("M", "-")
            if mo < "2000-01":
                continue
            row = {"month": mo}
            for k, i in idx.items():
                v = r[i]
                row[k] = float(v) if isinstance(v, (int, float)) else ""
            rows.append(row)
        if len(rows) < 200:
            raise RuntimeError(f"{len(rows)} mois seulement")
        write_csv(path, rows, ["month", "gas_eu", "urea", "dap", "kcl", "wheat_hrw", "maize"])
        meta = {"telecharge": datetime.now(timezone.utc).isoformat(timespec="seconds"), "url": m.group(0), "dernier_mois": rows[-1]["month"]}
        save_json(meta_p, meta)
        note("banque_mondiale", True, f"{len(rows)} mois, dernier {rows[-1]['month']}")
    except Exception as e:  # noqa: BLE001
        note("banque_mondiale", False, f"{e} (fichier précédent gardé)")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PRIV.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    for fn in (lambda: collect_euronext(today), collect_yahoo, collect_cftc, lambda: collect_engrais(today), collect_physique,
               collect_banque_mondiale):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            note("collecteur", False, f"{type(e).__name__}: {e}")
    save_json(OUT / "collecte.json", {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": status})
    ok = sum(1 for s in status.values() if s["ok"])
    print(f"Collecte : {ok}/{len(status)} sources lues")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
