"""
Cours de secours (20/10/2026) : la clôture de la dernière séance prise à la bourse elle-même quand Yahoo ne la donne pas.

Pourquoi :
- le calcul du soir démarre souvent tard (GitHub retarde les tâches planifiées de 2 à 6 heures) ; passé minuit à Paris, Yahoo
  n'a pas encore la dernière séance de la plupart des bourses de la zone euro (fiches du 19/10/2026 : 97 % sans la clôture
  du jour, Londres, Lisbonne et Dublin à jour) ;
- si Yahoo coupait l'accès, les places couvertes garderaient des cours frais (alertes de protection, classement).

Sources publiques des bourses, sans clé :
- Euronext (Paris, Amsterdam, Bruxelles, Milan, Lisbonne, Dublin, Oslo) : liste de toutes les actions avec la clôture de la
  dernière séance, en un seul fichier (live.euronext.com) ;
- Nasdaq Nordic (Stockholm, Helsinki, Copenhague) : liste complète de chaque bourse (marché principal et First North,
  api.nasdaq.com), retenue si deux titres très échangés confirment le cours de la séance (historique Nasdaq) ; sinon dix
  jours de cours titre par titre, les plus échangés d'abord, dans une limite de nombre et de temps.
Non couverts : Allemagne, Espagne, Vienne, Londres et Suisse (pas de source gratuite fiable trouvée).

Règles :
- seules les cases vides sont complétées : un cours Yahoo n'est jamais remplacé ;
- une clôture est écartée si sa devise diffère de celle du titre ou si elle sort de la fourchette ÷2 à ×2 du dernier cours
  connu (homonyme, erreur d'unité) ;
- une nouvelle séance n'est ajoutée aux fiches que si au moins 30 titres l'ont (toutes les fiches reçoivent les mêmes dates).

  python scrapers/backup_prices.py      complète data/societes/*.json et data/prices.json (calcul du soir, après Yahoo)
Compteurs : data/diagnostics/backup.json (lus par le contrôle du soir). Numéros des titres chez Nasdaq : data/backup-ids.json.
"""
import csv
import io
import json
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
EURONEXT_LIST = "https://live.euronext.com/en/pd_es/data/stocks/download"
NASDAQ = "https://api.nasdaq.com/api/nordic"
# colonne « Market » de la liste Euronext → suffixe Yahoo (« Euronext Growth Paris », « Oslo Børs », « Euronext Expand Oslo »…)
EURONEXT_PLACES = (("paris", "PA"), ("amsterdam", "AS"), ("brussels", "BR"), ("milan", "MI"), ("lisbon", "LS"),
                   ("dublin", "IR"), ("oslo", "OL"))
NORDIC = {"ST": "SEK", "HE": "EUR", "CO": "DKK"}  # suffixe Yahoo → devise de cotation habituelle
NORDIC_MARKETS = (("STO", "ST"), ("HEL", "HE"), ("CPH", "CO"))  # bourses Nasdaq Nordic → suffixe Yahoo
MIN_NEW_SESSION = 30  # titres au moins pour ajouter une séance aux fiches
NORDIC_MAX = 100  # titres demandés un par un à Nasdaq Nordic au plus par soir (secours du secours : ≈ 5 s par titre)
NORDIC_SECONDS = 240  # et pendant 4 minutes au plus
ID_RETRY_DAYS = 30  # titre introuvable chez Nasdaq : nouvelle recherche après 30 jours


def log(*a):
    print(*a, flush=True)


