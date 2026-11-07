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


def score_technique(a):
    """Note technique de −2 à +2 (tendance, momentum, excès, divergences)."""
    if a.get("insuffisant"):
        return None
    s = 0.0
    if "mm50" in a and "pente_mm50" in a:
        if a["ecart_mm50"] > 0 and a["pente_mm50"] > 0:
            s += 1
        elif a["ecart_mm50"] < 0 and a["pente_mm50"] < 0:
            s -= 1
    elif "mm20" in a:
        s += 0.5 if a["ecart_mm20"] > 0 else -0.5
    if a.get("histo") is not None:
        s += 0.5 if a["histo"] > 0 else -0.5
        if a.get("histo_5j") is not None:
            s += 0.25 if a["histo"] > a["histo_5j"] else -0.25
    if a.get("rsi") is not None:
        if a["rsi"] < 30:
            s += 0.5
        elif a["rsi"] > 70:
            s -= 0.5
    s += {"haussière": 0.5, "baissière": -0.5}.get(a.get("divergence"), 0)
    return max(-2.0, min(2.0, round(s, 2)))


def feu_execution(a):
    """Filtre de timing d'une tranche de vente prévue (cadre du prompt)."""
    if a.get("insuffisant"):
        return {"code": "inconnu", "texte": "Historique trop court pour le filtre technique"}
    rsi_v, pb = a.get("rsi"), a.get("boll_pb")
    cross = a.get("croisement_macd") or {}
    if (rsi_v is not None and rsi_v < 30) or (pb is not None and pb < 0.05):
        return {"code": "attendre", "texte": "Survente : ne pas vendre le creux, placer l'ordre sur un rebond (MM20 ou 38,2-50 %)"}
    hi, lo = a.get("haut3m"), a.get("bas3m")
    pos = (a["dernier"] - lo) / (hi - lo) * 100 if hi and lo and hi > lo else None
    if rsi_v is not None and rsi_v < 40 and pos is not None and pos <= 20:  # pas de seuil au fil du rasoir
        return {"code": "attendre", "texte": f"Bas du range de 3 mois ({pos:.0f} %) avec RSI faible : placer l'ordre sur un rebond plutôt que vendre"}
    if rsi_v is not None and rsi_v > 70 and (cross.get("sens") == "baissier" or a.get("divergence") == "baissière"):
        return {"code": "accelerer", "texte": "Surachat qui s'essouffle : exécuter la tranche sans attendre"}
    if rsi_v is not None and rsi_v > 70:
        return {"code": "executer", "texte": "Surachat : bon moment pour une tranche, surveiller l'essoufflement"}
    return {"code": "executer", "texte": "Pas d'excès technique : la tranche prévue peut partir"}


def niveaux(a, pas=0.25):
    """Ordres de vente au-dessus du cours (MM20, Fibonacci) et seuil de révision sous le plus bas de 3 mois."""
    if a.get("insuffisant"):
        return {}
    last = a["dernier"]
    cands = [a.get("mm20")] + ([a["fibo"][k] for k in ("38.2", "50", "61.8")] if a.get("fibo") else []) + [a.get("haut3m")]
    up = sorted({round(round(v / pas) * pas, 2) for v in cands if v is not None and v > last * 1.003})
    ordres = []
    for v in up:  # niveaux distincts d'au moins 1 %
        if not ordres or v > ordres[-1] * 1.01:
            ordres.append(v)
    return {"ordres": ordres[:3], "revision": round(round(a["bas3m"] * 0.99 / pas) * pas, 2), "support": a["bas3m"]}
