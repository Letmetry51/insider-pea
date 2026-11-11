"""Indicateurs techniques sans dépendance (listes de floats, ordre chronologique)."""
import math


def sma(x, n):
    out, s = [], 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def ema(x, n):
    k, out, e = 2 / (n + 1), [], None
    for v in x:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def rsi(x, n=14):
    """RSI de Wilder : amorçage par la moyenne simple des n premières variations, puis lissage alpha = 1/n."""
    out = [None] * len(x)
    if len(x) <= n:
        return out
    d = [x[i] - x[i - 1] for i in range(1, len(x))]
    au = sum(max(v, 0.0) for v in d[:n]) / n
    ad = sum(max(-v, 0.0) for v in d[:n]) / n

    def val(u, dn):
        return 100.0 if dn == 0 else 100 - 100 / (1 + u / dn)

    out[n] = val(au, ad)
    for i in range(n, len(d)):
        au += (max(d[i], 0.0) - au) / n
        ad += (max(-d[i], 0.0) - ad) / n
        out[i + 1] = val(au, ad)
    return out


def macd(x, fast=12, slow=26, sig=9):
    m = [a - b for a, b in zip(ema(x, fast), ema(x, slow))]
    s = ema(m, sig)
    return m, s, [a - b for a, b in zip(m, s)]


def bollinger(x, n=20, k=2.0):
    mid, pb, width = sma(x, n), [], []
    for i in range(len(x)):
        if mid[i] is None:
            pb.append(None)
            width.append(None)
            continue
        w = x[i - n + 1:i + 1]
        sd = math.sqrt(sum((v - mid[i]) ** 2 for v in w) / (n - 1))
        lo, hi = mid[i] - k * sd, mid[i] + k * sd
        pb.append((x[i] - lo) / (hi - lo) if hi > lo else 0.5)
        width.append((hi - lo) / mid[i] * 100 if mid[i] else None)
    return mid, pb, width


def divergence(x, r, n=20):
    """Nouveau plus bas (haut) du prix sur les n dernières séances sans nouveau plus bas (haut) du RSI."""
    if len(x) < 2 * n or any(v is None for v in r[-2 * n:]):
        return "aucune"
    p_now, p_prev, r_now, r_prev = x[-n:], x[-2 * n:-n], r[-n:], r[-2 * n:-n]
    if min(p_now) < min(p_prev) and min(r_now) > min(r_prev):
        return "haussière"
    if max(p_now) > max(p_prev) and max(r_now) < max(r_prev):
        return "baissière"
    return "aucune"


def last_cross(h):
    """Dernier changement de signe de l'histogramme MACD : (index, 'haussier'|'baissier') ou None."""
    for i in range(len(h) - 1, 0, -1):
        if h[i] is not None and h[i - 1] is not None and (h[i] > 0) != (h[i - 1] > 0):
            return i, "haussier" if h[i] > 0 else "baissier"
    return None


def analyse(dates, x):
    """Tableau technique complet d'une série de clôtures."""
    n = len(x)
    if n < 30:
        return {"seances": n, "insuffisant": True}
    last = x[-1]
    out = {"seances": n, "du": dates[0], "au": dates[-1], "dernier": round(last, 2)}
    for k, lab in ((5, "var1s"), (21, "var1m"), (63, "var3m")):
        if n > k:
            out[lab] = round((last / x[-1 - k] - 1) * 100, 1)
    for m in (20, 50, 200):
        if n >= m:
            v = sma(x, m)
            out[f"mm{m}"] = round(v[-1], 2)
            out[f"ecart_mm{m}"] = round((last / v[-1] - 1) * 100, 1)
            if n >= m + 10:
                out[f"pente_mm{m}"] = round((v[-1] / v[-11] - 1) * 100, 2)
    r = rsi(x)
    out["rsi"] = round(r[-1], 1) if r[-1] is not None else None
    out["rsi_5j"] = round(r[-6], 1) if n > 20 and r[-6] is not None else None
    m, s, h = macd(x)
    out.update(macd=round(m[-1], 2), macd_signal=round(s[-1], 2), histo=round(h[-1], 2), histo_5j=round(h[-6], 2) if n > 6 else None)
    lc = last_cross(h)
    if lc:
        out["croisement_macd"] = {"date": dates[lc[0]], "sens": lc[1]}
    _, pb, wd = bollinger(x)
    out["boll_pb"] = round(pb[-1], 2) if pb[-1] is not None else None
    out["boll_largeur"] = round(wd[-1], 1) if wd[-1] is not None else None
    out["divergence"] = divergence(x, r)
    w3 = x[-min(n, 63):]
    out["haut3m"], out["bas3m"] = round(max(w3), 2), round(min(w3), 2)
    out["bas3m_hier"] = round(min(x[-min(n, 64):-1]), 2)
    out["haut3m_hier"] = round(max(x[-min(n, 64):-1]), 2)
    # retracements de Fibonacci du dernier mouvement (plus haut et plus bas des 3 derniers mois)
    hi_i = max(range(n - len(w3), n), key=lambda i: x[i])
    lo_i = min(range(n - len(w3), n), key=lambda i: x[i])
    hi, lo = x[hi_i], x[lo_i]
    if hi > lo:
        if hi_i < lo_i:  # baisse : retracements vers le haut depuis le plus bas
            out["fibo"] = {"sens": "baisse", "38.2": round(lo + 0.382 * (hi - lo), 2), "50": round(lo + 0.5 * (hi - lo), 2),
                           "61.8": round(lo + 0.618 * (hi - lo), 2)}
        else:
            out["fibo"] = {"sens": "hausse", "38.2": round(hi - 0.382 * (hi - lo), 2), "50": round(hi - 0.5 * (hi - lo), 2),
                           "61.8": round(hi - 0.618 * (hi - lo), 2)}
    out["_rsi"], out["_histo"] = r, h
    return out


