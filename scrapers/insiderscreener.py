"""
Euro Signal — Allemagne, Espagne, Italie via l'API Insider Screener (payant, offre « API Starter »).
En secours, aussi Belgique et Pays-Bas quand la collecte directe FSMA / AFM n'est pas complète.

Insider Screener relève lui-même, toutes les heures, les registres officiels : BaFin (DE), CNMV (ES),
Consob (IT), FSMA (BE), AFM (NL). Euro Signal ne peut pas le faire directement pour DE / ES / IT : le
robots.txt de la BaFin interdit la collecte automatisée, la CNMV bloque les serveurs de centres de
données et la Consob ne publie plus de tableau.

Activation : secret GitHub INSIDERSCREENER_API_KEY. La clé n'est jamais écrite dans un fichier ni affichée.
Sans clé, le script marque DE / ES / IT « non configurés » et s'arrête : aucune alerte n'est alors émise
pour ces pays (couverture inconnue), sans fausse conclusion « aucun achat ».

API (documentation publique, FAQ Insider Screener) :
  GET https://www.insiderscreener.com/api/v1/data/transactions/   en-tête X-API-Key (sans préfixe)
  paramètres market, notification_date_from (AAAA-MM-JJ), ordering, page_size
  réponse { data: [...], pagination: { next: URL | null } } ; montants et prix renvoyés en texte
  401 clé invalide ou inactive · 403 offre sans accès à la ressource · 429 débit ou crédits dépassés

Coût : environ 5 crédits par bloc de 100 lignes pour un marché hors États-Unis. Collecte incrémentale par
date de notification, plafond par exécution (MAX_CREDITS_PER_RUN) et par mois (MONTHLY_BUDGET).

Le schéma détaillé des enregistrements n'étant pas public, chaque champ est cherché sous plusieurs noms
plausibles, et deux enregistrements bruts par marché sont déposés dans data/diagnostics/insiderscreener.json.
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "insiders-eu.json"
DIAG = DATA / "diagnostics" / "insiderscreener.json"
API = "https://www.insiderscreener.com/api/v1/data/transactions/"
# Marchés couverts uniquement par Insider Screener
MARKETS = {"DE": ("BaFin", "Allemagne"), "ES": ("CNMV", "Espagne"), "IT": ("CONSOB", "Italie")}
# Marchés en secours : interrogés seulement si la collecte directe du soir n'est pas complète
BACKUP = {"BE": ("FSMA", "Belgique"), "NL": ("AFM", "Pays-Bas")}
BACKFILL_DAYS = 120
MAX_CREDITS_PER_RUN = 150      # ≈ 30 pages de 100 lignes ; le rattrapage initial se répartit sur quelques soirs
MAX_CREDITS_PER_MARKET = 50    # un rattrapage long (Italie) ne doit pas priver les autres marchés, ni le secours Pays-Bas
MONTHLY_BUDGET = 900           # garde-fou sous les 1 000 crédits mensuels de l'offre Starter
CREDITS_PER_PAGE = 5


def load():
    try:
        st = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    for k in ("records", "sources", "cursors", "isUsage"):
        st.setdefault(k, {})
    return st


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def get(obj, p):
    cur = obj
    for k in p.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def pick(obj, *paths):
    """Première valeur non vide parmi des chemins « a.b.c » ; gère {amount, currency}."""
    for p in paths:
        cur = get(obj, p)
        if isinstance(cur, dict) and "amount" in cur:
            cur = cur.get("amount")
        if cur not in (None, "", [], {}):
            return cur
    return None


def money(obj, *paths):
    """(montant, devise) dans la devise d'origine. Les champs convertis en dollars (*_usd) sont ignorés."""
    for p in paths:
        cur = get(obj, p)
        if isinstance(cur, dict):
            if cur.get("amount") not in (None, ""):
                return cur.get("amount"), cur.get("currency")
        elif cur not in (None, ""):
            return cur, None
    return None, None


