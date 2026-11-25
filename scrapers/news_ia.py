"""
Euro Signal — lecture des titres de presse par une IA (Claude) : effet possible sur le cours de l'action (bloc « 📰 Qualitatif »).

Demande de François (25/11/2026) : « traduire ce que l'actualité (pour chaque article) veut dire potentiellement pour le cours de
l'action (hausse avec flèche verte vers le haut ou baisse ou neutre...) ». Les mots-clés de news.py se trompaient : « Husqvarna
demande à l'autorité commerciale britannique d'enquêter sur le dumping de tondeuses robotisées chinoises » marqué ⚠️ (le mot
« enquête ») alors que la mesure protégerait Husqvarna ; un club de football et des motos d'une autre société retenus comme
actualité de Husqvarna AB.

Chaque nouveau titre de data/news.json est lu une seule fois, avec le nom, le symbole, le pays et le secteur de la société : sans
rapport avec elle (homonyme, autre société, simple liste de marché) ou, s'il la concerne, effet possible sur le cours (hausse,
baisse ou neutre) et la raison en quelques mots. Lectures gardées dans data/news.json (champs i : up / down / flat, p : 0 si sans
rapport, r : raison, v : version de la consigne) et reprises les soirs suivants par news.py ; liste de chaque société remise dans
l'ordre (titres qui la concernent et qui peuvent faire bouger le cours d'abord). Sans le secret ANTHROPIC_API_KEY, ou si l'appel
échoue, les titres gardent le classement par mots-clés (⚠️ / ✅). Modèle, taille des lots et budget de temps : euro_signal/config.json
(« lectureNews »). Seuls des noms de sociétés et des titres d'articles publics sont envoyés. Lancé par le calcul du soir (étape
4c bis) et à chaque publication du code (publish.yml, titres pas encore lus seulement).
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "news.json"
API = "https://api.anthropic.com/v1/messages"
# $ par million de jetons : entrée, sortie, entrée relue du cache (comme grain_signal/actualites.py)
PRIX = {"claude-opus-5-5": (4, 20, 0.2), "claude-sonnet-5-5": (2, 10, 0.1), "claude-haiku-5-5": (0.1, 0.5, 0.01)}
VERSION = 1  # version de la consigne : une lecture plus ancienne est refaite
KEEP = 6     # titres gardés par société après la lecture
DEFAUT = {"modele": "claude-haiku-5-5", "maxTokens": 8000, "lot": 40, "budget": 150, "paralleles": 4}

SYSTEME = """Tu aides un investisseur particulier qui achète des actions européennes et les garde environ six mois. Pour une société
cotée donnée (nom, symbole boursier, pays, secteur), tu reçois des titres d'articles de presse récents : tu ne vois que le titre,
pas l'article. Pour CHAQUE titre, tu dis ce qu'il peut vouloir dire pour le cours de l'action de CETTE société.

- pertinent : false si le titre ne parle pas de cette société cotée : homonyme (club de sport, lieu, personne, autre entreprise
  du même nom), marque qui appartient à une autre société (par exemple les motos Husqvarna appartiennent à KTM, pas à Husqvarna
  AB), simple liste de cours ou de valeurs sans information sur elle, publicité, résultat sportif. true sinon.
- impact : seulement si pertinent ; "hausse" si la nouvelle est plutôt bonne pour le cours (contrat gagné, prévisions relevées,
  rachat d'actions, protection contre des concurrents, par exemple une enquête antidumping qu'elle demande contre des importations
  à bas prix, rachat par une autre société, autorisation obtenue), "baisse" si elle est plutôt mauvaise (avertissement sur
  résultats, perte d'un client, enquête ou amende qui la vise, augmentation de capital qui dilue, départ soudain du dirigeant,
  dégradation par un analyste), "neutre" si l'effet est faible, incertain ou déjà connu (compte rendu de séance, nomination
  attendue, nouvelle sans enjeu financier). Lis qui fait quoi à qui : une enquête demandée PAR la société contre des concurrents
  n'est pas une enquête QUI LA VISE. Ne devine pas au-delà du titre ; dans le doute, "neutre".
- raison : en français, 12 mots au plus, concrète (« protection possible contre les tondeuses chinoises à bas prix », « club de
  football homonyme », « compte rendu de séance, rien de nouveau »).

