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
import os
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
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
    m = re.search(r"[-+−]?\d{1,3}(?:[ .]\d{3})+(?:,\d+)?(?![\d.])|[-+−]?\d+(?:[.,]\d+)?", t)
    if not m:
        return None
    s = m.group(0).replace("−", "-").replace(" ", "")
    if "," in s:  # format français : 1.234,5 ou 1 234,5
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})+", s):  # 1.234 ou 1.234.567 : séparateur de milliers
        s = s.replace(".", "")
    # sinon « 225.50 » : point décimal (pages en anglais), gardé tel quel
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
            # pas de colonne « compensation » repérée : on n'invente pas, l'échéance est ignorée (la source sera notée en échec)
            if val is not None and 50 < val < 2000 and mat not in found:
                found[mat] = val
    return found


def parse_date_fr(html, default):
    """Date de la séance : 'Mis à jour le : 6 novembre 2026' ou '06 novembre' (année supposée la plus récente)."""
    text = re.sub(r"<[^>]+>", " ", html)
    m = re.search(r"Mis à jour le\s*:?\s*(\d{1,2})\s+([a-zéûè]+)\s+(\d{4})", text, re.I)
    if m and m.group(2).lower() in MOIS:
        return date(int(m.group(3)), MOIS[m.group(2).lower()], int(m.group(1)))
    m = re.search(r"Mis à jour le\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})", text, re.I)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return default


