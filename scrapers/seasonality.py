"""
Test de saisonnalité sur 30 ans d'indices : septembre-octobre sont-ils vraiment de mauvais mois, et une règle
d'exposition calendaire (moins investi en septembre-octobre, plein en novembre-janvier) bat-elle l'achat-conservation ?

Méthode (honnête plutôt que flatteuse) :
  - cours mensuels des indices (Yahoo), mois en cours exclu ; fenêtre principale = 30 dernières années complètes ;
  - rendement moyen, médian et part de mois positifs pour chaque mois calendaire, t de Student ;
    12 mois testés par indice : seuil corrigé |t| ≥ 2,9 (Bonferroni) pour parler d'un effet net ;
  - règle testée, déclarée à l'avance : 40 % investi en septembre-octobre, 100 % de novembre à janvier, 80 % sinon,
    le reste sans rendement ; frais 0,1 % par unité d'exposition changée ;
  - comparée à l'achat-conservation ET à une exposition constante de même moyenne (78 %), seule comparaison juste :
    une règle moins investie a mécaniquement moins de volatilité et de pertes ;
  - placebo : le même profil décalé sur les 11 autres positions du calendrier ; la règle n'a d'intérêt que si sa
    position réelle fait mieux que la plupart des décalages ;
  - deux moitiés de période séparées (la seconde sert de contrôle hors échantillon).

  python scrapers/seasonality.py            → data/seasonality.json
  python scrapers/seasonality.py --monthly  → ne recalcule que si le fichier a plus de 28 jours (lancé chaque nuit)
  python scrapers/seasonality.py --offline  → même calcul sur des cours simulés (vérification sans réseau)
"""
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "seasonality.json"

INDICES = [
    ("^FCHI", "CAC 40", "dividendes non inclus"),
    ("^GDAXI", "DAX", "dividendes inclus (indice de performance)"),
    ("^STOXX50E", "Euro Stoxx 50", "dividendes non inclus"),
    ("^GSPC", "S&P 500", "dividendes non inclus"),
]
YEARS = 30
RULE = {9: 0.4, 10: 0.4, 11: 1.0, 12: 1.0, 1: 1.0}  # autres mois : 0,8
OTHER = 0.8
COST = 0.001
MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def r(x, k=4):
    return None if x is None or not np.isfinite(x) else round(float(x), k)


def tstat(a):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    if len(a) < 3 or a.std(ddof=1) == 0:
        return None
    return a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or len(b) < 3:
        return None
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return None if se == 0 else (a.mean() - b.mean()) / se


def pval(t):
    return None if t is None else math.erfc(abs(t) / math.sqrt(2))


def profile(shift=0):
    """Exposition par mois calendaire (1..12), éventuellement décalée de « shift » mois (placebo)."""
    base = {m: RULE.get(m, OTHER) for m in range(1, 13)}
    return {m: base[(m - 1 - shift) % 12 + 1] for m in range(1, 13)}


def run_strategy(ret, expo):
    """ret : rendements mensuels (index = fin de mois) ; expo : dict mois → exposition. Exposition fixée d'avance."""
    e = np.array([expo[d.month] for d in ret.index])
    turn = np.abs(np.diff(np.concatenate([[e[0]], e])))
    return pd.Series(e * ret.values - COST * turn, index=ret.index)


def metrics(s):
    s = s.dropna()
    if len(s) < 24:
        return None
    eq = (1 + s).cumprod()
    yrs = len(s) / 12
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = s.std(ddof=1) * math.sqrt(12)
    dd = (eq / eq.cummax() - 1).min()
    return {"cagr": r(cagr), "vol": r(vol), "sharpe": r(cagr / vol if vol else None, 3), "maxDD": r(dd), "final": r(eq.iloc[-1], 3)}


def study(ret):
    """Toutes les mesures pour une série de rendements mensuels."""
    out = {"from": ret.index[0].strftime("%Y-%m"), "to": ret.index[-1].strftime("%Y-%m"), "months": len(ret)}
    rows = []
    for m in range(1, 13):
        a = ret[ret.index.month == m].values
        t = tstat(a)
        rows.append({"m": m, "label": MONTHS[m - 1], "n": len(a), "mean": r(a.mean()), "median": r(np.median(a)),
                     "pos": r((a > 0).mean(), 3), "t": r(t, 2)})
    out["byMonth"] = rows
    so = ret[ret.index.month.isin([9, 10])].values
    rest = ret[~ret.index.month.isin([9, 10])].values
    t = welch(so, rest)
    out["septOct"] = {"mean": r(so.mean()), "rest": r(rest.mean()), "diff": r(so.mean() - rest.mean()), "t": r(t, 2), "p": r(pval(t), 3)}
    win = ret[ret.index.month.isin([11, 12, 1, 2, 3, 4])].values
    summ = ret[ret.index.month.isin([5, 6, 7, 8, 9, 10])].values
    t = welch(win, summ)
    out["sellInMay"] = {"winter": r(win.mean()), "summer": r(summ.mean()), "diff": r(win.mean() - summ.mean()), "t": r(t, 2), "p": r(pval(t), 3)}

    rule = run_strategy(ret, profile(0))
    avg = float(np.mean([profile(0)[d.month] for d in ret.index]))
    const = ret * avg
    out["avgExposure"] = r(avg, 3)
    out["buyHold"], out["rule"], out["constant"] = metrics(ret), metrics(rule), metrics(const)
    # Placebo : 11 décalages du même profil
    sh = []
    for k in range(12):
        m = metrics(run_strategy(ret, profile(k)))
        sh.append(m["sharpe"] if m else None)
    valid = [x for x in sh if x is not None]
    out["placebo"] = {"sharpes": sh, "rank": 1 + sum(1 for x in valid[1:] if x > sh[0]) if sh[0] is not None else None, "of": len(valid)}
    # Différence mensuelle règle – exposition constante : t de la différence
    diff = (rule - const).values
    t = tstat(diff)
    out["ruleVsConstant"] = {"meanPerYear": r(diff.mean() * 12), "t": r(t, 2), "p": r(pval(t), 3)}
    return out


