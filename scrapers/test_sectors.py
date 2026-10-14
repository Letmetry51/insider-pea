"""
Stress test opérationnel du module Secteurs : données manquantes, abîmées ou incomplètes ne doivent ni faire planter
le calcul, ni produire de valeurs absurdes dans le fichier lu par le tableau de bord. Sans réseau (données simulées).

  python scrapers/test_sectors.py
"""
import json
import math
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sectors as S  # noqa: E402

S.PLACEBO_N = 30  # vérification du fonctionnement, pas de la statistique

results = []


def case(name):
    def deco(fn):
        tmp = Path(tempfile.mkdtemp())
        for k in ("SEC", "UNIVERSE", "INFO_CACHE", "ESTIMATES", "REV_HIST", "WEEKLY", "WEEKLY_VOL", "BACKTEST", "OUT", "OUT_CO"):
            old = getattr(S, k)
            setattr(S, k, tmp / ("sectors" if k == "SEC" else old.name))
        S.SEC.mkdir(parents=True, exist_ok=True)
        try:
            S.synthetic(seed=len(results) + 1)
            fn()
            results.append(("OK  ", name, ""))
        except Exception as e:
            results.append(("ÉCHEC", name, f"{e}\n{traceback.format_exc(limit=3)}"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return fn
    return deco


def check_outputs(require_backtest=True):
    if require_backtest:
        S.run_backtest()
    S.dashboard(fetch_daily=False)
    txt = S.OUT.read_text(encoding="utf-8")
    assert "NaN" not in txt and "Infinity" not in txt, "valeur non numérique dans sectors.json"
    d = json.loads(txt)
    assert d["format"] == "euro-signal-sectors" and d["groups"], "classement vide"
    for g in d["groups"]:
        assert 0 <= (g["breadth"] or 0) <= 1 and g["rank"] >= 1, f"groupe incohérent {g['key']}"
        for k in ("rs6", "rs3"):
            v = g.get(k)
            assert v is None or abs(v) < 5, f"{k} absurde pour {g['key']} : {v}"
    co = json.loads(S.OUT_CO.read_text(encoding="utf-8"))
    assert co["items"] and all(len(v.get("w") or []) in (0, len(co["wDates"])) for v in co["items"].values()), "fiches sociétés : cours non alignés"
    assert any(v.get("roles") for v in co["items"].values()), "fiches sociétés : aucun leader ni challenger"
    ranks = [g["rank"] for g in d["groups"]]
    assert sorted(ranks) == list(range(1, len(ranks) + 1)), "rangs non consécutifs"
    return d


def mutate_weekly(fn):
    W = pd.read_csv(S.WEEKLY, index_col=0, parse_dates=True, compression="gzip")
    W = fn(W)
    W.to_csv(S.WEEKLY, compression="gzip")


@case("Données propres : test historique et classement du jour")
def _():
    d = check_outputs()
    bt = json.loads(S.BACKTEST.read_text(encoding="utf-8"))
    assert bt["stress"]["trials"] >= 20, "essais non déclarés"
    assert 0 <= bt["stress"]["deflatedSharpe"] <= 1
    assert any(t["key"] == "cyber" for t in d["themes"]), "thème cybersécurité absent"


@case("30 % de cours manquants au hasard")
def _():
    rng = np.random.default_rng(1)
    mutate_weekly(lambda W: W.mask((rng.random(W.shape) < 0.3) & ~W.columns.isin([S.BENCH, S.US_BENCH])))
    check_outputs()


@case("Erreurs de cours : prix ×1000 isolé, prix négatif, série à zéro")
def _():
    def f(W):
        c = [x for x in W.columns if x.endswith(".PA")]
        W.iloc[200, W.columns.get_loc(c[0])] *= 1000
        W.iloc[210, W.columns.get_loc(c[1])] = -5
        W[c[2]] = 0.0
        return W
    mutate_weekly(f)
    d = check_outputs()
    assert all(abs(g["rs6"] or 0) < 5 for g in d["groups"])


@case("Dates en double et dans le désordre, barres du lundi et du mercredi mélangées")
def _():
    def f(W):
        W2 = W.iloc[::3].copy()
        W2.index = W2.index - pd.Timedelta(days=2)
        return pd.concat([W, W2]).sample(frac=1, random_state=3)
    mutate_weekly(f)
    W, _ = S.load_weekly()
    assert W.index.is_monotonic_increasing and W.index.is_unique and set(W.index.dayofweek) == {4}
    check_outputs()


@case("Indice de référence absent à la fin, baromètres américains manquants")
def _():
    def f(W):
        W.iloc[-6:, W.columns.get_loc(S.BENCH)] = np.nan
        return W.drop(columns=["NVDA", "LLY", "CRWD"], errors="ignore")
    mutate_weekly(f)
    check_outputs()


@case("Univers abîmé : secteur, industrie ou capitalisation manquants")
def _():
    u = json.loads(S.UNIVERSE.read_text(encoding="utf-8"))
    for k, s in enumerate(list(u["items"])):
        if k % 4 == 0:
            u["items"][s].pop("industry", None)
        if k % 7 == 0:
            u["items"][s].pop("sector", None)
        if k % 5 == 0:
            u["items"][s]["capEur"] = None
    S.UNIVERSE.write_text(json.dumps(u), encoding="utf-8")
    check_outputs()


@case("Révisions et surprises absentes ou illisibles, volumes absents")
def _():
    S.ESTIMATES.write_text(json.dumps({"ASML.AS": {"rev": {"up30": None}}, "SU.PA": {"surprises": []}}), encoding="utf-8")
    S.WEEKLY_VOL.unlink()
    check_outputs()


@case("Historique trop court (40 semaines) : rien d'écrit, aucun plantage")
def _():
    mutate_weekly(lambda W: W.iloc[-40:])
    S.run_backtest()
    assert not S.BACKTEST.exists() or "stress" not in json.loads(S.BACKTEST.read_text(encoding="utf-8"))


@case("Sans révisions ni test historique : le tableau de bord reste lisible")
def _():
    S.ESTIMATES.unlink()
    d = check_outputs(require_backtest=False)
    assert d["backtest"] is None


@case("Moteur sans regard vers le futur : mesures à la semaine t identiques avec ou sans les semaines suivantes")
def _():
    W, V = S.load_weekly()
    uni = json.loads(S.UNIVERSE.read_text(encoding="utf-8"))["items"]
    est = json.loads(S.ESTIMATES.read_text(encoding="utf-8"))
    groups = S.groups_of(uni)
    t = 250
    full = S.group_signals(S.panels(W, W[S.BENCH], V, est), groups)
    cut = S.group_signals(S.panels(W.iloc[:t + 1], W[S.BENCH].iloc[:t + 1], V.iloc[:t + 1], est), groups)
    for k in ("rs6", "rs3", "breadth", "composite", "volume", "surprise", "trending"):
        a, b = full[k].iloc[t], cut[k].iloc[t]
        assert ((a == b) | (a.isna() & b.isna())).all(), f"{k} dépend de données futures"


if __name__ == "__main__":
    for st, name, err in results:
        print(f"{st} {name}" + (f"\n     {err}" if err else ""))
    fail = sum(1 for r in results if r[0] != "OK  ")
    print(f"\n{len(results) - fail} réussis, {fail} échoués")
    sys.exit(1 if fail else 0)