def seance_precedente(today):
    """Le calcul tourne le matin : sans date lue sur la page, la cotation est celle du dernier jour ouvré avant aujourd'hui."""
    d = today - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def date_seance(parsed, now=None):
    """Date de cotation retenue : celle lue sur la page si elle est plausible, sinon la dernière séance close.
    Avant 17 h UTC, la séance du jour n'est pas close (clôtures Euronext vers 17 h 30 UTC) : une date du jour est ramenée à la veille."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    sp = seance_precedente(today)
    if parsed is None or parsed > today or parsed.weekday() >= 5:
        return sp if parsed is None or parsed > today else min(parsed, sp)
    if parsed == today and now.hour < 17:
        return sp
    return parsed


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
        before = [x.strip() for x in tb.find_all_previous(string=True, limit=40)
                  if x.strip() and x.parent is not None and x.parent.name not in ("script", "style", "noscript")
                  and not re.search(r"[{};]|function|window\.|var |=>", x)][:25]
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
                d = date_seance(parse_date_fr(html, None) if label == "terre-net" else None)
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
        # contrôle de vraisemblance : écart de plus de 12 % avec la dernière cotation connue de la même échéance = rejet
        prev = {}
        for r in rows:
            if r["product"] == prod and r["date"] < d:
                prev[r["maturity"]] = float(r["settle"])
        rejet = {m_: v for m_, v in got.items() if m_ in prev and abs(v / prev[m_] - 1) > 0.12}
        got = {m_: v for m_, v in got.items() if m_ not in rejet}
        if rejet:
            err.append("rejetées (écart > 12 % avec la veille) : " + ", ".join(f"{m_} {v:g}" for m_, v in rejet.items()))
        if len(got) < 2:
            note("euronext_" + prod, False, " ; ".join(err))
            continue
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
        note("euronext_" + prod, True, f"{src}, séance du {d}, {len(got)} échéances" + (f" ; {err[-1]}" if rejet else ""))
    rows.sort(key=lambda r: (r["product"], r["date"], r["maturity"]))
    write_csv(path, rows, ["date", "product", "maturity", "settle"])
    print(f"Euronext : {added} nouvelles cotations, {len(rows)} au total")


def yahoo_series(tk, recent_only=False, mini=None):
    """Clôtures journalières sur 5 ans : yfinance (gère les jetons de Yahoo, comme Euro Signal), sinon accès direct."""
    errs = []
    # Yahoo renvoie parfois une seule séance (gaz TTF sur 5 ans) ou refuse (429) : période plus courte, puis nouvel essai
    # historique déjà en mémoire : seules les dernières semaines sont demandées (requête légère, moins de refus de Yahoo)
    periods, mini_ = (("1mo", "3mo"), 5) if recent_only else (("5y", "2y", "1y"), 50)
    mini = mini or mini_
    for attempt, period in enumerate(periods):
        try:
            import yfinance as yf

            h = yf.Ticker(tk).history(period=period, interval="1d", auto_adjust=False)
            # date de la bourse (index yfinance dans son fuseau) ; la barre du jour, pas encore close, est écartée
            ser = {i.date().isoformat(): round(float(v), 4) for i, v in h["Close"].dropna().items() if i.date() < date.today()}
            if len(ser) >= mini:
                return ser, f"yfinance {period}"
            errs.append(f"yfinance {period} : {len(ser)} séances")
        except Exception as e:  # noqa: BLE001
            errs.append(f"yfinance : {type(e).__name__} {str(e)[:80]}")
        time.sleep(5 * (attempt + 1))
    for host in ("query2", "query1"):
        try:
            j = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{tk}?range={'3mo' if recent_only else '5y'}&interval=1d").json()
            res = j["chart"]["result"][0]
            ser = {}
            off = int((res.get("meta") or {}).get("gmtoffset") or 0)  # décalage horaire de la bourse
            for t, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []):
                if c is not None:
                    dd = datetime.fromtimestamp(t + off, timezone.utc).date()
                    if dd < datetime.now(timezone.utc).date():
                        ser[dd.isoformat()] = round(float(c), 4)
            if len(ser) >= mini:
                return ser, host
            errs.append(f"{host} : {len(ser)} séances")
        except Exception as e:  # noqa: BLE001
            errs.append(f"{host} : {e}")
    raise RuntimeError(" ; ".join(errs))


def collect_yahoo():
    path = PRIV / "yahoo.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out = dict(old)
    pending = list(CFG["yahoo"].items())
    t0 = time.monotonic()
    for tour in (1, 2):  # second tour, après une pause, pour les séries refusées au premier (Yahoo limite les requêtes)
        failed = []
        for tk, name in pending:
            prev = ((old.get(tk) or {}).get("serie")) or {}
            if time.monotonic() - t0 > 420:  # 7 minutes : Yahoo refuse tout, les autres sources doivent passer
                failed.append((tk, name))
                note("yahoo_" + tk, False, "Yahoo trop lent ou refuse (historique précédent gardé)")
                continue
            have = len(prev) >= 250  # un an d'historique déjà gardé : mise à jour légère
            try:
                # historique gardé : une seule séance nouvelle suffit (Yahoo ne renvoie parfois que la dernière séance du gaz TTF)
                ser, src = yahoo_series(tk, recent_only=have, mini=1 if have else None)
                merged = dict(prev)
                merged.update(ser)
                out[tk] = {"nom": name, "serie": dict(sorted(merged.items())[-1400:])}
                last = max(merged)
                if (datetime.now(timezone.utc).date() - date.fromisoformat(last)).days > 6:
                    raise RuntimeError(f"série figée au {last}")
                note("yahoo_" + tk, True, f"{len(merged)} séances, dernière {last} ({src}{', mise à jour' if have else ''})")
            except Exception as e:  # noqa: BLE001
                failed.append((tk, name))
                note("yahoo_" + tk, False, f"{e} (historique précédent gardé)" if tk in old else e)
            time.sleep(3)
        if not failed or time.monotonic() - t0 > 420:
            break
        pending = failed
        if tour == 1:
            time.sleep(60)
    save_json(path, out)


LONG_TICKERS = ("ZW=F", "ZC=F", "EURUSD=X", "BZ=F")  # blé, maïs, euro-dollar, Brent : tout l'historique de Yahoo


def collect_cftc_long():
    """Positions des fonds (managed money, CFTC) depuis 2006 pour le blé et le maïs, une fois par semaine : backtest de la note des
    fonds."""
    path = PRIV / "cftc_long.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    stamp = old.get("_telecharge")
    if stamp and (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).days < 7:
        note("cftc_historique", True, f"déjà téléchargé le {stamp[:10]}")
        return
    out, ok = dict(old), 0
    codes = [c for c, m in CFG["cftc"]["marches"].items() if m.get("culture") in ("ble", "mais")]
    for code in codes:
        try:
            params = {"cftc_contract_market_code": code, "$order": "report_date_as_yyyy_mm_dd ASC", "$limit": "5000",
                      "$select": "report_date_as_yyyy_mm_dd,m_money_positions_long_all,m_money_positions_short_all"}
            j = get(CFG["cftc"]["dataset"], params=params, timeout=90).json()
            ser = []
            for r in j:
                try:
                    ser.append({"date": r["report_date_as_yyyy_mm_dd"][:10], "long": int(float(r["m_money_positions_long_all"])),
                                "short": int(float(r["m_money_positions_short_all"]))})
                except (KeyError, ValueError, TypeError):
                    continue
            if len(ser) < 500:
                raise RuntimeError(f"{len(ser)} rapports seulement")
            out[code] = {"culture": CFG["cftc"]["marches"][code]["culture"], "nom": CFG["cftc"]["marches"][code]["nom"], "serie": ser}
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"CFTC historique {code} : {e}")
    if ok == len(codes):
        out["_telecharge"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_json(path, out)
    note("cftc_historique", ok == len(codes), f"{ok}/{len(codes)} marchés" + (f", depuis {min(v['serie'][0]['date'] for k, v in out.items() if not k.startswith('_'))}" if ok else ""))


def collect_yahoo_long():
    """Historique complet (depuis 2000) du blé et du maïs de Chicago et de l'EUR/USD, pour le backtest. Une fois par semaine."""
    path = PRIV / "yahoo_long.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    stamp = old.get("_telecharge")
    if stamp and (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).days < 7 and "BZ=F" in old:
        note("yahoo_historique_long", True, f"déjà téléchargé le {stamp[:10]}")
        return
    out, ok = dict(old), 0
    try:
        import yfinance as yf
    except ImportError as e:
        note("yahoo_historique_long", False, e)
        return
    for tk in LONG_TICKERS:
        try:
            h = yf.Ticker(tk).history(period="max", interval="1d", auto_adjust=False)
            ser = {i.date().isoformat(): round(float(v), 4) for i, v in h["Close"].dropna().items() if i.date() < date.today()}
            if len(ser) < 2000:
                raise RuntimeError(f"{len(ser)} séances")
            out[tk] = {"serie": ser}
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"Historique long {tk} : {e}")
        time.sleep(5)
    n = len(LONG_TICKERS)
    if ok == n:
        out["_telecharge"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_json(path, out)
    note("yahoo_historique_long", ok == n, f"{ok}/{n} séries complètes" + (" (historique précédent gardé pour les autres)" if ok < n else ""))


STATS_URL = "https://live.euronext.com/sites/default/files/statistics/derivatives/daily/2017/Derivatives%20{:%Y%m%d}.xlsx"
HISTO_DEBUT = date(2019, 11, 1)  # premiers fichiers statistiques quotidiens publiés (2018 : accès refusé)


def stats_rows(content, d):
    """Fichier statistique quotidien d'Euronext (feuille « Series ») → prix de compensation des contrats à terme blé, colza,
    maïs, par échéance. Les contrats « T » (Trading at Settlement) et les prix nuls sont écartés. Échéance déduite du dernier jour
    de cotation et de la règle du contrat (blé et maïs : dans le mois de l'échéance ; colza : dernier jour du mois précédent)."""
    try:
        from python_calamine import CalamineWorkbook

        rows = CalamineWorkbook.from_filelike(io.BytesIO(content)).get_sheet_by_name("Series").to_python()
    except ImportError:  # secours plus lent
        import openpyxl

        rows = list(openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)["Series"].iter_rows(values_only=True))
    return parse_series(rows, d)