def extra(x, *labels):
    """Champ du registre d'origine recopié par Insider Screener (raw.extra_data), libellé tolérant."""
    ed = get(x, "raw.extra_data") or {}
    if not isinstance(ed, dict):
        return None
    norm = {str(k).replace("\ufeff", "").strip().lower(): v for k, v in ed.items()}
    for lab in labels:
        v = norm.get(lab.lower())
        if v not in (None, ""):
            return v
    return None


def person_fields(x):
    """(déclarant, fonction, personne liée) selon le schéma 2026-04-01 d'Insider Screener."""
    rp = get(x, "reporting_person") or {}
    flags = rp.get("relationship_flags") or {}
    pos = rp.get("position")
    if isinstance(pos, dict):
        pos = pos.get("raw") or pos.get("display") or pos.get("normalized")
    pos = pos or extra(x, "Position / status", "position", "funzione", "cargo")
    cap = bool(flags.get("is_closely_affiliated")) or bool(pos and "closely" in str(pos).lower())
    if cap:
        person = rp.get("cap_name") or rp.get("closely_affiliated_name") or rp.get("display_name") or rp.get("name")
        linked = rp.get("pdmr_name") if rp.get("pdmr_name") and rp.get("pdmr_name") != person else None
        if linked and len(str(linked).split()) > 5:
            linked = None  # phrase libre, pas un nom : la personne liée n'est alors pas comptée comme acheteur
        role = "Closely associated person" + (" (" + str(pos) + ")" if pos and "closely" not in str(pos).lower() else "")
    else:
        person = rp.get("pdmr_name") or rp.get("display_name") or rp.get("name") or rp.get("effective_name")
        linked = None
        if not pos:
            pos = "Director" if flags.get("is_director") else "Officer" if flags.get("is_officer") else None
        role = pos
    return person, role, linked


def to_record(x, market, registry, via):
    rid = str(pick(x, "id", "transaction.id") or "")
    code = pick(x, "transaction.classification.normalized_operation", "transaction.nature", "nature")
    nature_raw = pick(x, "transaction.classification.nature_raw") or extra(x, "Nature of transaction", "nature", "tipo operazione", "naturaleza")
    price, pcur = money(x, "transaction.price", "transaction.price_local", "transaction.unit_price")
    amount, acur = money(x, "transaction.gross_value", "transaction.gross_value_local", "transaction.value", "transaction.amount")
    currency = pcur or acur or pick(x, "transaction.currency", "security.currency", "currency")
    person, role, linked = person_fields(x)
    slug = pick(x, "issuer.slug", "security.issuer.slug")
    src_status = str(pick(x, "source.status") or "").upper()
    status = "cancelled" if src_status in ("CANCELLED", "WITHDRAWN", "DELETED") else (
        "amendment" if pick(x, "source.is_amendment") or re.search(r"amend|rettific|correc|modif|wijzig|berichtig", str(pick(x, "source.notification_type") or ""), re.I) else None)
    return {
        "registry": registry, "country": market, "id": rid, "via": via,
        "url": pick(x, "source.url", "source.document_url") or (f"https://www.insiderscreener.com/en/company/{slug}" if slug else None),
        "published": str(pick(x, "source.notification_date", "transaction.notification_date", "notification_date") or "")[:10] or None,
        "txDate": str(pick(x, "transaction.execution_date", "transaction.transaction_date", "transaction_date", "transaction.date") or "")[:10] or None,
        "issuer": pick(x, "issuer.name", "security.issuer.name"),
        "isin": pick(x, "security.isin", "issuer.isin") or extra(x, "ISIN") or pick(x, "raw.extra_data.it_ingestion.instrument_identification"),
        "instrument": pick(x, "security.type", "security.instrument_type") or extra(x, "Typ of instrument", "Type of instrument") or "Share",
        "person": person, "role": role, "linkedTo": linked,
        "nature": nature_raw or code, "natureCode": code,
        "price": price, "currency": currency,
        "quantity": pick(x, "transaction.quantity", "transaction.shares"),
        "amount": amount,
        "place": extra(x, "Place of transaction") or pick(x, "security.trading_place"),
        "status": status,
        "numberLocale": "en", "collectedAt": date.today().isoformat(),
    }


