"""
Euro Signal — mesure en direct des lectures de l'IA : titres de presse (scrapers/news_ia.py) et comptes publiés
(scrapers/comptes_ia.py).

Demande de François (26/11/2026) : « TOUT faire ce que tu proposes », dont « Mesurer les lectures de l'IA au fil des mois ». Elles
ne peuvent pas être testées sur le passé : l'actualité européenne d'EODHD est mince avant 2020 et absente pour les sociétés
disparues, et les lectures se font aujourd'hui. Chaque soir, juste après les lectures :
  - journal : chaque lecture de comptes (société, période lue) la première fois que l'outil la voit ; pour les titres, une ligne
    par société et par jour avec le solde des titres jugés en rapport avec la société (↑ moins ↓) ; date de l'événement = le soir
    où l'outil le voit, jamais avant ;
  - mesure : clôture de la première séance à partir de cette date, puis 13 et 26 semaines plus tard (clôtures d'un an des fiches,
    data/societes), face à la moyenne des sociétés du classement sur les mêmes séances (écart en points) ;
  - bilan (« stats ») : nombre de cas et écart moyen par avis sur les comptes, par effet possible (↑ → ↓), par conseil (« point
    d'alerte » ou « rien qui contredise la règle ») et pour les titres ↑ → ↓ ; « p » : lecture de comptes tout juste publiés. Repris par euro_signal/build.mjs (rank.aiTrack) pour la page : lignes 🧪 des blocs
    « 📑 Lecture des comptes » et « 📰 Qualitatif ».
Aucune règle ne dépend de ces chiffres : ils diront s'il faut se fier aux lectures, ou les retirer (revue du 31/01/2027, puis à
l'été 2027). Les cas de plus de 400 jours, mesurés, sont rangés dans des totaux (« arch ») : le fichier reste léger. Fichier
data/suivi_ia.json, écrit d'un bloc (atomique) ; un fichier d'entrée illisible ne fait rien perdre. Étape 4c ter du calcul du soir.
"""
import hashlib
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "suivi_ia.json"
SINCE = "2026-11-26"
HORIZONS = (("x13", 91), ("x26", 182))
GIVE_UP = 420  # jours : cours introuvables (société retirée, fiche absente) → cas abandonné
ARCHIVE = 400  # jours : cas mesurés rangés dans les totaux
SEEN_DAYS = 60  # mémoire des titres déjà comptés
MIN_N = 20  # en dessous, la page dit « trop peu de cas »