def parse_series(rows, d):
    """Lignes de la feuille « Series » (anciens et nouveaux formats d'Euronext) → prix de compensation par échéance."""
    head = next((r for r in rows if r and r[0] == "Date"), None)
    if not head:
        raise RuntimeError("feuille Series sans entête")
    hd = [str(c or "").replace("\n", " ").strip() for c in head]
    ic, ia, il, isp = (hd.index(k) for k in ("Contract Code", "AMR", "Last Trading Date", "Settlement Price"))
    out = []
    for r in rows:
        if len(r) <= isp or r[ic] not in CFG["euronext"]:
            continue
        code, amr = r[ic], str(r[ia] or "")
        if not amr.startswith("YF" + code) or amr[len(code) + 2:len(code) + 3] == "T":
            continue  # pas un contrat à terme standard (TAS, options)
        try:
            sp, ltd = float(r[isp] or 0), r[il]
        except (TypeError, ValueError):
            continue
        if sp <= 0 or not hasattr(ltd, "year"):
            continue
        y, m = ltd.year, ltd.month
        if CFG["euronext"][code]["expiration"]["regle"] != "jour":  # colza : expire le mois précédent l'échéance
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append({"date": d.isoformat(), "product": code, "maturity": f"{y}-{m:02d}", "settle": round(sp, 4)})
    return out


