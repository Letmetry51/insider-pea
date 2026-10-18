"""
Euro Signal — actualité qualitative des sociétés à acheter ou à surveiller (bloc « 📰 Qualitatif » de l'analyse).

Pour les sociétés proposées par le 🎯 et le 💎, la sélection du lundi et les 150 premières du classement (liste de la veille) :
  - titres d'articles des 30 derniers jours (Google Actualités, en français, puis en anglais si rien) ;
  - communiqués et actualités Yahoo déjà relevés par events.py pour les sociétés suivies par Euro Signal.
Chaque titre est classé par mots-clés : ⚠️ (perte de client ou de contrat, avertissement, enquête, dégradation…) ou ✅ (contrat
remporté, prévisions relevées, rachat d'actions…). Rien n'est interprété au-delà : le titre et le lien sont donnés tels quels.
Sortie : data/news.json = { generated_at, items: { clé: [ { t, s, d, u, k } ] } } (clé = ISIN ou symbole Yahoo, comme le classement).
"""
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "news.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
DAYS = 30

NEG = [r"perte d[eu']? ?(son |un |une |sa |ses )?(principal |gros |plus gros )?(client|contrat|march[ée])", r"perd (son|un|une|sa) (principal |gros )?(client|contrat)", r"avertissement",
       r"profit warning", r"abaisse (ses|son|sa)", r"revoit (à la baisse|en baisse)", r"r[ée]vis\w* (à la baisse|en baisse)", r"lowers? (its |full.year )?(guidance|outlook|forecast)",
       r"cuts? (its |full.year )?(guidance|outlook|forecast)", r"enqu[êe]te", r"investigation", r"probe", r"amende", r"\bfined?\b", r"plainte", r"lawsuit", r"fraude", r"fraud",
       r"d[ée]mission", r"resigns?", r"d[ée]part (du|de son) (pdg|directeur|dg|ceo|cfo)", r"steps down", r"downgrade", r"d[ée]grad", r"rappel (de|des) produits", r"recall",
       r"cyberattaque", r"cyber.?attack", r"gr[èe]ve", r"\bstrike\b", r"faillite", r"insolv", r"redressement judiciaire", r"augmentation de capital", r"capital increase", r"dilution",
       r"vente à découvert", r"short seller", r"short report", r"chute", r"plonge", r"plunges?", r"s'effondre", r"tumbles?", r"sinks?", r"loses? (a |its )?(major |key |biggest )?(customer|client|contract)",
       r"non.renouvel", r"résili", r"terminat"]
POS = [r"remporte", r"\bwins?\b", r"d[ée]croche", r"nouveau contrat", r"new contract", r"commande", r"\border(s)?\b", r"rel[èe]ve (ses|son|sa)", r"raises? (its |full.year )?(guidance|outlook|forecast)",
       r"upgrade", r"relèvement", r"\brecord\b", r"rachat d'actions", r"buy.?back", r"share repurchase", r"partenariat", r"partnership", r"approbation", r"approval", r"\bfeu vert\b",
       r"acquisition", r"acquiert", r"acquires?", r"offre publique", r"takeover", r"beats? (estimates|expectations|consensus)", r"dépasse (les )?(attentes|consensus)", r"surge", r"bondit", r"s'envole"]
NEG_RE = re.compile("|".join(NEG), re.I)
POS_RE = re.compile("|".join(POS), re.I)
LEGAL = {"sa", "se", "ag", "nv", "plc", "spa", "s", "p", "a", "kgaa", "co", "gmbh", "ab", "publ", "oyj", "asa", "as", "bv", "ltd", "limited", "inc", "group", "groupe", "holding", "sca", "the"}