def num(v):
    """« 1,234.50 », « 8.675 », 12 → nombre positif ; vide, « - », zéro ou illisible → None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = str(v).strip().replace(",", "").replace(" ", "").replace("\xa0", "").replace(" ", "")
        try:
            x = float(s)
        except ValueError:
            return None
    return x if x > 0 and x != float("inf") else None


def snum(v):
    """Nombre signé (« -1.00 », « +0.004 », « 1,234.5 ») ; vide ou illisible → None."""
    s = str(v if v is not None else "").strip().replace(",", "").replace("+", "").replace("\u2212", "-")
    try:
        x = float(s)
    except ValueError:
        return None
    return x if abs(x) != float("inf") and x == x else None


def iso_date(s):
    """« 19/10/2026 » ou « 19/10/2026 17:35 » (Euronext), « 2026-10-19 » (Nasdaq) → « 2026-10-19 » ; sinon None."""
    s = str(s or "").strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    d = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else (re.match(r"\d{4}-\d{2}-\d{2}", s) or [None])[0]
    if not d:
        return None
    try:
        date.fromisoformat(d)
    except ValueError:
        return None
    return d


def sig(v):
    """Cinq chiffres significatifs, comme les fiches sociétés (scrapers/sectors.py)."""
    return float(f"{v:.5g}")


def quote(d, close, open_=None, high=None, low=None, volume=None, currency=None, src=None):
    return {"date": d, "close": close, "open": open_, "high": high, "low": low, "volume": volume, "currency": currency, "src": src}


def parse_euronext(text):
    """Liste des actions Euronext (CSV « ; », quelques lignes d'en-tête) → {symbole Yahoo : cotation de la dernière séance}.
    Une action cotée sur plusieurs places donne un symbole par place ; une ligne sans clôture datée est ignorée."""
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    head = next((i for i, x in enumerate(rows) if x and x[0].strip().lower() == "name"), None)
    if head is None:
        return {}
    h = [c.strip().lower() for c in rows[head]]
    out = {}
    for x in rows[head + 1:]:
        if len(x) < len(h):
            continue
        r = dict(zip(h, (c.strip() for c in x)))
        sym, d, c = (r.get("symbol") or "").upper(), iso_date(r.get("closing price datetime")), num(r.get("closing price"))
        if not sym or not d or not c:
            continue
        mk = (r.get("market") or "").lower()
        q = quote(d, c, num(r.get("open price")), num(r.get("high price")), num(r.get("low price")), num(r.get("volume")),
                  (r.get("currency") or "").upper() or None, "Euronext")
        for key, suf in EURONEXT_PLACES:
            if key in mk:
                out.setdefault(f"{sym}.{suf}", q)
    return out


def nordic_symbol(sym):
    """Symbole Yahoo → symbole Nasdaq Nordic : « INVE-B.ST » → « INVE B », « NDA-FI.HE » → « NDA FI »."""
    return sym.rsplit(".", 1)[0].replace("-", " ").upper()


def parse_nordic_search(js, base, currency=None):
    """Réponse de la recherche Nasdaq Nordic → numéro du titre (« orderbookId ») au symbole exact, sinon None.
    Si la réponse indique une devise, elle doit être celle attendue (même symbole sur deux places)."""
    groups = js.get("data") if isinstance(js, dict) else None
    for g in groups if isinstance(groups, list) else []:
        found = g.get("instruments") if isinstance(g, dict) else None
        for i in found if isinstance(found, list) else []:
            if not isinstance(i, dict) or str(i.get("symbol") or "").strip().upper() != base.upper() or not i.get("orderbookId"):
                continue
            cur = str(i.get("currency") or "").upper()
            if currency and cur and cur != currency:
                continue
            return str(i["orderbookId"])
    return None


def parse_nordic_chart(js):
    """Historique Nasdaq Nordic (« data.charts.rows », nombres avec séparateurs de milliers) → cotations triées par date."""
    d0 = js.get("data") if isinstance(js, dict) else None
    ch = d0.get("charts") if isinstance(d0, dict) else None
    rows = ch.get("rows") if isinstance(ch, dict) else None
    out = []
    for x in rows if isinstance(rows, list) else []:
        if not isinstance(x, dict):
            continue
        d, c = iso_date(x.get("dateTime")), num(x.get("close"))
        if d and c:
            out.append(quote(d, c, num(x.get("open")), num(x.get("high")), num(x.get("low")), num(x.get("totalVolume")), None,
                             "Nasdaq Nordic"))
    return sorted(out, key=lambda q: q["date"])


def parse_nordic_list(js, suf):
    """Liste complète d'une bourse Nasdaq Nordic (« data.instrumentListing.rows ») → {symbole Yahoo : dernier cours, volume du
    jour, montant échangé, devise, numéro du titre}. « INVE B » → « INVE-B.ST ». La liste ne donne pas de date."""
    d0 = js.get("data") if isinstance(js, dict) else None
    il = d0.get("instrumentListing") if isinstance(d0, dict) else None
    rows = il.get("rows") if isinstance(il, dict) else None
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        sym, c = str(r.get("symbol") or "").strip().upper(), num(r.get("lastSalePrice"))
        if not sym or not c:
            continue
        out[sym.replace(" ", "-") + "." + suf] = {"close": c, "change": snum(r.get("netChange")), "volume": num(r.get("volume")),
                                                   "turnover": num(r.get("turnover")),
                                                   "currency": str(r.get("currency") or "").upper() or None,
                                                   "oid": str(r.get("orderbookId") or "") or None}
    return out


def http_get(url, params=None, accept=None, tries=2, timeout=30):
    import requests
    h = dict(UA, **({"Accept": accept} if accept else {}))
    err = None
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            if r.status_code == 200:
                return r
            err = f"HTTP {r.status_code}"
        except Exception as e:  # réseau : nouvel essai, puis abandon
            err = type(e).__name__
        if k + 1 < tries:
            time.sleep(2 * (k + 1))
    raise RuntimeError(err or "échec")


def euronext_quotes():
    r = http_get(EURONEXT_LIST, params={"mics": "dm_all_stock", "initialLetter": "", "fe_type": "csv", "fe_decimal_separator": ".",
                                        "fe_date_format": "d/m/Y"}, timeout=60)
    return parse_euronext(r.content.decode("utf-8-sig", "replace"))


class Nordic:
    """Nasdaq Nordic, titre par titre : numéro du titre (gardé d'un soir à l'autre), puis dix jours de cours.
    quotes(sym) → liste de cotations ([] : titre introuvable), None : non demandé (limite atteinte ou source muette)."""

    def __init__(self, ids, today, max_n=NORDIC_MAX, seconds=NORDIC_SECONDS, get=None):
        self.ids, self.today, self.max_n = ids, today, max_n
        self.until = time.time() + seconds
        self.get = get or http_get
        self.asked = self.got = self.errors = self.fails_in_row = 0
        self.cache = {}

    def _json(self, url, params):
        try:
            r = self.get(url, params=params, accept="application/json", tries=1, timeout=20)
            self.fails_in_row = 0
            return r.json()
        except Exception:
            self.errors += 1
            self.fails_in_row += 1
            return None

    def quotes(self, sym):
        if sym in self.cache:
            return self.cache[sym]
        suf = sym.rsplit(".", 1)[-1]
        if suf not in NORDIC:
            return None
        known = self.ids.get(sym)
        oid = known[0] if isinstance(known, list) and known and known[0] else None
        cutoff = (date.fromisoformat(self.today) - timedelta(days=ID_RETRY_DAYS)).isoformat()
        if not oid and isinstance(known, list) and len(known) > 1 and str(known[1]) >= cutoff:
            self.cache[sym] = []  # introuvable il y a moins de 30 jours : pas de nouvelle recherche
            return []
        if self.asked >= self.max_n or time.time() > self.until or self.fails_in_row >= 5:
            return None
        self.asked += 1
        if not oid:
            base = nordic_symbol(sym)
            js = self._json(f"{NASDAQ}/search", {"searchText": base})
            if js is None:
                return None
            oid = parse_nordic_search(js, base, NORDIC[suf])
            self.ids[sym] = [oid or "", self.today]
            time.sleep(0.15)
            if not oid:
                self.cache[sym] = []
                return []
        qs = self.chart(oid)
        if qs is None:
            return None
        for q in qs:
            q["currency"] = NORDIC[suf]  # la recherche a déjà vérifié la devise quand Nasdaq l'indique
        self.got += bool(qs)
        self.cache[sym] = qs
        return qs

    def chart(self, oid):
        """Quinze derniers jours de cours d'un titre (numéro Nasdaq), None si pas de réponse."""
        end = date.fromisoformat(self.today)
        js = self._json(f"{NASDAQ}/instruments/{oid}/chart/download",
                        {"assetClass": "SHARES", "fromDate": (end - timedelta(days=14)).isoformat(), "toDate": end.isoformat()})
        time.sleep(0.15)
        return None if js is None else parse_nordic_chart(js)

    def confirms(self, r, T):
        """Le dernier cours d'une ligne de liste est-il la clôture de T ? Oui si l'historique du titre a T au même cours (à 0,2 %
        près), ou s'il s'arrête avant T sur la clôture précédente de la liste (dernier cours − variation du jour : historique
        pas encore à jour le soir). En séance, le dernier cours diffère de la clôture : non."""
        qs = self.chart(r["oid"]) or []
        near = lambda a, b: a and b and abs(a / b - 1) <= 0.002
        qT = next((q for q in qs if q["date"] == T), None)
        if qT:
            return bool(near(qT["close"], r["close"]))
        before = [q for q in qs if q["date"] < T]
        return bool(before and r["change"] is not None and near(before[-1]["close"], r["close"] - r["change"]))

    def lists(self, T):
        """Listes complètes de Stockholm, Helsinki et Copenhague (marché principal et First North). Une liste n'a pas de date :
        elle est retenue pour la séance T seulement si les deux titres les plus échangés de la bourse la confirment (confirms) ;
        en séance ou un jour férié, elle est donc écartée.
        → ({symbole Yahoo : cotation de T, titres échangés ce jour seulement}, {bourse : {lignes, retenue}})."""
        out, info = {}, {}
        for mk, suf in NORDIC_MARKETS:
            rows = {}
            for cat in ("MAIN_MARKET", "FIRST_NORTH"):
                js = self._json(f"{NASDAQ}/screener/shares", {"category": cat, "tableonly": "false", "market": mk})
                rows.update(parse_nordic_list(js, suf))
            for sym, r in rows.items():
                if r["oid"]:
                    self.ids[sym] = [r["oid"], self.today]  # numéros gratuits pour le secours titre par titre
            top = sorted((x for x in rows if rows[x]["volume"] and rows[x]["oid"]), key=lambda x: -(rows[x]["turnover"] or 0))[:2]
            ok = sum(1 for x in top if T and self.confirms(rows[x], T))
            info[mk] = {"rows": len(rows), "used": len(top) == 2 and ok == 2}
            if info[mk]["used"]:
                for sym, r in rows.items():
                    if r["volume"]:  # titre échangé ce jour : son dernier cours est la clôture de T
                        out[sym] = quote(T, r["close"], volume=r["volume"], currency=r["currency"], src="Nasdaq Nordic")
        return out, info