def load(path, default):
    try:
        v = json.loads(Path(path).read_text(encoding="utf-8"))
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def plain(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def closes():
    """Symbole → (séances, clôtures) d'après les fiches (data/societes/*.json : dDates et d, un an de séances)."""
    out = {}
    for f in sorted((DATA / "societes").glob("*.json")):
        sh = load(f, {})
        dd = sh.get("dDates") if isinstance(sh.get("dDates"), list) else []
        for sym, v in (sh.get("items") or {}).items():
            d = v.get("d") if isinstance(v, dict) else None
            if dd and isinstance(d, list) and len(d) == len(dd):
                out[sym] = (dd, d)
    return out


def first_at(dd, day):
    """Indice de la première séance à partir de day (dates triées AAAA-MM-JJ), ou None."""
    lo, hi = 0, len(dd)
    while lo < hi:
        mid = (lo + hi) // 2
        if str(dd[mid]) < day:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(dd) else None


def ret(series, day, h):
    """Rendement de la clôture de la première séance à partir de day à celle de la première séance h jours plus tard ; None si
    l'une manque ou n'est pas encore là ; borné à −90 % / +300 % (erreur de cours plutôt que vraie hausse)."""
    if not series:
        return None
    dd, d = series
    a = first_at(dd, day)
    b = first_at(dd, (date.fromisoformat(day) + timedelta(days=h)).isoformat())
    if a is None or b is None or b <= a:
        return None
    pa, pb = d[a], d[b]
    if not isinstance(pa, (int, float)) or not isinstance(pb, (int, float)) or pa <= 0 or pb <= 0:
        return None
    return max(-.9, min(3.0, pb / pa - 1))


def universe():
    """Clé du classement → symbole (Yahoo), et liste des symboles pour la moyenne des sociétés."""
    rows = (load(DATA / "euro-signal.json", {}).get("rank") or {}).get("rows") or []
    keys = {str(r["key"]): str(r.get("sym") or "") for r in rows if isinstance(r, dict) and r.get("key")}
    return keys, sorted({s for s in keys.values() if s})


def log_comptes(book, keys, today_s):
    """Nouvelles lectures de comptes (société, période) : une ligne la première fois."""
    items = load(DATA / "comptes_ia.json", {}).get("items")
    n = 0
    lim = (date.fromisoformat(today_s) - timedelta(days=30)).isoformat()
    recent = {e.get("k") for e in book["c"].values() if str(e.get("d") or "") > lim}
    for k, c in (items if isinstance(items, dict) else {}).items():
        if not isinstance(c, dict) or c.get("a") not in ("fav", "mit", "def") or not c.get("per"):
            continue
        cid = "c|%s|%s" % (k, c["per"])
        if cid in book["c"]:
            continue
        if k in recent and not c.get("pub"):
            # même société déjà notée il y a moins de 30 jours (premier relevé des trimestres juste après celui des exercices) : pas
            # deux fois la même hausse ; les comptes tout juste publiés, eux, sont toujours notés
            continue
        book["c"][cid] = {"k": k, "s": keys.get(k) or "", "d": today_s, "i": c.get("i") if c.get("i") in ("up", "down") else "flat",
                          "a": c["a"], "al": 1 if (c.get("al") or c.get("a") == "def") else 0, "p": 1 if c.get("pub") else 0}
        n += 1
    return n


def log_titres(book, keys, today_s):
    """Titres lus par l'IA et jugés en rapport avec la société, pas encore comptés : solde ↑ − ↓ par société pour ce soir."""
    items = load(DATA / "news.json", {}).get("items")
    seen, n, day = book["seen"], 0, {}
    for k, lst in (items if isinstance(items, dict) else {}).items():
        for g in lst if isinstance(lst, list) else []:
            if not isinstance(g, dict) or "v" not in g or g.get("p") != 1:
                continue
            h = hashlib.sha1(("%s|%s" % (k, plain(g.get("t"))[:60])).encode()).hexdigest()[:12]
            if h in seen:
                continue
            seen[h] = today_s
            s = day.setdefault(k, [0, 0])
            s[0] += 1 if g.get("i") == "up" else -1 if g.get("i") == "down" else 0
            s[1] += 1
    for k, (net, cnt) in day.items():
        tid = "t|%s|%s" % (k, today_s)
        if tid in book["t"]:
            continue
        book["t"][tid] = {"k": k, "s": keys.get(k) or "", "d": today_s, "net": (net > 0) - (net < 0), "n": cnt}
        n += 1
    return n


def measure(book, px, syms, today):
    """Écarts à 13 et 26 semaines face à la moyenne des sociétés, pour les cas qui ont assez de recul ; renvoie le nombre mesuré."""
    bench, n = {}, 0

    def avg(day, h):
        key = (day, h)
        if key not in bench:
            v = [r for r in (ret(px.get(s), day, h) for s in syms) if r is not None]
            bench[key] = sum(v) / len(v) if len(v) >= 50 else None
        return bench[key]
    for part in ("c", "t"):
        for e in book[part].values():
            try:
                age = (today - date.fromisoformat(e["d"])).days
            except (KeyError, TypeError, ValueError):
                continue
            for f, h in HORIZONS:
                if f in e or age < h:
                    continue
                r, m = ret(px.get(e.get("s")), e["d"], h), avg(e["d"], h)
                if r is not None and m is not None:
                    e[f] = round((r - m) * 100, 2)
                    n += 1
                elif age > GIVE_UP:
                    e[f] = None  # abandonné : pas de cours
    return n


GROUPS = {"c": (("avis", "a", ("fav", "mit", "def")), ("effet", "i", ("up", "flat", "down")), ("conseil", "al", (1, 0))),
          "t": (("effet", "net", (1, 0, -1)),)}


def gid(part, g, v):
    return "%s:%s:%s" % (part, g, v)


def archive(book, today):
    """Cas de plus de ARCHIVE jours, mesurés (ou abandonnés) aux deux horizons : rangés dans les totaux, retirés du journal."""
    arch, n = book["arch"], 0
    for part in ("c", "t"):
        for cid in list(book[part]):
            e = book[part][cid]
            try:
                old = (today - date.fromisoformat(e["d"])).days > ARCHIVE
            except (KeyError, TypeError, ValueError):
                old = True
            if not old or not all(f in e for f, _ in HORIZONS):
                continue
            for g, fld, vals in GROUPS[part]:
                if e.get(fld) not in vals:
                    continue
                a = arch.setdefault(gid(part, g, e[fld]), {})
                for f, _ in HORIZONS:
                    if isinstance(e.get(f), (int, float)):
                        a["n" + f[1:]] = a.get("n" + f[1:], 0) + 1
                        a["s" + f[1:]] = round(a.get("s" + f[1:], 0.0) + e[f], 2)
            del book[part][cid]
            n += 1
    return n


def stats(book, today_s):
    """Nombre de cas et écart moyen (points, face à la moyenne des sociétés) par groupe, à 13 et 26 semaines."""
    out = {"since": SINCE, "at": today_s, "minN": MIN_N, "c": {}, "t": {}}
    for part in ("c", "t"):
        for g, fld, vals in GROUPS[part]:
            for v in vals:
                a = dict(book["arch"].get(gid(part, g, v)) or {})
                cell = {}
                for f, _ in HORIZONS:
                    xs = [e[f] for e in book[part].values() if e.get(fld) == v and isinstance(e.get(f), (int, float))]
                    n = len(xs) + int(a.get("n" + f[1:], 0))
                    s = sum(xs) + float(a.get("s" + f[1:], 0.0))
                    cell["n" + f[1:]] = n
                    cell["m" + f[1:]] = round(s / n, 1) if n else None
                cell["cas"] = sum(1 for e in book[part].values() if e.get(fld) == v)
                out[part]["%s:%s" % (g, v)] = cell
    return out


def main():
    today = datetime.now(timezone.utc).date()
    today_s = today.isoformat()
    raw = load(OUT, {})
    book = {"c": raw.get("c") if isinstance(raw.get("c"), dict) else {}, "t": raw.get("t") if isinstance(raw.get("t"), dict) else {},
            "seen": raw.get("seen") if isinstance(raw.get("seen"), dict) else {},
            "arch": raw.get("arch") if isinstance(raw.get("arch"), dict) else {}}
    if OUT.exists() and not raw:
        print("Suivi des lectures de l'IA : data/suivi_ia.json illisible, rien n'est écrit (fichier gardé pour vérification)")
        return 1
    keys, syms = universe()
    nc, nt = log_comptes(book, keys, today_s), log_titres(book, keys, today_s)
    lim = (today - timedelta(days=SEEN_DAYS)).isoformat()
    book["seen"] = {h: d for h, d in book["seen"].items() if isinstance(d, str) and d >= lim}
    px = closes()
    nm = measure(book, px, syms, today) if px and syms else 0
    na = archive(book, today)
    st = stats(book, today_s)
    tmp = OUT.with_name(OUT.name + ".tmp")
    tmp.write_text(json.dumps({"format": "euro-signal-suivi-ia", "v": 1, "updated": datetime.now(timezone.utc).isoformat(), **book,
                               "stats": st}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    c13 = {k: v["n13"] for k, v in st["c"].items() if k.startswith("avis:")}
    print("Suivi des lectures de l'IA : %d lectures de comptes et %d jours de titres ajoutés, %d mesures faites, %d cas rangés ; "
          "journal %d comptes, %d titres ; mesurés à 13 semaines : %s ; cours de %d sociétés" % (
              nc, nt, nm, na, len(book["c"]), len(book["t"]), ", ".join("%s %d" % (k[5:], v) for k, v in c13.items()), len(px)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
