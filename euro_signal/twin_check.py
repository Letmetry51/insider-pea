"""
Euro Signal — double calcul du classement tendance + comptes et de la sélection des 5 (contrôle indépendant du moteur).

Pourquoi : un chiffre faux peut avoir l'air juste, et des tests écrits en même temps que le code partagent ses erreurs. Ce
programme, écrit à part en Python simple (aucune bibliothèque de calcul), refait chaque soir, à partir des mêmes cours du
catalogue (data/societes/*.json), les repères de chaque société (hausse sur 12 mois hors dernier mois, plus haut sur un an,
moyennes 50 et 200 séances, pente du canal, volumes, bond sur gros volume, volatilité, variation d'un jour, saut de cours),
les points et la note, puis la sélection des 5 de l'email du lundi et les 10 🎯 du tableau de bord, et compare le tout au
calcul du moteur JavaScript (data/euro-signal.json, euro_signal/core.js).

Repris tels quels du moteur (calculés par d'autres modules, hors de ce contrôle) : comptes (verdict et exclusions liées aux
comptes), points des dirigeants, ventes à découvert publiées. Réglages lus dans la configuration publiée (cfg.rank) ; seuils
lus dans euro_signal/core.js (ES.VOL_WILD, ES.SHORT_MIN, ES.RANK_JUMP_UP et _DOWN, ES.SHORT_EXCLUDE, pentes de ES.slopeClass,
valeurs par défaut de ES.pickThree) : un seuil changé d'un seul côté ne peut pas passer inaperçu. Les autres constantes des
règles (bond de +8 % sur 3 fois le volume, 10 semaines de volumes sur 52, réparations des cours Yahoo…) sont écrites ici :
les changer dans le moteur fait apparaître un écart, voulu.

Écrit data/diagnostics/twin.json, lu par euro_signal/check_outputs.mjs (email de contrôle et Aide → État des données).
N'arrête jamais le calcul ; sort en erreur seulement si le contrôle n'a pas pu se faire (le rapport le dit aussi).

  python euro_signal/twin_check.py              (après euro_signal/build.mjs)
  python euro_signal/twin_check.py --data DIR   (autre dossier de données)
  python euro_signal/twin_check.py --strict     (sortie en erreur au moindre écart : calcul rejoué de la CI)
"""
import json
import math
import os
import re
import sys
import time
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# exclusions venues des comptes (reprises du moteur) et exclusions tirées des cours (recalculées ici)
ACC_OUT = re.compile(r"comptes en dégradation|dernier exercice en perte|bilan en zone de détresse")
PRICE_OUT = [
    ("liquidité", re.compile(r"^peu liquide")),
    ("moins d'un an", re.compile(r"^moins d'un an de cours")),
    ("tiers faible", re.compile(r"tiers le plus faible")),
    ("cours figé", re.compile(r"^cours figé")),
    ("saut de cours", re.compile(r"^saut de cours anormal")),
]


# ---------- petits outils, au sens du JavaScript ----------
def jround(x):
    """Math.round : moitié vers le haut, négatifs compris (−2,5 → −2)."""
    return math.floor(x + 0.5)


def to_fixed(x, k):
    """(x).toFixed(k) relu en nombre : valeur binaire exacte, moitié loin de zéro."""
    return float(Decimal(x).quantize(Decimal(1).scaleb(-k), rounding=ROUND_HALF_UP))


def mean(a):
    t = 0.0
    for v in a:
        t += v
    return t / len(a)