def session_of(quotes, today, min_n=MIN_NEW_SESSION):
    """Dernière séance selon la source de secours : la date la plus fréquente (au moins min_n titres), jamais dans le futur."""
    c = Counter(q["date"] for q in quotes if q and q.get("date") and q["date"] <= today)
    d, n = c.most_common(1)[0] if c else (None, 0)
    return d if n >= min_n else None


def friday(d):
    """Vendredi de la semaine d'une date (semaines du lundi au vendredi, comme les cours hebdomadaires des fiches)."""
    x = date.fromisoformat(d)
    return x + timedelta(days=4 - x.weekday())


def last_pos(a, end=None):
    for v in reversed(a[:end] if end is not None else a):
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return v
    return None


def acceptable(q, ref, currency):
    """Devise identique (quand les deux sont connues) et clôture entre la moitié et le double du dernier cours connu."""
    if currency and q.get("currency") and str(currency).upper() != str(q["currency"]).upper():
        return False
    return ref is None or 0.5 <= q["close"] / ref <= 2.0


def stats():
    return {"needed": 0, "filled": 0, "rejected": 0, "byMarket": {}}


def _count(st, sym, k="filled"):
    st[k] += 1
    if k == "filled":
        m = sym.rsplit(".", 1)[-1]
        st["byMarket"][m] = st["byMarket"].get(m, 0) + 1