class Budget:
    def __init__(self, st):
        self.month = date.today().strftime("%Y-%m")
        self.used_month = int(st["isUsage"].get(self.month, 0))
        self.run = 0
        self.st = st

    def start_market(self):
        self.market = 0

    def can_spend(self):
        return (self.run + CREDITS_PER_PAGE <= MAX_CREDITS_PER_RUN and self.used_month + CREDITS_PER_PAGE <= MONTHLY_BUDGET
                and getattr(self, "market", 0) + CREDITS_PER_PAGE <= MAX_CREDITS_PER_MARKET)

    def spend(self):
        self.market = getattr(self, "market", 0) + CREDITS_PER_PAGE
        self.run += CREDITS_PER_PAGE
        self.used_month += CREDITS_PER_PAGE
        self.st["isUsage"] = {self.month: self.used_month}  # seul le mois en cours est gardé

    def reason(self):
        if self.used_month + CREDITS_PER_PAGE > MONTHLY_BUDGET:
            return "budget mensuel de crédits atteint"
        return "plafond de crédits par soir atteint"


def fetch_market(m, registry, via, st, headers, budget, today):
    """Collecte incrémentale d'un marché. Retourne (lignes, complet, erreur, diagnostic)."""
    budget.start_market()
    since = st["cursors"].get(m)
    since = (date.fromisoformat(since) - timedelta(days=3)) if since else today - timedelta(days=BACKFILL_DAYS)
    url = API
    params = {"market": m, "notification_date_from": since.isoformat(), "ordering": "notification_date", "page_size": 100}
    n, pages, last_notif, complete, err = 0, 0, None, False, None
    d = {"from": since.isoformat(), "samples": []}
    while url:
        if not budget.can_spend():
            err_soft = budget.reason()
            d["stoppedBy"] = err_soft
            break
        r = None
        for attempt in (1, 2):
            try:
                r = requests.get(url, headers=headers, params=params, timeout=60)
            except Exception as e:
                err = "réseau : " + type(e).__name__
                r = None
                break
            budget.spend()
            if r.status_code == 429 and attempt == 1:
                time.sleep(15)  # débit dépassé : une seule nouvelle tentative
                continue
            break
        if r is None:
            break
        pages += 1
        if r.status_code != 200:
            d["errorBody"] = r.text[:300]
            err = {401: "clé refusée ou inactive (HTTP 401)",
                   403: "l'offre ne donne pas accès à ce marché (HTTP 403)",
                   402: "crédits épuisés (HTTP 402)",
                   429: "débit ou crédits dépassés (HTTP 429)",
                   400: "paramètres refusés par l'API (HTTP 400)"}.get(r.status_code, f"HTTP {r.status_code}")
            break
        params = None  # l'URL « next » contient déjà ses paramètres
        try:
            body = r.json()
        except ValueError:
            err = "réponse illisible (pas du JSON)"
            d["errorBody"] = r.text[:300]
            break
        if not isinstance(body, dict):
            err = "réponse inattendue (pas un objet JSON)"
            d["errorBody"] = r.text[:300]
            break
        rows = body.get("data") or body.get("results") or []
        if not isinstance(rows, list):
            rows = []
        for x in rows:
            if len(d["samples"]) < 2:
                d["samples"].append(x)
            rec = to_record(x, m, registry, via)
            if not rec["id"]:
                continue
            st["records"][f"IS:{m}:{rec['id']}"] = rec
            n += 1
            if rec["published"] and (not last_notif or rec["published"] > last_notif):
                last_notif = rec["published"]
        url = ((body.get("pagination") or {}) if isinstance(body.get("pagination"), dict) else {}).get("next") or body.get("next")
        if url and not str(url).startswith("https://www.insiderscreener.com/api/"):
            err = "lien de page suivante hors du domaine Insider Screener : ignoré"  # la clé n'est jamais envoyée ailleurs
            url = None
        if not url:
            complete = True
        time.sleep(1.1)  # 1 requête par seconde au plus
    if not err:
        if complete:
            st["cursors"][m] = last_notif or today.isoformat()
        elif last_notif:
            st["cursors"][m] = last_notif  # reprise au soir suivant
    d.update({"pages": pages, "rows": n, "complete": complete, "error": err})
    return n, complete, err, d