def positive(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def js_key_order(keys):
    """Ordre des clés d'un objet JavaScript : entiers d'abord (croissants), puis ordre d'insertion."""
    num = [k for k in keys if re.fullmatch(r"0|[1-9]\d*", k) and int(k) < 2 ** 32 - 1]
    return sorted(num, key=int) + [k for k in keys if k not in set(num)]


def days_between(a, b):
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


# ---------- seuils lus dans le moteur ----------
def engine_constants(core_src):
    """Seuils du moteur lus dans core.js ; une constante introuvable arrête le contrôle (rapport en erreur)."""
    c = {}
    for name in ("RANK_JUMP_UP", "RANK_JUMP_DOWN", "VOL_WILD", "SHORT_MIN"):
        m = re.search(r"ES\." + name + r"\s*=\s*([0-9.]+)\s*;", core_src)
        if not m:
            raise ValueError(f"seuil ES.{name} introuvable dans core.js")
        c[name] = float(m.group(1))
    m = re.search(r"ES\.SHORT_EXCLUDE\s*=\s*\{([^}]*)\}", core_src)
    if not m:
        raise ValueError("ES.SHORT_EXCLUDE introuvable dans core.js")
    c["SHORT_EXCLUDE"] = set(re.findall(r"(\w+)\s*:\s*true", m.group(1)))
    m = re.search(r"ES\.slopeClass = function[\s\S]*?slope >= ([0-9.]+)[\s\S]*?slope >= ([0-9.]+)", core_src)
    if not m:
        raise ValueError("seuils de pente de ES.slopeClass introuvables dans core.js")
    c["SLOPE_STRONG"], c["SLOPE_MID"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"ES\.pickThree = function \(rows, opt\) \{\s*var o = Object\.assign\(\{([^}]*)\}", core_src)
    if not m:
        raise ValueError("réglages par défaut de ES.pickThree introuvables dans core.js")
    pick = {k: float(v) for k, v in re.findall(r"(\w+)\s*:\s*([0-9.e+]+)", m.group(1))}
    for k in ("momMin", "momMax", "liqMin", "volMin", "perSec"):
        if k not in pick:
            raise ValueError(f"réglage {k} de ES.pickThree introuvable dans core.js")
    c["PICK"] = pick
    m = re.search(r"ES\.EEA = \[([^\]]*)\]", core_src)
    if not m:
        raise ValueError("liste ES.EEA introuvable dans core.js")
    c["EEA"] = set(re.findall(r"'([A-Z]{2})'", m.group(1)))
    return c


# ---------- repères d'une société (cours journaliers sur un an, hebdomadaires sur 5 ans, volumes hebdomadaires) ----------
def features(daily, weekly, wvol):
    D = [float(v) for v in (daily or []) if positive(v)]
    W = [float(v) for v in (weekly or []) if positive(v)]
    WV = [float(v) if positive(v) else None for v in (wvol or [])]
    # erreurs isolées de Yahoo : semaine ×2,5 puis retour (ou l'inverse) remplacée par la moyenne de ses voisines
    for z in range(1, len(W) - 1):
        up, down = W[z] / W[z - 1], W[z + 1] / W[z]
        if (up > 2.5 and down < 0.4) or (up < 0.4 and down > 2.5):
            W[z] = (W[z - 1] + W[z + 1]) / 2
    # dernière clôture hebdomadaire alignée sur la dernière journalière si elles divergent de plus de 15 %
    if D and W:
        q = W[-1] / D[-1]
        if q > 1.15 or q < 0.87:
            W[-1] = D[-1]
    f = {}
    if len(D) >= 2:
        dq = D[-1] / D[-2]
        if dq > 1.4 or dq < 0.6:
            f["dayJump"] = jround((dq - 1) * 100)
    last = D[-1] if D else (W[-1] if W else None)
    if not last:
        return None
    f["last"] = last
    if len(W) >= 53:
        f["mom"] = W[-5] / W[-53] - 1  # 12 mois sans le dernier mois
    high = sma50 = sma200 = None
    if len(D) >= 200:
        high, sma50, sma200 = max(D[-252:]), mean(D[-50:]), mean(D[-200:])
    elif len(W) >= 40:
        high, sma50, sma200 = max(W[-52:]), mean(W[-10:]), mean(W[-40:])
    f["sma50"] = sma50
    if high:
        f["ratio"] = min(1, last / high)
    if sma200:
        f["trend"] = "up" if (sma50 > sma200 and last > sma200) else "part" if last > sma200 else "down"

    def volatility(n):
        r = [W[k] / W[k - 1] - 1 for k in range(len(W) - n, len(W))]
        m = mean(r)
        s = 0.0
        for x in r:
            s += (x - m) * (x - m)
        return math.sqrt(s / len(r)) * math.sqrt(52)

    if len(W) >= 27:
        f["vol"] = volatility(26)
    if len(W) >= 53:
        f["vol52"] = volatility(52)
    if len(W) >= 26:  # pente : régression du logarithme des 26 dernières clôtures hebdomadaires, rythme annuel
        ys = [math.log(v) for v in W[-26:]]
        xm, ym = (len(ys) - 1) / 2, mean(ys)
        sxy = sxx = 0.0
        for i, y in enumerate(ys):
            sxy += (i - xm) * (y - ym)
            sxx += (i - xm) * (i - xm)
        f["slope"] = math.exp(sxy / sxx * 52) - 1
    jump = None
    for j in range(max(1, len(W) - 53), len(W)):
        q = W[j] / W[j - 1]
        if (q > CONST["RANK_JUMP_UP"] or q < CONST["RANK_JUMP_DOWN"]) and (
            jump is None or abs(math.log(q)) > abs(math.log(jump[0]))
        ):
            jump = (q, len(W) - 1 - j)
    f["jump"] = jump
    # volumes des 10 dernières semaines rapportés à ceux de l'année
    year = WV[-52:]
    known = [v for v in year if v is not None]
    if len(year) >= 52 and len(known) >= 45:
        recent = [v for v in year[-10:] if v is not None]
        if len(recent) >= 8:
            f["volx"] = jround(mean(recent) / mean(known) * 10) / 10
    # bond : une semaine à +8 % ou plus sur au moins 3 fois le volume moyen de l'année, dans les 8 dernières semaines
    for kb in range(8):
        vi, wi = len(WV) - 1 - kb, len(W) - 1 - kb
        if vi < 52 or wi - 1 < 0:
            break
        base = [v for v in WV[vi - 52:vi] if v is not None]
        if len(base) >= 40 and WV[vi] is not None and W[wi] / W[wi - 1] - 1 >= 0.08 and WV[vi] >= 3 * mean(base):
            f["bump"] = kb
            break
    # sortie de base : nouveau plus haut sur un an dans les 4 dernières semaines, après un cours à plus de 25 % sous son plus haut
    if len(W) >= 82:
        def top(a, b):
            m = 0
            for i in range(a, b + 1):
                if W[i] > m:
                    m = W[i]
            return m

        for t in range(len(W) - 1, len(W) - 5, -1):
            if W[t] >= 0.999 * top(t - 51, t) and W[t - 26] / top(t - 77, t - 26) < 0.75:
                f["brk"] = len(W) - 1 - t
                break
    return f


# ---------- classement ----------
def percentile(sorted_vals, v):
    n = len(sorted_vals)
    if not n or v is None:
        return None
    lo, hi = bisect_left(sorted_vals, v), bisect_right(sorted_vals, v)
    return (lo + (hi - lo) / 2) / n


def slope_class(slope, trend):
    if slope is None or trend != "up":
        return None
    return "strong" if slope >= CONST["SLOPE_STRONG"] else "mid" if slope >= CONST["SLOPE_MID"] else "light"


def rank_universe(items, rcfg, today):
    """items : [{key, isin, sym, name, sector, secEn, turnover, pea, lastDay, f, acc, accOut, insiders, short}] dans l'ordre du
    catalogue ; renvoie les lignes triées comme le moteur (écartées en dernier, note, rang sur 12 mois)."""
    w, min_t = rcfg["w"], rcfg["minTurnoverEur"]
    pool = [x for x in items if x["f"] and x["f"].get("mom") is not None and (x["turnover"] or 0) >= min_t]
    moms = sorted(x["f"]["mom"] for x in pool)
    vols = sorted(x["f"]["vol"] for x in pool if x["f"].get("vol") is not None)
    rows = []
    for order, x in enumerate(items):
        f = x["f"] or {}
        out = []
        if (x["turnover"] or 0) < min_t:
            out.append("liquidité")
        if f.get("mom") is None:
            out.append("moins d'un an")
        mp = percentile(moms, f.get("mom")) if f.get("mom") is not None else None
        vp = percentile(vols, f.get("vol")) if f.get("vol") is not None else None
        if mp is not None and mp < 1 / 3:
            out.append("tiers faible")
        out += x["accOut"]
        if today and x["lastDay"] and days_between(x["lastDay"], today) > 7:
            out.append("cours figé")
        if f.get("jump"):
            out.append("saut de cours")
        ratio, trend, acc = f.get("ratio"), f.get("trend"), x["acc"]
        parts = {
            "mom": jround(w["mom"] * mp) if mp is not None else 0,
            "high": jround(w["high"] * clamp((ratio - rcfg["highFloor"]) / (1 - rcfg["highFloor"]), 0, 1))
            if ratio is not None
            else 0,
            "trend": w["trend"] if trend == "up" else jround(w["trend"] / 3) if trend == "part" else 0,
            "accounts": jround(w["accounts"] * 0.4)
            if acc is None
            else jround(w["accounts"] / 2)
            if acc in ("fin", "mixed")
            else w["accounts"]
            if acc == "good"
            else 0
            if acc == "bad"
            else jround(w["accounts"] * 0.4),
            "calm": jround(w["calm"] / 2)
            if vp is None
            else w["calm"]
            if vp < 1 / 3
            else jround(w["calm"] / 2)
            if vp < 2 / 3
            else 0,
            "insiders": x["insiders"],
        }
        note = clamp(sum(parts.values()), 0, 100)
        verdict = "out" if out else "top" if note >= rcfg["top"] else "good" if note >= rcfg["good"] else "mid"
        slope = f.get("slope")
        slope_r = jround(slope * 1000) / 1000 if slope is not None else None
        rows.append({
            "key": x["key"], "isin": x["isin"], "sym": x["sym"], "name": x["name"], "order": order,
            "sector": x["sector"], "secEn": x["secEn"], "turnover": x["turnover"], "pea": x["pea"],
            "out": out, "parts": parts, "note": note, "v": verdict, "mp": mp, "acc": acc, "short": x["short"],
            "mom": f.get("mom"), "ratio": f.get("ratio"), "trend": trend,
            "sc": slope_class(slope, trend), "slope6": jround((math.sqrt(1 + slope_r) - 1) * 100) if slope_r is not None else None,
            "volx": f.get("volx"), "dayJump": f.get("dayJump"), "bump": f.get("bump"), "brk": f.get("brk"),
            "vola": jround(f["vol52"] * 100) if f.get("vol52") is not None else None,
            "ma10": jround((f["last"] / f["sma50"] - 1) * 1000) / 10 if (f.get("sma50") or 0) > 0 and (f.get("last") or 0) > 0
            else None,
        })
    rows.sort(key=lambda r: (1 if r["out"] else 0, -r["note"], -(r["mp"] or 0), r["order"]))
    k = 0
    for r in rows:
        if not r["out"]:
            k += 1
            r["pos"] = k
    return rows


# ---------- sélection (règles du bouton 🎯 et de l'email du lundi) ----------
def pick(rows, n, pea_only=False):
    """rows : lignes au format de la sélection (mom en %, liq en €…), dans l'ordre du classement ; renvoie [(ligne, palier)]."""
    o = CONST["PICK"]
    mom_min, mom_max, liq_min, vol_min, per_sec = o["momMin"], o["momMax"], o["liqMin"], o["volMin"], int(o["perSec"])

    def not_pea(r):
        return r["pea"] is False

    def tier(r):
        if r["out"] or (pea_only and not_pea(r)):
            return None
        if r["dj"] is not None:
            return None
        if r["vo"] is not None and r["vo"] >= CONST["VOL_WILD"] * 100:
            return None
        if r["sh"] is not None and r["sh"] >= CONST["SHORT_MIN"] and r["shc"] in CONST["SHORT_EXCLUDE"]:
            return None
        m, liq = r["mom"], r["liq"] or 0
        if m is None or m > mom_max:
            return None
        if r["acc"] == "good" and r["sc"] == "strong" and m >= mom_min and liq >= liq_min:
            return 0
        if r["acc"] == "good" and r["sc"] in ("strong", "mid") and m >= 30 and liq >= liq_min:
            return 1
        if r["acc"] != "bad" and r["sc"] in ("strong", "mid") and m >= 30 and liq >= 1e6:
            return 2
        return None

    hot = lambda r: 1 if r["vx"] is not None and r["vx"] >= vol_min else 0  # noqa: E731
    bump = lambda r: 1 if r["bp"] is not None else 0  # noqa: E731
    wait = lambda r: 1 if r["m10"] is not None and r["m10"] < 0 else 0  # noqa: E731
    cand = [[], [], []]
    for r in rows:
        t = tier(r)
        if t == 1 and bump(r) and not wait(r):
            t = 0  # 📣 repêche la règle assouplie
        if t is not None:
            cand[t].append(r)
    for c in cand:
        c.sort(key=lambda r: (-(2 * hot(r) + bump(r)), wait(r), -r["note"], -(r["slope6"] or 0)))
    picks, used, seen = [], set(), {}

    def take(max_per_sec):
        for t in range(3):
            if len(picks) >= n:
                break
            for r in cand[t]:
                s = r["sec"] or "?"
                if len(picks) >= n or r["key"] in used or seen.get(s, 0) >= max_per_sec:
                    continue
                used.add(r["key"])
                seen[s] = seen.get(s, 0) + 1
                picks.append((r, t))

    take(per_sec)
    if len(picks) < n:
        take(per_sec + 1)
    return picks


def selection_rows(rows):
    """Lignes du moteur telles que les lit la sélection du lundi (ES.rankSelection) : arrondies comme les lignes publiées, secteur seul."""
    return [{
        "key": r["key"], "note": r["note"], "out": r["out"], "acc": r["acc"], "pea": r["pea"], "sec": r["sector"],
        "sc": r["sc"], "mom": to_fixed(r["mom"] * 100, 1) if r["mom"] is not None else None, "dj": r["dayJump"],
        "liq": jround(r["turnover"]) if r["turnover"] is not None else None,
        "vx": r["volx"], "vo": r["vola"], "m10": r["ma10"], "bp": r["bump"],
        "sh": (r["short"] or {}).get("pct"), "shc": (r["short"] or {}).get("cc"), "slope6": None,
    } for r in rows]


def published_rows(rows):
    """Lignes telles que publiées (arrondies, secteur anglais d'abord) : celles que lisent les 10 🎯."""
    return [{
        "key": r["key"], "isin": r["isin"], "sym": r["sym"], "note": r["note"], "out": r["out"], "acc": r["acc"],
        "pea": False if r["pea"] is False else None, "sec": r["secEn"] or r["sector"], "sc": r["sc"],
        "mom": to_fixed(r["mom"] * 100, 1) if r["mom"] is not None else None, "dj": r["dayJump"],
        "liq": jround(r["turnover"]) if r["turnover"] is not None else None, "vx": r["volx"], "vo": r["vola"],
        "m10": r["ma10"], "bp": r["bump"], "sh": (r["short"] or {}).get("pct"), "shc": (r["short"] or {}).get("cc"),
        "slope6": r["slope6"],
    } for r in rows]


def isin_tables(data_dir):
    """Symbole → ISIN des listes officielles (data/backup-isins.json) puis des ventes à découvert (data/shorts-symbols.json),
    dans l'ordre du moteur ; un fichier absent ou illisible est ignoré, comme dans le moteur."""
    out = []
    try:
        with open(os.path.join(data_dir, "backup-isins.json"), encoding="utf-8") as fh:
            bk = json.load(fh)
        t = {}
        for isin, v in ((bk or {}).get("isins") or {}).items():
            if isinstance(v, list) and v and isinstance(v[0], str):
                t.setdefault(v[0], isin)
        out.append(t)
    except Exception:
        pass
    try:
        with open(os.path.join(data_dir, "shorts-symbols.json"), encoding="utf-8") as fh:
            ss = json.load(fh)
        t = {}
        for isin, sym in (ss or {}).items():
            if isinstance(sym, str):
                t.setdefault(sym, isin)
        out.append(t)
    except Exception:
        pass
    return out


# ---------- lecture des données ----------
def load_catalogue(data_dir):
    folder = os.path.join(data_dir, "societes")
    co, w_dates, d_dates = {}, [], []
    for name in sorted(os.listdir(folder)):  # même ordre que le moteur (Node trie les noms de fichiers)
        if not re.fullmatch(r"\d+\.json", name):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                sh = json.load(fh)
        except Exception:
            continue
        if not isinstance(sh, dict) or not isinstance(sh.get("items"), dict):
            continue
        if isinstance(sh.get("wDates"), list) and len(sh["wDates"]) > len(w_dates):
            w_dates = sh["wDates"]
        if isinstance(sh.get("dDates"), list) and len(sh["dDates"]) > len(d_dates):
            d_dates = sh["dDates"]
        co.update(sh["items"])
    return co, w_dates, d_dates


def build_items(main, co, d_dates, engine_rows, isin_tables=None):
    inst = main.get("inst") or {}
    isin_of_sym = {}
    for isin in js_key_order(list(inst)):
        t = (inst[isin] or {}).get("ticker")
        if t and t not in isin_of_sym:
            isin_of_sym[t] = isin
    # ISIN connu par ailleurs (listes officielles des bourses, ventes à découvert) : son pays décide du PEA
    isin_any = dict(isin_of_sym)
    for table in isin_tables or []:
        for sym, isin in table.items():
            isin_any.setdefault(sym, isin)
    items = []
    for sym in js_key_order(list(co)):
        x = co[sym] or {}
        isin = isin_of_sym.get(sym)
        i = inst.get(isin) if isin else None
        key = isin or sym
        eng = engine_rows.get(key) or {}
        last_day = None
        d = x.get("d") or []
        for k in range(len(d) - 1, -1, -1):
            if positive(d[k]):
                last_day = d_dates[k] if k < len(d_dates) and d_dates[k] else None
                break
        known = isin or isin_any.get(sym) or ""
        non_pea = ((i and i.get("peaStatus") == "non_eligible") or re.match(r"REIT\b", str(x.get("industry") or ""), re.I)
                   or (re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", known) and known[:2] not in CONST["EEA"]))
        fund_sector = ((i or {}).get("fund") or {}).get("sector")
        items.append({
            "key": key, "isin": isin, "sym": sym, "name": (i or {}).get("name") or x.get("name") or sym,
            "sector": x.get("sector") or None, "secEn": x.get("sector") or fund_sector or None,
            "turnover": x.get("turnoverEur"), "pea": False if non_pea else x.get("pea") is not False,
            "lastDay": last_day, "f": features(x.get("d"), x.get("w"), x.get("wv")),
            # repris du moteur : comptes, dirigeants, ventes à découvert
            "acc": eng.get("acc"), "accOut": [t for t in eng.get("out") or [] if ACC_OUT.search(t)],
            "insiders": (eng.get("parts") or {}).get("insiders", 0),
            "short": {"pct": eng.get("sh"), "cc": eng.get("shc")} if eng.get("sh") is not None else None,
        })
    return items


# ---------- comparaison ----------
# repères tirés des cours d'abord, puis ce qui en découle (rang sur 12 mois, points, note, verdict, place) : les exemples du
# rapport montrent la cause avant ses conséquences
FIELDS = ["mom", "ratio", "trend", "sc", "slope6", "vx", "vo", "m10", "bp", "dj", "brk", "liq", "pea", "out",
          "momPct", "parts", "note", "v", "pos"]
LABELS = {
    "mom": "hausse sur 12 mois (%)", "ratio": "cours / plus haut sur un an (%)", "trend": "tendance de fond",
    "sc": "classe de pente", "slope6": "pente sur 6 mois (%)", "vx": "volumes (×)", "vo": "volatilité (%/an)",
    "m10": "écart à la moyenne 10 semaines (%)", "bp": "bond sur gros volume (semaines)", "dj": "variation du jour (%)",
    "brk": "sortie de base (semaines)", "liq": "échanges par jour (€)", "pea": "PEA", "out": "raisons d'écarter",
    "momPct": "rang sur 12 mois", "parts": "points", "note": "note", "v": "verdict", "pos": "place", "société": "société",
}


def price_out(texts):
    cats = []
    for t in texts or []:
        for cat, rx in PRICE_OUT:
            if rx.search(t):
                cats.append(cat)
    return sorted(cats)


def twin_view(r):
    """Valeurs publiées que doit retrouver le moteur, calculées ici."""
    return {
        "mom": to_fixed(r["mom"] * 100, 1) if r["mom"] is not None else None,
        "momPct": jround(r["mp"] * 100) if r["mp"] is not None else None,
        "ratio": to_fixed(r["ratio"] * 100, 1) if r["ratio"] is not None else None,
        "trend": r["trend"], "sc": r["sc"], "slope6": r["slope6"], "vx": r["volx"], "vo": r["vola"], "m10": r["ma10"],
        "bp": r["bump"], "dj": r["dayJump"], "brk": r["brk"],
        "liq": jround(r["turnover"]) if r["turnover"] is not None else None,
        "pea": False if r["pea"] is False else None,
        "parts": {k: v for k, v in r["parts"].items() if k != "insiders"},
        "note": r["note"], "v": r["v"], "pos": r.get("pos"), "out": sorted(c for c in r["out"] if not ACC_OUT.search(c)),
    }


def engine_view(e):
    return {
        "mom": e.get("mom"), "momPct": e.get("momPct"), "ratio": e.get("ratio"), "trend": e.get("trend"),
        "sc": e.get("sc"), "slope6": e.get("slope6"), "vx": e.get("vx"), "vo": e.get("vo"), "m10": e.get("m10"),
        "bp": e.get("bp"), "dj": e.get("dj"), "brk": e.get("brk"), "liq": e.get("liq"),
        "pea": False if e.get("pea") is False else None,
        "parts": {k: v for k, v in (e.get("parts") or {}).items() if k != "insiders"},
        "note": e.get("note"), "v": e.get("v"), "pos": e.get("pos"), "out": price_out(e.get("out")),
    }


def same(field, a, b):
    if a is None or b is None:
        return a is None and b is None
    if field == "slope6":  # logarithme et exponentielle : la bibliothèque mathématique peut différer d'un dernier chiffre
        return abs(a - b) <= 1
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= 1e-9
    return a == b


def run(data_dir):
    t0 = time.time()
    with open(os.path.join(data_dir, "euro-signal.json"), encoding="utf-8") as fh:
        main = json.load(fh)
    rank = main.get("rank") or {}
    if not rank.get("rows"):
        raise ValueError("classement absent de euro-signal.json")
    rcfg = (main.get("cfg") or {}).get("rank")
    if not rcfg:
        raise ValueError("réglages du classement (cfg.rank) absents de euro-signal.json")
    co, _, d_dates = load_catalogue(data_dir)
    if not co:
        raise ValueError("catalogue des sociétés (data/societes) vide ou illisible")
    engine = {r["key"]: r for r in rank["rows"]}
    rows = rank_universe(build_items(main, co, d_dates, engine, isin_tables(data_dir)), rcfg, main.get("today"))
    twin = {r["key"]: r for r in rows}
    by_field, found, n = {}, [], 0
    for key, e in engine.items():
        r = twin.get(key)
        if not r:
            by_field["absente"] = by_field.get("absente", 0) + 1
            found.append((-1, {"name": e.get("name"), "field": "société", "engine": "classée", "twin": "absente"}))
            continue
        n += 1
        a, b = engine_view(e), twin_view(r)
        for k, fld in enumerate(FIELDS):
            if not same(fld, a[fld], b[fld]):
                by_field[fld] = by_field.get(fld, 0) + 1
                found.append((k, {"name": e.get("name"), "field": fld, "engine": a[fld], "twin": b[fld]}))
    found.sort(key=lambda x: x[0])  # tri stable : la cause avant ses conséquences, dans l'ordre du classement
    examples = [dict(x, label=LABELS.get(x["field"], x["field"])) for _, x in found[:30]]
    by_label = {LABELS.get(k, k): v for k, v in sorted(by_field.items(), key=lambda kv: FIELDS.index(kv[0]) if kv[0] in FIELDS else -1)}
    # sélection du lundi : ES.rankSelection (PEA seulement, palier 0 ou 1, note minimale) ; 10 🎯 : ES.pickN sur les lignes publiées
    sel_rows = selection_rows(rows)
    sel = [r["key"] for r, t in pick(sel_rows, int(rcfg["selSize"]), pea_only=True) if t < 2 and r["note"] >= rcfg["selMin"]]
    shown = [r for r in rows if (r["turnover"] or 0) >= rcfg["minTurnoverEur"] or r["isin"]]
    pea_only = ((main.get("cfg") or {}).get("selection") or {}).get("peaOnly") is not False
    p10 = [r["isin"] or r["sym"] for r, _ in pick(published_rows(shown), 10, pea_only=pea_only)]
    eng_sel = [x.get("key") for x in (rank.get("selection") or {}).get("items") or []]
    eng_p10 = rank.get("pick10") or []
    name = {r["key"]: r["name"] for r in rows}
    name.update({r["isin"] or r["sym"]: r["name"] for r in rows})
    # trous dans les cours hebdomadaires de l'année d'une société de la sélection : la hausse sur 12 mois porte alors sur plus d'un an
    gaps = []
    for k in eng_sel:
        r = twin.get(k)
        x = co.get(r["sym"]) if r else None
        if x and any(not positive(v) for v in (x.get("w") or [])[-53:]):
            gaps.append(name.get(k, k))
    diffs = sum(by_field.values())
    return {
        "date": main.get("today"), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engineAt": main.get("generatedAt"), "rows": n, "catalogue": len(co), "diffs": diffs, "byField": by_field,
        "byLabel": by_label, "examples": examples,
        "selection": {"same": sel == eng_sel, "engine": [name.get(k, k) for k in eng_sel], "twin": [name.get(k, k) for k in sel]},
        "pick10": {"same": p10 == eng_p10, "engine": [name.get(k, k) for k in eng_p10], "twin": [name.get(k, k) for k in p10]},
        "gaps": gaps, "error": None, "seconds": round(time.time() - t0, 1),
    }


CONST = {}


def main(argv):
    data_dir = os.path.join(ROOT, "data")
    if "--data" in argv:
        data_dir = argv[argv.index("--data") + 1]
    out_path = os.path.join(data_dir, "diagnostics", "twin.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        with open(os.path.join(HERE, "core.js"), encoding="utf-8") as fh:
            CONST.update(engine_constants(fh.read()))
        rep = run(data_dir)
        code = 0
    except Exception as e:  # le contrôle n'a pas pu se faire : rapport en erreur, lu par le contrôle des fichiers
        today = None
        try:
            with open(os.path.join(data_dir, "euro-signal.json"), encoding="utf-8") as fh:
                today = json.load(fh).get("today")
        except Exception:
            pass
        rep = {"date": today, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": f"{type(e).__name__}: {e}"}
        code = 1
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    if rep.get("error"):
        print("Double calcul impossible : " + rep["error"])
    else:
        print(f"Double calcul : {rep['rows']} sociétés comparées ({rep['catalogue']} au catalogue), {rep['diffs']} écart(s)"
              + (f" {rep['byField']}" if rep["diffs"] else "") + f" ; sélection des 5 {'identique' if rep['selection']['same'] else 'DIFFÉRENTE'}"
              f" ; 10 🎯 {'identiques' if rep['pick10']['same'] else 'DIFFÉRENTES'} ({rep['seconds']} s)")
        for ex in rep["examples"][:10]:
            print(f"  · {ex['name']} : {ex['field']} moteur {ex['engine']} / double calcul {ex['twin']}")
        if not rep["selection"]["same"]:
            print("  sélection du moteur : " + ", ".join(rep["selection"]["engine"]))
            print("  sélection recalculée : " + ", ".join(rep["selection"]["twin"]))
        if "--strict" in argv and (rep["diffs"] or not rep["selection"]["same"] or not rep["pick10"]["same"]):
            code = 2  # une modification du moteur doit être reportée dans le double calcul (et inversement)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