def week_slot(wd, T, mode):
    """Place de la séance T dans les cours hebdomadaires : « new » (semaine suivant la dernière, ajout seulement), indice de sa
    semaine, ou None."""
    if not wd:
        return None
    if friday(T) > friday(wd[-1]):
        return "new" if mode == "append" else None
    return next((k for k in range(len(wd) - 1, -1, -1) if friday(wd[k]) == friday(T)), None)


def patch_catalogue(shards, enx, nordic, today, T):
    """Complète en place les fiches sociétés (fichiers data/societes/*.json chargés) avec la séance T.
    enx : {symbole : cotation} (Euronext) ; nordic(sym) → cotations Nasdaq Nordic, ou None si non demandé. Renvoie les compteurs.
    « fill » : T est déjà dans les dates, ses cases vides sont complétées. « append » : T est plus récente, elle est ajoutée à
    toutes les fiches (la plus ancienne séance sort, les longueurs ne changent pas ; None pour les titres non couverts)."""
    st = dict(stats(), session=T, mode=None)
    if not shards or not T or T > today:
        return st
    dd, wd = shards[0].get("dDates") or [], shards[0].get("wDates") or []
    same = all((sh.get("dDates") or []) == dd and (sh.get("wDates") or []) == wd for sh in shards)
    if not dd:
        return st
    if T > dd[-1]:
        if not same:  # dates différentes d'un fichier à l'autre : rien n'est ajouté (le calcul suppose des dates communes)
            return st
        mode = "append"
    elif any(T in (sh.get("dDates") or []) for sh in shards):
        mode = "fill"
    else:
        return st
    st["mode"] = mode
    todo = []
    for sh in shards:
        sdd = sh.get("dDates") or []
        iT = sdd.index(T) if T in sdd else None
        for sym, x in (sh.get("items") or {}).items():
            d = x.get("d")
            if isinstance(d, list) and len(d) == len(sdd) and (mode == "append" or (iT is not None and d[iT] is None)):
                todo.append((sh, sym, x))
    st["needed"] = len(todo)
    # Nasdaq Nordic : les titres les plus échangés d'abord ; si les trois premiers répondent sans la séance T (jour férié), arrêt
    nq, probe = {}, []
    for _, sym, x in sorted(todo, key=lambda t: -(t[2].get("turnoverEur") or 0)):
        if sym.rsplit(".", 1)[-1] not in NORDIC or sym in enx:
            continue
        qs = nordic(sym)
        if qs is None:
            continue
        nq[sym] = qs
        if qs and len(probe) < 3:
            probe.append(any(q["date"] == T for q in qs))
            if len(probe) == 3 and not any(probe):
                break
    vT = {}
    for sh, sym, x in todo:
        qs = [enx[sym]] if sym in enx else nq.get(sym) or []
        d, cur = x["d"], x.get("currency")
        pos = {v: k for k, v in enumerate(sh.get("dDates") or [])}
        for q in qs:  # séances déjà dans les dates des fiches (Nasdaq en donne plusieurs) : cases vides seulement
            k = pos.get(q["date"])
            if k is None or d[k] is not None or q["date"] > today:
                continue
            if acceptable(q, last_pos(d, k), cur):
                d[k] = sig(q["close"])
                if q["date"] == T:
                    vT[(id(sh), sym)] = d[k]
                    _count(st, sym)
            elif q["date"] == T:
                _count(st, sym, "rejected")
        q = next((q for q in qs if q["date"] == T), None) if mode == "append" else None
        if q is not None:
            if acceptable(q, last_pos(d), cur):
                vT[(id(sh), sym)] = sig(q["close"])
                _count(st, sym)
            else:
                _count(st, sym, "rejected")
    # ajout de la séance et cours hebdomadaires : toutes les fiches, pour garder les mêmes dates partout
    for sh in shards:
        sdd, swd = sh.get("dDates") or [], sh.get("wDates") or []
        wk = week_slot(swd, T, mode)
        for sym, x in (sh.get("items") or {}).items():
            v = vT.get((id(sh), sym))
            d = x.get("d")
            if mode == "append" and isinstance(d, list) and len(d) == len(sdd):
                x["d"] = d[1:] + [v]
            w = x.get("w")
            okw = isinstance(w, list) and len(w) == len(swd)
            if wk == "new":
                if okw:
                    x["w"] = w[1:] + [v]
                if isinstance(x.get("wv"), list) and x["wv"]:
                    x["wv"] = x["wv"][1:] + [None]  # volume de la semaine inconnu : None (ignoré par le calcul)
            elif okw and isinstance(wk, int) and v is not None and (w[wk] is None or (mode == "append" and wk == len(swd) - 1)):
                w[wk] = v
        if mode == "append":
            sh["dDates"] = sdd[1:] + [T]
            if wk == "new":
                sh["wDates"] = swd[1:] + [T]
            elif isinstance(wk, int) and wk == len(swd) - 1 and T > swd[-1]:
                sh["wDates"] = swd[:-1] + [T]
    return st