def plain(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def short_name(name):
    w = [x for x in re.split(r"[^\w&'-]+", str(name or "")) if x and plain(x) not in LEGAL]
    return " ".join(w[:3]) if w else str(name or "")


def tag(title):
    if NEG_RE.search(title):
        return "neg"
    if POS_RE.search(title):
        return "pos"
    return ""


def google(name, lang):
    hl, gl, ceid = ("fr", "FR", "FR:fr") if lang == "fr" else ("en", "GB", "GB:en")
    q = '"%s" when:%dd' % (short_name(name), DAYS)
    u = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": hl, "gl": gl, "ceid": ceid})
    r = requests.get(u, headers=UA, timeout=20)
    r.raise_for_status()
    out = []
    root = ET.fromstring(r.content)
    key = plain(short_name(name)).split(" ")[0]
    for it in root.iter("item"):
        t = html.unescape(it.findtext("title") or "").strip()
        src = it.findtext("source") or ""
        if src and t.endswith(" - " + src):
            t = t[: -len(src) - 3]
        if key and key not in plain(t):
            continue  # le titre doit citer la société (évite les homonymes et les listes de marché)
        try:
            d = parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
        except Exception:
            continue
        out.append({"t": t[:180], "s": src[:40], "d": d, "u": it.findtext("link") or ""})
    return out


def targets():
    """Clés et noms des sociétés à couvrir, d'après le tableau de bord de la veille."""
    try:
        dash = json.loads((DATA / "euro-signal.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    rank = dash.get("rank") or {}
    rows = {r.get("key"): r for r in rank.get("rows") or [] if isinstance(r, dict) and r.get("key")}
    keys = []
    for k in (rank.get("pick10") or []) + (rank.get("value10") or []):
        keys += [r for r in rows if r == k or rows[r].get("sym") == k or rows[r].get("isin") == k]
    keys += [x.get("key") for x in ((rank.get("selection") or {}).get("items") or []) if isinstance(x, dict)]
    ranked = sorted((r for r in rows.values() if not r.get("out")), key=lambda r: -(r.get("note") or 0))
    keys += [r.get("key") for r in ranked[:150]]
    seen, out = set(), {}
    for k in keys:
        if k and k in rows and k not in seen:
            seen.add(k)
            out[k] = rows[k].get("name") or k
    return out


def yahoo_press():
    """Communiqués et actualités Yahoo relevés par events.py (sociétés suivies par Euro Signal), par ISIN."""
    try:
        ev = json.loads((DATA / "events.json").read_text(encoding="utf-8")).get("items") or {}
    except Exception:
        return {}
    out = {}
    for isin, v in ev.items():
        for p in (v or {}).get("press") or []:
            if p.get("title") and p.get("date"):
                out.setdefault(isin, []).append({"t": p["title"][:180], "s": (p.get("provider") or "Yahoo")[:40], "d": p["date"][:10], "u": p.get("url") or ""})
    return out


def main():
    since = (date.today() - timedelta(days=DAYS)).isoformat()
    T = targets()
    yp = yahoo_press()
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8")).get("items") or {}
    except Exception:
        prev = {}
    items, ok, fail = {}, 0, 0
    t0 = time.time()
    for k, name in T.items():
        if time.time() - t0 > 420:
            break  # budget de 7 minutes : la suite au prochain soir
        got = []
        for lang in ("fr", "en"):
            try:
                got = google(name, lang)
            except Exception:
                got = []
                fail += 1
            if got:
                break
            time.sleep(0.6)
        got += yp.get(k, [])
        if not got and prev.get(k):
            got = prev[k]  # rien ce soir : on garde ceux de la veille
        seen, lst = set(), []
        for g in sorted(got, key=lambda g: g["d"], reverse=True):
            key = plain(g["t"])[:60]
            if g["d"] < since or key in seen:
                continue
            seen.add(key)
            g["k"] = tag(g["t"])
            lst.append(g)
        if lst:
            # d'abord les titres marqués (⚠️ puis ✅), puis les plus récents ; 6 au plus
            lst.sort(key=lambda g: ({"neg": 0, "pos": 1}.get(g["k"], 2), g["d"]), reverse=False)
            lst = sorted(lst[:6], key=lambda g: ({"neg": 0, "pos": 1}.get(g["k"], 2), "" if g["k"] else g["d"]))
            items[k] = lst
            ok += 1
        time.sleep(0.6)
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "days": DAYS, "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Actualité qualitative : %d sociétés avec des articles sur %d visées (%d requêtes refusées)" % (ok, len(T), fail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