def stats_jour(k):
    """Une séance (AAAA-MM-JJ) : ("ok", lignes) | ("absent", None) | ("erreur", message). Fonction de premier niveau : exécutée
    en parallèle dans des processus séparés (téléchargement et lecture du fichier de 10 à 33 Mo)."""
    d = date.fromisoformat(k)
    try:
        r = requests.get(STATS_URL.format(d), headers=UA, timeout=60)
    except Exception as e:  # noqa: BLE001
        return "erreur", type(e).__name__
    if r.status_code in (403, 404):
        return "absent", None
    if r.status_code != 200 or r.content[:2] != b"PK":
        return "erreur", f"HTTP {r.status_code}"
    try:
        return "ok", stats_rows(r.content, d)
    except Exception as e:  # noqa: BLE001
        return "erreur", str(e)[:120]


def collect_euronext_histo(today, budget=None, workers=None):
    """Historique officiel d'Euronext depuis novembre 2019 (fichiers statistiques quotidiens publics, un par séance), repris du plus
    récent au plus ancien dans la limite de `budget` secondes (8 minutes ; GS_HISTO_BUDGET pour un rattrapage), plusieurs fichiers
    à la fois ; contrôle croisé avec les prix lus sur terre-net."""
    budget = budget or int(os.environ.get("GS_HISTO_BUDGET") or 480)
    workers = workers or int(os.environ.get("GS_HISTO_WORKERS") or 4)
    st_path = PRIV / "euronext_histo.json"
    st = json.loads(st_path.read_text(encoding="utf-8")) if st_path.exists() else {}
    faits = set(st.get("faits") or [])
    path = seed("euronext.csv")
    rows = read_csv(path)
    have = {(r["date"], r["product"], r["maturity"]): r for r in rows}
    t0, lus, absents, ecarts, err = time.monotonic(), 0, 0, [], None
    todo, d = [], today - timedelta(days=1)
    while d >= HISTO_DEBUT:
        if d.weekday() < 5 and d.isoformat() not in faits:
            todo.append(d.isoformat())
        d -= timedelta(days=1)
    pool = None
    if workers > 1 and len(todo) > 1:
        from concurrent.futures import ProcessPoolExecutor

        pool = ProcessPoolExecutor(max_workers=workers)
    try:
        for i in range(0, len(todo), max(1, workers)):
            if time.monotonic() - t0 > budget:
                break
            lot = todo[i:i + max(1, workers)]
            res = list(pool.map(stats_jour, lot)) if pool else [stats_jour(k) for k in lot]
            for k, (etat, val) in zip(lot, res):
                if etat == "absent":
                    if (today - date.fromisoformat(k)).days > 7:  # jour férié ; fichier récent pas encore publié : redemandé demain
                        faits.add(k)
                        absents += 1
                elif etat == "ok":
                    for x in val:
                        key = (x["date"], x["product"], x["maturity"])
                        old = have.get(key)
                        if old is None:
                            rows.append(x)
                            have[key] = x
                        elif abs(float(old["settle"]) - x["settle"]) > 0.001:
                            ecarts.append(f"{k} {x['product']} {x['maturity']} : terre-net {old['settle']} / Euronext {x['settle']}")
                    faits.add(k)
                    lus += 1
                else:
                    err = f"{k} : {val}"
            if err:
                break  # Euronext injoignable ou fichier illisible : repris au prochain calcul
    finally:
        if pool:
            pool.shutdown(cancel_futures=True)
    rows.sort(key=lambda r: (r["product"], r["date"], r["maturity"]))
    write_csv(path, rows, ["date", "product", "maturity", "settle"])
    save_json(st_path, {"faits": sorted(faits)})
    total = sum(1 for x in faits if x >= HISTO_DEBUT.isoformat())
    reste = sum(1 for k in todo if k not in faits)
    detail = (f"{lus} séance(s) lue(s), {absents} sans fichier en {time.monotonic() - t0:.0f} s ; {total} jours traités depuis le "
              f"{HISTO_DEBUT:%d/%m/%Y}, {reste} restant(s)")
    note("euronext_historique", err is None, detail + (f" ; arrêt : {err}" if err else ""))
    if ecarts:  # même séance, même échéance : terre-net doit donner le prix officiel d'Euronext
        note("controle_terre_net", False, f"{len(ecarts)} écart(s) avec Euronext : " + " ; ".join(ecarts[:3]))
    elif lus:
        note("controle_terre_net", True, "prix terre-net identiques aux fichiers officiels d'Euronext")