def patch_prices(prices, enx, nordic, today, T):
    """Cours Euro Signal (data/prices.json) : séances manquantes ajoutées à la suite (jusqu'à T), cases vides seulement."""
    st = dict(stats(), session=T)
    items = (prices or {}).get("items") or {}
    if not T:
        return st
    for isin, it in items.items():
        tk, rows = (it or {}).get("ticker"), (it or {}).get("rows")
        if not tk or not isinstance(rows, list) or not rows or str(rows[-1][0]) >= T:
            continue
        st["needed"] += 1
        qs = [enx[tk]] if tk in enx else (nordic(tk) or [])
        added = 0
        for q in qs:
            if q["date"] <= str(rows[-1][0]) or q["date"] > today:
                continue
            if not acceptable(q, rows[-1][4] if len(rows[-1]) > 4 else None, it.get("currency")):
                if q["date"] == T:
                    _count(st, tk, "rejected")
                continue
            vol = q.get("volume")
            rows.append([q["date"], q.get("open"), q.get("high"), q.get("low"), q["close"], int(vol) if vol else None])
            added += 1
        if not added:
            continue
        _count(st, tk)
        it["backup"] = rows[-1][0]
        wk = it.get("weekly")
        if isinstance(wk, list):
            last = [rows[-1][0], rows[-1][4]]
            if wk and date.fromisoformat(str(wk[-1][0])).isocalendar()[:2] == date.fromisoformat(last[0]).isocalendar()[:2]:
                wk[-1] = last
            else:
                wk.append(last)
    return st