Réponds uniquement par un objet JSON : {"lectures": [{"id": "…", "pertinent": true, "impact": "hausse", "raison": "…"}, …]},
une entrée par titre, avec l'identifiant donné."""


def config():
    try:
        c = json.loads((ROOT / "euro_signal" / "config.json").read_text(encoding="utf-8")).get("lectureNews") or {}
    except Exception:
        c = {}
    return {**DEFAUT, **{k: v for k, v in c.items() if k in DEFAUT}}


def contexte():
    """Nom, symbole, pays et secteur des sociétés du classement (tableau de bord du soir), par clé."""
    try:
        rows = json.loads((DATA / "euro-signal.json").read_text(encoding="utf-8")).get("rank", {}).get("rows") or []
    except Exception:
        return {}
    out = {}
    for r in rows:
        if isinstance(r, dict) and r.get("key"):
            out[r["key"]] = {"nom": r.get("name") or r["key"], "symbole": r.get("sym") or "", "pays": r.get("country") or "",
                             "secteur": r.get("secEn") or r.get("sector") or ""}
    return out


def lots(items, ctx, size):
    """Titres sans lecture à jour, groupés par lots de `size` (une société n'est pas coupée entre deux lots si possible)."""
    todo = []
    for k, lst in items.items():
        for j, g in enumerate(lst or []):
            if isinstance(g, dict) and g.get("t") and g.get("v") != VERSION:
                todo.append((k, j))
    out, cur, nb = [], [], 0
    for k in dict.fromkeys(k for k, _ in todo):
        mine = [x for x in todo if x[0] == k]
        if cur and nb + len(mine) > size:
            out.append(cur)
            cur, nb = [], 0
        cur.append((k, mine))
        nb += len(mine)
    if cur:
        out.append(cur)
    return out


def message(lot, items, ctx):
    """Texte envoyé pour un lot : chaque société, puis ses titres avec un identifiant k:j."""
    parts = []
    for k, mine in lot:
        c = ctx.get(k) or {"nom": k}
        parts.append("Société : %s (symbole %s, pays %s, secteur %s)" % (c.get("nom"), c.get("symbole") or "?", c.get("pays") or "?",
                                                                        c.get("secteur") or "?"))
        for _, j in mine:
            g = items[k][j]
            parts.append('  - id "%s:%d" · %s · %s · %s' % (k, j, str(g.get("d") or "")[:10], str(g.get("s") or "")[:40], str(g["t"])[:200]))
    return "\n".join(parts)