def verdict(res):
    """Phrase de synthèse construite à partir des chiffres, sans adjectif ajouté à la main."""
    win30 = [x["last30"] for x in res if x.get("last30")]
    if not win30:
        return "Données insuffisantes."
    beats = sum(1 for x in win30 if x["rule"]["sharpe"] > x["constant"]["sharpe"])
    halves = sum(1 for x in res if x.get("halves") and all(h["rule"]["sharpe"] > h["constant"]["sharpe"] for h in x["halves"]))
    sig = sum(1 for x in win30 if (x["septOct"]["t"] or 0) <= -2.9)
    top = sum(1 for x in win30 if x["placebo"]["rank"] is not None and x["placebo"]["rank"] <= 2)
    n = len(win30)
    parts = [f"Sur {n} indices et 30 ans, septembre-octobre est nettement plus faible que les autres mois (|t| ≥ 2,9) pour {sig} indice(s) sur {n}."]
    parts.append(f"La règle 40 / 100 / 80 % fait mieux, à risque égal, qu'une exposition constante de même moyenne pour {beats} indice(s) sur {n}, "
                 f"et dans les deux moitiés de période pour {halves} sur {n}.")
    parts.append(f"Elle se classe dans les 2 premiers des 12 décalages de calendrier pour {top} indice(s) sur {n}.")
    if beats == n and halves == n and top >= n - 1 and sig >= 1:
        parts.append("Effet saisonnier cohérent et stable : la règle peut servir de modulation de la taille des achats, pas de signal de vente.")
    elif beats >= n - 1 and halves >= n // 2:
        parts.append("Effet faible et irrégulier : au mieux un léger frein sur la taille des nouveaux achats en septembre-octobre, sans vendre.")
    else:
        parts.append("Pas d'effet exploitable : réduire l'exposition en septembre-octobre ne paie pas une fois comparé à juste titre.")
    return " ".join(parts)


def load_live():
    import yfinance as yf
    tick = [t for t, _, _ in INDICES]
    raw = yf.download(tick, start="1950-01-01", interval="1mo", auto_adjust=False, progress=False, group_by="column", threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": tick[0]})
    return close


def load_synthetic(seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1990-01-01", "2026-09-01", freq="MS")
    cols = {}
    for k, (t, _, _) in enumerate(INDICES):
        mu = np.where(idx.month.isin([9, 10]), -0.004, 0.008) if k == 0 else np.full(len(idx), 0.006)
        cols[t] = 1000 * np.cumprod(1 + mu + rng.normal(0, 0.045, len(idx)))
    return pd.DataFrame(cols, index=idx)


def monthly_returns(close):
    """Cours mensuels datés du début de mois → rendements datés de la fin du mois, mois en cours exclu, aberrations écartées."""
    close = close.copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).to_period("M").to_timestamp("M")
    close = close[~close.index.duplicated(keep="last")].sort_index()
    today = pd.Timestamp(date.today())
    close = close[close.index < today.to_period("M").to_timestamp("M")]
    ret = close.pct_change(fill_method=None)
    return ret.where(ret.abs() < 0.5)


def main():
    offline = "--offline" in sys.argv
    if "--monthly" in sys.argv and OUT.exists():
        try:
            g = datetime.fromisoformat(json.loads(OUT.read_text(encoding="utf-8"))["generatedAt"])
            if (datetime.now(timezone.utc) - g).days < 28:
                print(f"Saisonnalité à jour ({g.date()}) : rien à faire.")
                return 0
        except Exception:
            pass
    close = load_synthetic() if offline else load_live()
    ret_all = monthly_returns(close)
    res = []
    for t, name, note in INDICES:
        if t not in ret_all:
            print(f"  {name} : pas de cours")
            continue
        s = ret_all[t].dropna()
        if len(s) < 120:
            print(f"  {name} : historique trop court ({len(s)} mois)")
            continue
        last = s.index[-1]
        start = pd.Timestamp(year=last.year - YEARS, month=last.month, day=1).to_period("M").to_timestamp("M")
        s30 = s[s.index > start]
        item = {"ticker": t, "name": name, "note": note, "full": study(s), "last30": study(s30)}
        mid = len(s30) // 2
        item["halves"] = [study(s30.iloc[:mid]), study(s30.iloc[mid:])]
        res.append(item)
        a = item["last30"]
        print(f"  {name:14s} {a['from']}→{a['to']}  sept-oct {a['septOct']['mean']:+.2%} vs {a['septOct']['rest']:+.2%} (t {a['septOct']['t']})"
              f" | Sharpe achat {a['buyHold']['sharpe']} · règle {a['rule']['sharpe']} · constante {a['constant']['sharpe']}"
              f" | rang placebo {a['placebo']['rank']}/{a['placebo']['of']}")
    if not res:
        print("Aucun indice exploitable : rien d'écrit.")
        return 1
    out = {"format": "euro-signal-seasonality", "version": 1, "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "simulated": offline, "rule": {"septOct": 0.4, "novJan": 1.0, "other": OTHER, "cost": COST},
           "indices": res, "verdict": verdict(res)}
    if offline:
        print(out["verdict"])
        return 0
    OUT.write_text(json.dumps(out, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} écrit ({OUT.stat().st_size // 1024} Ko)")
    print(out["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