COT_URL = "https://live.euronext.com/sites/default/files/commodities_reporting/{y}/{m:02d}/{d:02d}/en/cdwpr_{p}_{y}{m:02d}{d:02d}.pdf"


def cot_num(cell):
    t = (cell or "").replace("\xa0", " ").replace("\u202f", " ").strip()
    if not re.fullmatch(r"-?\d{1,3}(?: \d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", t):
        return None
    return float(t.replace(" ", ""))


def parse_cot_pdf(content):
    """Rapport hebdomadaire Euronext (MiFID II) : positions des fonds d'investissement et des opérateurs commerciaux.
    Colonnes (long, court) : établissements de crédit, fonds d'investissement, autres financiers, commerciaux, quotas CO2.
    Contrôle : pour chaque colonne, total = couverture + autres, sinon le rapport est rejeté (rien n'est deviné)."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join(pg.extract_text() or "" for pg in pdf.pages)
        rows = []
        for pg in pdf.pages:
            for tb in pg.extract_tables():
                rows += [[(c or "").replace("\n", " ").strip() for c in r] for r in tb]
    return parse_cot_rows(text, rows)


def parse_cot_rows(text, rows):
    """Lignes du tableau (cellules texte) → positions ; séparé de la lecture du PDF pour être testé sans pdfplumber."""
    m = re.search(r"Report date\D{0,20}(\d{2})/(\d{2})/(\d{4})", text, re.I) or re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if not m:
        raise RuntimeError("date du rapport introuvable")
    rdate = date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    found = {}
    for r in rows:
        label = " ".join(c for c in r if cot_num(c) is None).lower()
        vals = [cot_num(c) for c in r if cot_num(c) is not None]
        if len(vals) < 10:
            continue
        key = "rr" if "risk" in label else "autres" if "other" in label else "total" if "total" in label else None
        if key and key not in found:  # premier bloc = nombre de positions (lots)
            found[key] = vals[-10:]
    if len(found) < 3:
        raise RuntimeError(f"tableau des positions introuvable ({sorted(found)})")
    if any(abs(found["total"][i] - found["rr"][i] - found["autres"][i]) > 1 for i in range(10)):
        raise RuntimeError("contrôle total = couverture + autres non vérifié")
    t = found["total"]
    return {"date": rdate, "fonds_long": round(t[2]), "fonds_short": round(t[3]), "net": round(t[2] - t[3]),
            "commerciaux_net": round(t[6] - t[7])}


def fetch_pdf(url):
    """Contenu du PDF ; "absent" si Euronext répond qu'il n'existe pas (404) ; None si erreur (réseau, 5xx, réponse anormale) :
    une erreur n'est jamais prise pour une semaine sans rapport (elle sera réessayée)."""
    try:
        r = requests.get(url, headers=UA, timeout=20)
    except Exception:  # noqa: BLE001
        return None
    if r.status_code == 200 and r.content[:4] == b"%PDF":
        return r.content
    return "absent" if r.status_code in (403, 404, 410) else None