def read_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(p, obj):
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    tmp.replace(p)


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    co_dir, prices_f, ids_f = DATA / "societes", DATA / "prices.json", DATA / "backup-ids.json"
    files = sorted(co_dir.glob("*.json"), key=lambda f: int(f.stem) if f.stem.isdigit() else 999) if co_dir.exists() else []
    shards = [read_json(f, None) for f in files]
    ok = [(f, sh) for f, sh in zip(files, shards) if isinstance(sh, dict) and isinstance(sh.get("items"), dict)]
    prices = read_json(prices_f, None)
    diag = {"date": today, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "euronext": {}, "nordic": {}}
    t0 = time.time()
    try:
        enx = euronext_quotes()
        diag["euronext"] = {"quotes": len(enx)}
    except Exception as e:
        enx = {}
        diag["euronext"] = {"quotes": 0, "error": str(e)[:120]}
    T = session_of(list(enx.values()), today)
    log(f"Liste Euronext : {len(enx)} cotations, dernière séance {T or '?'} ({time.time() - t0:.0f} s)")
    ids = read_json(ids_f, {})
    nordic = Nordic(ids if isinstance(ids, dict) else {}, today)
    nl, ninfo = nordic.lists(T) if T else ({}, {})
    log("Listes Nasdaq Nordic : " + ", ".join(f"{k} {v['rows']} titres{' (retenue)' if v['used'] else ' (écartée)'}" for k, v in ninfo.items()))
    enx = {**nl, **enx}  # une seule table des cotations du soir : Euronext, puis listes nordiques
    used = {suf for mk, suf in NORDIC_MARKETS if (ninfo.get(mk) or {}).get("used")}

    def one_by_one(sym):  # bourse dont la liste est retenue : un titre absent n'a pas été échangé ce jour, rien à demander
        return [] if sym.rsplit(".", 1)[-1] in used else nordic.quotes(sym)
    before = {f: json.dumps([sh.get("dDates"), sh.get("wDates")]) for f, sh in ok}
    # cours Euro Signal d'abord (dossiers suivis, alertes) : les titres nordiques déjà lus resservent aux fiches sociétés
    sp = patch_prices(prices, enx, one_by_one, today, T) if isinstance(prices, dict) else dict(stats(), session=T)
    sc = patch_catalogue([sh for _, sh in ok], enx, one_by_one, today, T)
    diag.update(session=T, catalogue=sc, prices=sp, seconds=round(time.time() - t0))
    diag["nordic"] = {"lists": ninfo, "quotes": len(nl), "asked": nordic.asked, "got": nordic.got, "errors": nordic.errors}
    if sc["filled"] or sc.get("mode") == "append":
        for f, sh in ok:
            write_json(f, sh)
    if sp["filled"]:
        write_json(prices_f, prices)
    if nordic.ids:
        write_json(ids_f, nordic.ids)
    (DATA / "diagnostics").mkdir(parents=True, exist_ok=True)
    write_json(DATA / "diagnostics" / "backup.json", diag)
    changed = sum(1 for f, sh in ok if json.dumps([sh.get("dDates"), sh.get("wDates")]) != before[f])
    log(f"Fiches sociétés ({sc.get('mode') or 'rien à faire'}) : {sc['filled']} clôtures du {T or '?'} ajoutées sur {sc['needed']} manquantes"
        f" ({', '.join(f'{k} {v}' for k, v in sorted(sc['byMarket'].items(), key=lambda kv: -kv[1])) or 'aucune'}),"
        f" {sc['rejected']} écartées ; dates modifiées dans {changed} fichiers")
    log(f"Cours Euro Signal : {sp['filled']} titres complétés sur {sp['needed']} en retard, {sp['rejected']} écartés")
    log(f"Nasdaq Nordic : {len(nl)} cours des listes, {nordic.asked} titres demandés un par un, {nordic.got} avec des cours, "
        f"{nordic.errors} erreurs ({diag['seconds']} s au total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