def appel(key, cfg, texte, systeme=None):
    """Un appel à l'API (consigne en cache) ; deux essais. Erreur : code HTTP ou type d'exception seulement (journal public).
    Sert aussi à la lecture des comptes (scrapers/comptes_ia.py, avec sa propre consigne)."""
    body = {"model": cfg["modele"], "max_tokens": cfg["maxTokens"],
            "system": [{"type": "text", "text": systeme or SYSTEME, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": texte}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    last = None
    for i in range(2):
        try:
            r = requests.post(API, headers=headers, json=body, timeout=60)
            if r.status_code == 200:
                return r.json()
            last = "HTTP %d" % r.status_code  # jamais la réponse ni les en-têtes (journal public)
            if r.status_code in (400, 401, 403, 404):
                break
        except Exception as e:  # noqa: BLE001
            last = type(e).__name__
        time.sleep(5 * (i + 1))
    raise RuntimeError(last)


def lire(text):
    """Lectures de la réponse ; une entrée mal formée est ignorée sans perdre les autres."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        o = json.loads(m.group(0))
        lst = o.get("lectures") if isinstance(o, dict) else None
        if isinstance(lst, list):
            return [x for x in lst if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass
    out, dec = [], json.JSONDecoder()
    for mm in re.finditer(r'\{\s*"id"\s*:', text):
        try:
            x, _ = dec.raw_decode(text, mm.start())
            if isinstance(x, dict):
                out.append(x)
        except json.JSONDecodeError:
            continue
    return out


def applique(items, lectures):
    """Reporte les lectures sur les titres ; renvoie le nombre de titres lus."""
    n = 0
    for x in lectures:
        try:
            k, j = str(x.get("id")).rsplit(":", 1)
            g = items[k][int(j)]
        except (KeyError, ValueError, IndexError, TypeError, AttributeError):
            continue
        pert = x.get("pertinent")
        if not isinstance(pert, bool):
            continue
        imp = {"hausse": "up", "baisse": "down", "neutre": "flat"}.get(str(x.get("impact") or "").strip().lower(), "flat")
        g["p"] = 1 if pert else 0
        g["i"] = imp if pert else "flat"
        g["r"] = re.sub(r"\s+", " ", str(x.get("raison") or "")).strip()[:120]
        g["v"] = VERSION
        n += 1
    return n


def ordre(lst):
    """Titres qui concernent la société et peuvent faire bouger le cours d'abord (baisse, hausse), puis neutres, puis sans rapport ;
    les plus récents d'abord dans chaque groupe. Les titres non lus gardent l'ordre des mots-clés après les titres lus."""
    def rang(g):
        if g.get("v") != VERSION:
            return 3
        if not g.get("p"):
            return 4
        return {"down": 0, "up": 0, "flat": 2}.get(g.get("i"), 2)
    lst = sorted(lst, key=lambda g: str(g.get("d") or ""), reverse=True)
    return sorted(lst, key=rang)[:KEEP]


def cout(usage, modele):
    pin, pout, plu = PRIX.get(modele, PRIX["claude-haiku-5-5"])
    return (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout + usage.get("cache_read_input_tokens", 0) * plu
            + usage.get("cache_creation_input_tokens", 0) * pin * 1.25) / 1e6


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception as e:
        print("Lecture des titres : data/news.json illisible (%s), rien à faire" % type(e).__name__)
        return 0
    items = data.get("items") or {}
    cfg = config()
    ctx = contexte()
    L = lots(items, ctx, int(cfg["lot"]))
    nt = sum(len(m) for lot in L for _, m in lot)
    if not key:
        print("Lecture des titres : pas de secret ANTHROPIC_API_KEY, %d titres gardent le classement par mots-clés" % nt)
        return 0
    if not L:
        print("Lecture des titres : aucun nouveau titre")
        return 0
    t0, lus, err, usage = time.time(), 0, {}, {}

    def one(lot):
        if time.time() - t0 > cfg["budget"]:
            return lot, None, "budget"
        try:
            return lot, appel(key, cfg, message(lot, items, ctx)), None
        except Exception as e:  # noqa: BLE001
            return lot, None, str(e)[:40]
    with cf.ThreadPoolExecutor(int(cfg["paralleles"])) as pool:
        for lot, res, e in pool.map(one, L):
            if e:
                err[e] = err.get(e, 0) + 1
                continue
            for k_, v_ in (res.get("usage") or {}).items():
                if isinstance(v_, (int, float)):
                    usage[k_] = usage.get(k_, 0) + v_
            text = "".join(b.get("text", "") for b in res.get("content") or [] if isinstance(b, dict) and b.get("type") == "text")
            lus += applique(items, lire(text))
    if lus:  # rien de lu (API en panne) : fichier laissé tel quel, ordre des mots-clés compris
        for k in list(items):
            items[k] = ordre(items[k])
        data["items"] = items
        data["lecture"] = {"modele": cfg["modele"], "version": VERSION, "lus": lus, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        tmp = OUT.with_name(OUT.name + ".tmp")  # écriture atomique
        tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(OUT)
    allv = [g for lst in items.values() for g in lst if isinstance(g, dict)]
    rd = [g for g in allv if g.get("v") == VERSION]
    print("Lecture des titres (%s) : %d lus ce soir sur %d à lire, en %.0f s, environ %.3f $ ; affichés : %d lus (%d sans rapport, "
          "%d hausse, %d baisse, %d neutres), %d non lus%s" % (
              cfg["modele"], lus, nt, time.time() - t0, cout(usage, cfg["modele"]), len(rd), sum(1 for g in rd if not g.get("p")),
              sum(1 for g in rd if g.get("p") and g.get("i") == "up"), sum(1 for g in rd if g.get("p") and g.get("i") == "down"),
              sum(1 for g in rd if g.get("p") and g.get("i") == "flat"), len(allv) - len(rd),
              (" ; lots non lus : " + ", ".join("%s (%d)" % kv for kv in err.items())) if err else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