def collect_cot_euronext(today, budget=150):
    """Positions des fonds sur Euronext (blé, colza, maïs), rapport publié le mercredi (mardi ou jeudi en semaine fériée).
    Historique rattrapé progressivement (6 semaines par calcul, jusqu'à 3 ans), dans la limite de `budget` secondes."""
    path = PRIV / "cot_euronext.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    t0 = time.monotonic()
    for prod in ("EBM", "ECO", "EMA"):
        cur = data.get(prod) if isinstance(data.get(prod), dict) else {}
        serie = [x for x in (cur.get("serie") or []) if isinstance(x, dict) and x.get("publie")]
        absents = set(cur.get("absents") or [])  # semaines déjà cherchées sans rapport (avant le début de la publication)
        pubs = {x["publie"] for x in serie}
        nouveaux, err_recent, err_histo = 0, None, 0

        def essai(d):
            """(rapport trouvé, nouveau rapport lu, erreur de lecture éventuelle) pour cette date de publication."""
            if d.isoformat() in pubs:
                return True, False, None
            pdf = fetch_pdf(COT_URL.format(y=d.year, m=d.month, d=d.day, p=prod))
            if pdf is None:
                raise ConnectionError(f"Euronext injoignable ({d})")
            if pdf == "absent":
                return False, False, None
            try:
                rec = parse_cot_pdf(pdf)
            except Exception as e:  # noqa: BLE001
                return True, False, f"{d} : {e}"
            rec["publie"] = d.isoformat()
            pubs.add(d.isoformat())
            if rec["date"] in {x["date"] for x in serie}:  # même semaine de positions déjà lue (rapport republié)
                return True, False, None
            serie.append(rec)
            return True, True, None

        last = max(pubs) if pubs else None
        try:
            if not last or (today - date.fromisoformat(last)).days >= 6:
                for back in range(14):  # dernier rapport publié (mardi, mercredi ou jeudi)
                    d = today - timedelta(days=back)
                    if d.weekday() in (1, 2, 3):
                        found, neuf, err_recent = essai(d)
                        if found:
                            nouveaux += neuf
                            break
        except ConnectionError as ex:
            err_recent = str(ex)
        if pubs and (today - date.fromisoformat(max(pubs))).days > 10 and not err_recent:
            err_recent = f"aucun rapport publié depuis le {max(pubs)}"  # source muette : notée en panne (alerte au 2e jour)
        avant_debut = sum(1 for a in absents if pubs and a < min(pubs))
        if pubs and len(serie) < 156 and avant_debut < 8 and not err_recent:  # 8 semaines vides : début de la publication atteint
            first = date.fromisoformat(min(pubs | absents))
            first += timedelta(days=2 - first.weekday())  # mercredi de la même semaine (rapport publié mardi ou jeudi en semaine fériée)
            try:
                for k in range(1, 7):
                    if time.monotonic() - t0 > budget:
                        break
                    wed = first - timedelta(weeks=k)
                    for dd in (0, 1, -1):
                        found, neuf, e = essai(wed + timedelta(days=dd))
                        if found:
                            err_histo += e is not None
                            nouveaux += neuf
                            break
                    else:
                        absents.add(wed.isoformat())  # trois « absent » d'Euronext : semaine sans rapport (jamais sur une erreur)
            except ConnectionError:
                pass  # Euronext injoignable : rattrapage repris au prochain calcul
        serie.sort(key=lambda x: x["date"])
        data[prod] = {"serie": serie, "absents": sorted(absents)[:40]}
        detail = f"{len(serie)} rapports, dernier au {serie[-1]['date']} (+{nouveaux})" if serie else ""
        if err_histo:
            detail += f", {err_histo} rapport(s) ancien(s) illisible(s)"
        if serie and not err_recent:
            note("cot_euronext_" + prod, True, detail)
        else:
            note("cot_euronext_" + prod, False, err_recent or "aucun rapport trouvé")
    save_json(path, data)