def main():
    key = os.environ.get("INSIDERSCREENER_API_KEY", "").strip()
    st = load()
    today = date.today()
    if not key:
        for m, (reg, pays) in MARKETS.items():
            st["sources"][reg] = {"name": reg, "countries": [m], "kind": "déclarations", "via": "Insider Screener API", "status": "absent",
                                  "note": f"{pays} : non configuré (secret INSIDERSCREENER_API_KEY absent)", "lastAttempt": today.isoformat()}
        save(OUT, st)
        print("Insider Screener : clé absente, Allemagne / Espagne / Italie non collectées")
        return 0
    headers = {"X-API-Key": key, "Accept": "application/json", "User-Agent": "EuroSignal/1.1 (usage personnel)"}
    budget = Budget(st)
    diag = {"at": datetime.now(timezone.utc).isoformat(), "markets": {}}

    # 1. Allemagne, Espagne, Italie : Insider Screener est la seule source
    key_refused = False
    for m, (reg, pays) in MARKETS.items():
        src = st["sources"].get(reg, {})
        src.update({"name": reg, "countries": [m], "kind": "déclarations",
                    "via": "Insider Screener API (relève horaire du registre " + reg + ")", "lastAttempt": today.isoformat()})
        if key_refused:  # inutile de dépenser une requête de plus
            src.update({"status": "echec", "note": "clé refusée ou inactive (HTTP 401)"})
            st["sources"][reg] = src
            continue
        n, complete, err, d = fetch_market(m, reg, "Insider Screener API", st, headers, budget, today)
        if err:
            src.update({"status": "echec", "note": err})
        else:
            src.update({"status": "ok" if complete else "partiel", "rows": n,
                        "lastSuccess": today.isoformat() if complete else src.get("lastSuccess"),
                        "note": None if complete else "rattrapage en cours (" + (d.get("stoppedBy") or "suite au prochain soir") + ")"})
        st["sources"][reg] = src
        diag["markets"][m] = d
        etat = "ÉCHEC — " + err if err else ("complet" if complete else "partiel (suite au prochain soir)")
        print(f"Insider Screener {m} ({reg}) : {n} lignes, {d['pages']} page(s), {etat}")
        key_refused = bool(err and "401" in err)

    # 2. Belgique, Pays-Bas : en secours seulement si la collecte directe de ce soir n'est pas complète
    for m, (reg, pays) in BACKUP.items():
        src = st["sources"].get(reg)
        if key_refused or not src or src.get("status") == "ok":
            continue
        direct_note = src.get("note")
        n, complete, err, d = fetch_market(m, reg, "Insider Screener API (secours)", st, headers, budget, today)
        d["backupFor"] = reg
        diag["markets"][m] = d
        if not err and complete:
            src.update({"status": "ok", "lastSuccess": today.isoformat(),
                        "note": "complété via Insider Screener (collecte directe : " + (direct_note or src.get("status", "?")) + ")"})
        print(f"Insider Screener {m} (secours {reg}) : {n} lignes, " + ("ÉCHEC — " + err if err else ("complet" if complete else "partiel")))

    diag["credits"] = {"thisRun": budget.run, "thisMonth": budget.used_month, "monthlyBudget": MONTHLY_BUDGET}
    save(DIAG, diag)
    st["generated_at"] = datetime.now(timezone.utc).isoformat()
    save(OUT, st)
    print(f"Crédits estimés : {budget.run} ce soir, {budget.used_month} ce mois-ci (garde-fou : {MONTHLY_BUDGET})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