def _note(e50, p50, e20, histo, histo5, r, div=None):
    """Note technique de −2 à +2 : tendance (MM50 et sa pente, sinon MM20), élan (MACD), excès (RSI), divergence."""
    s = 0.0
    if e50 is not None and p50 is not None:
        s += 1 if e50 > 0 and p50 > 0 else -1 if e50 < 0 and p50 < 0 else 0
    elif e20 is not None:
        s += 0.5 if e20 > 0 else -0.5
    if histo is not None:
        s += 0.5 if histo > 0 else -0.5
        if histo5 is not None:
            s += 0.25 if histo > histo5 else -0.25
    if r is not None:
        s += 0.5 if r < 30 else -0.5 if r > 70 else 0
    s += {"haussière": 0.5, "baissière": -0.5}.get(div, 0)
    return max(-2.0, min(2.0, round(s, 2)))


def score_technique(a):
    """Note technique du dernier jour (tableau d'analyse())."""
    if a.get("insuffisant"):
        return None
    return _note(a.get("ecart_mm50") if "pente_mm50" in a else None, a.get("pente_mm50"), a.get("ecart_mm20"), a.get("histo"),
                 a.get("histo_5j"), a.get("rsi"), a.get("divergence"))


def score_serie(x):
    """Même note, jour par jour (backtest), sans les divergences."""
    m20, m50, r = sma(x, 20), sma(x, 50), rsi(x)
    _, _, h = macd(x)
    out = [None] * len(x)
    for i in range(60, len(x)):
        e50 = x[i] / m50[i] - 1 if m50[i] else None
        p50 = m50[i] / m50[i - 10] - 1 if m50[i] and m50[i - 10] else None
        out[i] = _note(e50, p50, x[i] / m20[i] - 1 if m20[i] else None, h[i], h[i - 5], r[i])
    return out


def sens(score):
    """Lecture d'une note technique : haussière (≥ +0,75), baissière (≤ −0,75) ou neutre."""
    if score is None:
        return None
    return "haussière" if score >= 0.75 else "baissière" if score <= -0.75 else "neutre"


def niveaux(a, pas=0.25):
    """Résistances (au-dessus du cours) et supports (en dessous) : MM20, MM50, retracements de Fibonacci, extrêmes de 3 mois.
    Deux de chaque côté, les plus proches, écartés d'au moins 1 %."""
    if a.get("insuffisant"):
        return {}
    last = a["dernier"]
    cands = [a.get("mm20"), a.get("mm50"), a.get("haut3m"), a.get("bas3m")] + \
        ([a["fibo"][k] for k in ("38.2", "50", "61.8")] if a.get("fibo") else [])
    q = sorted({round(round(v / pas) * pas, 2) for v in cands if v is not None})

    def tri(vals):
        out = []
        for v in vals:
            if not out or abs(v - out[-1]) > out[-1] * 0.01:
                out.append(v)
        return out[:2]
    return {"resistances": tri([v for v in q if v > last * 1.003]), "supports": tri([v for v in reversed(q) if v < last * 0.997])}


def lecture(a, score=None):
    """Lecture technique en clair : sens, une phrase, supports et résistances."""
    if not a or a.get("insuffisant"):
        return None
    score = score_technique(a) if score is None else score
    t = []
    if a.get("pente_mm50") is not None:
        t.append("au-dessus de sa moyenne 50 séances" + (", qui monte" if a["pente_mm50"] > 0 else ", qui baisse")
                 if a["ecart_mm50"] > 0 else "sous sa moyenne 50 séances" + (", qui baisse" if a["pente_mm50"] < 0 else ", qui monte"))
    elif a.get("ecart_mm20") is not None:
        t.append("au-dessus de sa moyenne 20 séances" if a["ecart_mm20"] > 0 else "sous sa moyenne 20 séances")
    if a.get("histo") is not None:
        t.append("élan " + ("haussier" if a["histo"] > 0 else "baissier") + " (MACD)")
    r = a.get("rsi")
    if r is not None:
        t.append(f"RSI {r:.0f}" + (" : surachat" if r > 70 else " : survente" if r < 30 else ""))
    if a.get("divergence") in ("haussière", "baissière"):
        t.append(f"divergence {a['divergence']}")
    txt = ", ".join(t)
    return {"sens": sens(score), "score": score, "texte": txt[:1].upper() + txt[1:], **niveaux(a)}