METEO_ARCH = ("https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={a}&end_date={b}"
              "&daily=precipitation_sum,temperature_2m_max&timezone=UTC")
METEO_PREV = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=precipitation_sum,temperature_2m_max"
              "&past_days=10&forecast_days=14&timezone=UTC")


def om_daily(j):
    d = j["daily"]
    return {t: [p, x] for t, p, x in zip(d["time"], d["precipitation_sum"], d["temperature_2m_max"])}


def collect_meteo(today):
    """Pluie et température maximale des zones de production (Open-Meteo) : 11 ans d'observations (une fois par semaine)
    et prévision à 14 jours (chaque jour). Une seule source notée pour toutes les zones (pas dix alertes de panne)."""
    path = PRIV / "meteo.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    ok, errs, perimees = 0, [], []
    for zn, z in CFG["meteo"]["zones"].items():
        cur = data.get(zn) if isinstance(data.get(zn), dict) else {}
        try:
            au = cur.get("archive_au")
            if not au or (today - date.fromisoformat(au)).days >= 7 or len(cur.get("archive") or {}) < 3000:
                url = METEO_ARCH.format(lat=z["lat"], lon=z["lon"], a=(today - timedelta(days=11 * 366)).isoformat(),
                                        b=(today - timedelta(days=6)).isoformat())
                arch = {k: v for k, v in om_daily(get(url).json()).items() if v[0] is not None}
                if len(arch) < 3000:
                    raise RuntimeError(f"archive de {len(arch)} jours")
                cur.update(archive=arch, archive_au=today.isoformat())
        except Exception as e:  # noqa: BLE001
            errs.append(f"{zn} (archive) : {str(e)[:70]}")  # archive de la semaine précédente gardée (moins de 14 jours : sans effet)
        try:
            cur.update(prevision=om_daily(get(METEO_PREV.format(lat=z["lat"], lon=z["lon"])).json()), prevision_au=today.isoformat())
        except Exception as e:  # noqa: BLE001
            errs.append(f"{zn} (prévision) : {str(e)[:70]}")
        # zone utilisable : archive de moins de 14 jours et prévision de moins de 3 jours
        def recent(k, jours):
            try:
                return (today - date.fromisoformat(cur.get(k, ""))).days < jours
            except ValueError:
                return False
        if recent("archive_au", 14) and recent("prevision_au", 3):
            ok += 1
        else:
            perimees.append(zn)
        data[zn] = cur
        time.sleep(1)
    save_json(path, data)
    n = len(CFG["meteo"]["zones"])
    # en panne dès qu'une zone n'a plus de données fraîches (une seule zone peut peser 45 % d'une culture)
    note("meteo", not perimees, f"{ok}/{n} zones à jour" + (f" ; sans données fraîches : {', '.join(perimees)}" if perimees else "")
         + (" ; " + " ; ".join(errs[:3]) if errs else ""))


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
            d = date_seance(day_month(items[0]["titre"], today)).isoformat()
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
                d = date_seance(day_month(it["titre"], today)).isoformat()
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
    premier = (read_csv(path)[:1] or [{}])[0].get("month", "9999")
    if last and premier < "1961" and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days < CFG["banqueMondiale"]["joursEntreTelechargements"]:
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
            if mo < "1960-01":  # tout l'historique (backtest des achats d'azote) ; le calcul du matin ne lit que les 10 dernières années
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
    for fn in (lambda: collect_euronext(today), lambda: collect_euronext_histo(today), collect_yahoo, collect_yahoo_long, collect_cftc, collect_cftc_long, lambda: collect_cot_euronext(today), lambda: collect_meteo(today), lambda: collect_engrais(today), collect_physique,
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
