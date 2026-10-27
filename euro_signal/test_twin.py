"""
Tests du double calcul (euro_signal/twin_check.py), sans réseau ni données réelles.

1. Les seuils sont bien lus dans euro_signal/core.js.
2. Mêmes repères que le moteur JavaScript (ES.rankFeatures, lancé avec Node) sur des séries construites pour les cas limites :
   trous, semaine aberrante, dernière semaine décalée, saut de cours, variation d'un jour, volumes en hausse, bond, sortie de
   base, historique court, volumes manquants.
3. Même classement, même sélection des 5 et mêmes 10 🎯 que le moteur (ES.rankUniverse, ES.rankSelection, ES.pickN) sur un
   univers construit : paliers, bond qui repêche, attente sous la moyenne 10 semaines, 2 par secteur, ventes à découvert, PEA.
4. Un écart est trouvé : chiffre faux du moteur, cours différent, sélection différente.
5. Données absentes : rapport en erreur, jamais « tout va bien ».

  python euro_signal/test_twin.py
"""
import copy
import importlib.util
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("twin_check", os.path.join(HERE, "twin_check.py"))
tw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tw)
CORE = open(os.path.join(HERE, "core.js"), encoding="utf-8").read()
tw.CONST.update(tw.engine_constants(CORE))

ok = 0
fails = []


def check(cond, label):
    global ok
    if cond:
        ok += 1
    else:
        fails.append(label)
        print("ÉCHEC  " + label)


# Node : le moteur lui-même, sur les mêmes entrées (même assemblage que euro_signal/build.mjs pour le classement)
NODE = r"""
const ES = require(process.argv[1]);
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
if (inp.mode === 'features') {
  process.stdout.write(JSON.stringify(inp.series.map((s) => ES.rankFeatures(s[0], s[1], s[2]))));
} else {
  const cfg = JSON.parse(JSON.stringify(ES.DEFAULT_CONFIG)), today = inp.today, co = inp.co, inst = inp.inst;
  const isinOfSym = {};
  Object.keys(inst).forEach((isin) => { const t = inst[isin].ticker; if (t && !isinOfSym[t]) isinOfSym[t] = isin; });
  const isinOfSymAll = Object.assign({}, isinOfSym);
  Object.keys(inp.backupIsins).forEach((is) => { const v = inp.backupIsins[is]; if (!isinOfSymAll[v[0]]) isinOfSymAll[v[0]] = is; });
  Object.keys(inp.shortsSymbols).forEach((is) => { const t = inp.shortsSymbols[is]; if (!isinOfSymAll[t]) isinOfSymAll[t] = is; });
  const outsideEea = (is) => /^[A-Z]{2}[A-Z0-9]{9}\d$/.test(is || '') && ES.EEA.indexOf(is.slice(0, 2)) < 0;
  const items = Object.keys(co).map((sym) => {
    const x = co[sym], isin = isinOfSym[sym] || null, i = isin ? inst[isin] : null, extra = inp.extra[sym] || {};
    return {
      key: isin || sym, isin, sym, name: (i && i.name) || x.name || sym, country: x.country || null,
      sector: ES.sectorFr(x.sector) || null,
      lastDay: (() => { const d = x.d || []; for (let k = d.length - 1; k >= 0; k--) if (d[k] > 0) return inp.dDates[k] || null; return null; })(),
      turnoverEur: x.turnoverEur,
      pea: (i && i.peaStatus === 'non_eligible') || /^REIT\b/i.test(String(x.industry || '')) || outsideEea(isin || isinOfSymAll[sym]) ? false : x.pea,
      f: ES.rankFeatures(x.d, x.w, x.wv), short: extra.short || null, acc: extra.acc || null, ins: extra.ins || null,
    };
  });
  const rows = ES.rankUniverse(items, cfg, { today });
  const sel = ES.rankSelection(rows, cfg);
  const shown = rows.filter((r) => (r.turnoverEur || 0) >= cfg.rank.minTurnoverEur || r.isin);
  shown.forEach((r) => { const x = co[r.sym] || {}, i = r.isin ? inst[r.isin] : null; r.secEn = x.sector || (i && i.fund && i.fund.sector) || null; });
  const slim = (r) => ({
    key: r.key, isin: r.isin, sym: r.sym, name: r.name, sector: r.sector, note: r.note, parts: r.parts, v: r.verdict.key,
    out: r.out, mom: r.mom != null ? +(r.mom * 100).toFixed(1) : null, momPct: r.momPct != null ? Math.round(r.momPct * 100) : null,
    ratio: r.ratio != null ? +(r.ratio * 100).toFixed(1) : null, trend: r.trend, liq: r.turnoverEur != null ? Math.round(r.turnoverEur) : null,
    pos: r.pos || null, acc: r.acc, slope6: r.slope != null ? Math.round((Math.sqrt(1 + r.slope) - 1) * 100) : null,
    sc: r.slopeCls || null, brk: r.brk != null ? r.brk : undefined, vx: r.volx != null ? r.volx : undefined,
    dj: r.dayJump != null ? r.dayJump : undefined, vo: r.vola != null ? r.vola : undefined, m10: r.ma10 != null ? r.ma10 : undefined,
    bp: r.bump != null ? r.bump : undefined, bh: r.bumpHi != null ? r.bumpHi : undefined, sh: r.short ? r.short.pct : undefined,
    shc: r.short ? r.short.cc : undefined,
    pea: r.pea === false ? false : undefined, secEn: r.secEn || null,
  });
  const pub = shown.map(slim);
  process.stdout.write(JSON.stringify({
    today, generatedAt: '2026-10-20T21:00:00.000Z', cfg, inst,
    rank: { rows: pub, selection: { week: 'test', items: sel.map(slim) }, pick10: ES.pickN(pub, { n: 10, peaOnly: cfg.selection.peaOnly !== false }).picks.map((p) => p.isin || p.sym) },
  }));
}
"""


def node(payload):
    r = subprocess.run(["node", "-e", NODE, os.path.join(HERE, "core.js")], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=120)
    if r.returncode:
        raise RuntimeError("Node : " + r.stderr[-800:])
    return json.loads(r.stdout)


# ---------- univers construit ----------
rng = random.Random(20261021)
N_DAYS, N_WEEKS, N_VOL = 1310, 262, 62
today = date(2026, 10, 20)
d_dates, d = [], today
while len(d_dates) < 257:
    if d.weekday() < 5:
        d_dates.append(d.isoformat())
    d -= timedelta(days=1)
d_dates.reverse()
w_dates = [(today - timedelta(days=7 * k)).isoformat() for k in range(N_WEEKS - 1, -1, -1)]


def path(drift, sigma, shape=None):
    p, out = 100.0, []
    for t in range(N_DAYS):
        mu = shape(t) if shape else drift
        p *= math.exp(mu + sigma * rng.gauss(0, 1))
        out.append(p)
    return out


def company(kind, drift=0.0, sigma=0.015, shape=None):
    P = path(drift, sigma, shape)
    D = [round(v, 4) for v in P[-257:]]
    W = [round(P[5 * k + 4], 4) for k in range(N_WEEKS)]
    W[-1] = D[-1]
    V = [int(1e6 * rng.lognormvariate(0, 0.3)) for _ in range(N_VOL)]
    if "surge" in kind:
        V[-10:] = [int(v * 2.3) for v in V[-10:]]
    if "bumphi" in kind:  # semaine à +12 % sur 2,5 fois le volume, il y a 2 semaines (📣 au plus haut de l'année seulement)
        k = N_WEEKS - 3
        W[k:] = [round(v * 1.12, 4) for v in W[k:]]
        D[-15:] = [round(v * 1.12, 4) for v in D[-15:]]
        V[-3] = int(sum(V[-55:-3]) / 52 * 2.5)
    elif "bump" in kind:  # semaine à +10 % sur 4 fois le volume, il y a 3 semaines
        k = N_WEEKS - 4
        W[k:] = [round(v * 1.10, 4) for v in W[k:]]
        D[-20:] = [round(v * 1.10, 4) for v in D[-20:]]
        V[-4] = int(sum(V[-56:-4]) / 52 * 4)
    if "dip" in kind:  # repli sous la moyenne 10 semaines
        D[-12:] = [round(v * 0.86, 4) for v in D[-12:]]
        W[-3:] = [round(v * 0.86, 4) for v in W[-3:]]
        W[-1] = D[-1]
    if "gap" in kind:
        W[-20] = None
        D[-40] = None
    if "spike" in kind:
        W[-30] = round(W[-30] * 3, 4)
    if "jump" in kind:  # regroupement d'actions non ajusté il y a 40 semaines
        W[-40:] = [round(v * 3, 4) for v in W[-40:]]
        D[-195:] = [round(v * 3, 4) for v in D[-195:]]
    if "dayjump" in kind:
        D[-1] = round(D[-1] * 1.5, 4)
        W[-1] = D[-1]
    if "diverge" in kind:
        W[-1] = round(W[-1] * 1.25, 4)
    if "short" in kind:
        W[:225] = [None] * 225
        D[:120] = [None] * 120
    if "stale" in kind:
        D[-8:] = [None] * 8
    if "novol" in kind:
        V[-30:] = [0] * 30
    return {"d": D, "w": W, "wv": V}


def breakout(t):
    # hausse, puis base à −30 % pendant 6 mois, puis nouveau plus haut sur les 3 dernières semaines
    return 0.004 if t < 1000 else -0.0035 if t < 1100 else 0.0 if t < 1290 else 0.03


SECTORS = ["Industrials", "Technology", "Energy", "Healthcare", "Consumer Cyclical"]
co, extra, inst = {}, {}, {}
good = {"key": "good", "f9": 7, "loss": False, "alt": None, "fin": False}


def add(sym, kind, drift, sector, sigma=0.015, turnover=5e6, acc=good, shape=None, **kw):
    c = company(kind, drift, sigma, shape)
    co[sym] = dict(c, name=sym, sector=sector, industry=kw.get("industry", ""), country=kw.get("country", "FR"),
                   turnoverEur=turnover, pea=kw.get("pea", True))
    extra[sym] = {"acc": acc, "short": kw.get("short"), "ins": kw.get("ins")}


for k in range(26):  # fortes hausses régulières, concentrées dans deux secteurs (règle des 2 par secteur)
    kind = ["", "surge", "bump", "surge bump", "dip", "surge dip"][k % 6]
    add(f"UP{k}", kind, 0.0036 + 0.0004 * (k % 4), SECTORS[0] if k < 10 else SECTORS[1] if k < 18 else SECTORS[2 + k % 3])
for k in range(12):  # hausses moyennes (palier assoupli), certaines repêchées par un bond
    add(f"MID{k}", ["", "bump", "surge bump", "dip bump"][k % 4], 0.0013, SECTORS[k % 5])
for k in range(30):  # le reste du marché, pour les rangs sur 12 mois
    add(f"FLAT{k}", "surge" if k % 7 == 0 else "", rng.uniform(-0.002, 0.001), SECTORS[k % 5])
# cas limites
add("GAP", "gap surge", 0.0038, "Technology")
add("SPIKE", "spike", 0.0036, "Energy")
add("JUMP", "jump", 0.0036, "Energy")
add("DAYJ", "dayjump", 0.0036, "Healthcare")
add("DIVG", "diverge surge", 0.0036, "Healthcare")
add("SHORTH", "short", 0.0036, "Healthcare")
add("STALE", "stale", 0.0036, "Industrials")
add("NOVOL", "novol", 0.0036, "Technology")
add("WILD", "surge", 0.0036, "Technology", sigma=0.07)
add("HOT", "surge", 0.0065, "Energy")  # plus de +200 % sur 12 mois
add("ILLIQ", "surge", 0.0036, "Energy", turnover=4e5)
add("SMALLQ", "surge", 0.0036, "Healthcare", turnover=2e6)  # 1 à 3 M€ par jour : palier 2 seulement
add("MIXED", "surge bump", 0.0036, "Consumer Cyclical", acc={"key": "mixed", "f9": 5, "loss": False, "alt": None, "fin": False})
add("BAD", "surge", 0.0036, "Consumer Cyclical", acc={"key": "bad", "f9": 2, "loss": True, "alt": "distress", "fin": False})
add("BANK", "surge", 0.0036, "Financial Services", acc={"key": "na", "f9": None, "loss": False, "alt": None, "fin": True})
add("NOACC", "surge", 0.0036, "Consumer Cyclical", acc=None)
add("SHFR", "surge bump", 0.0040, "Consumer Cyclical", short={"pct": 0.7, "n": 2, "cc": "FR"})
add("SHGB", "surge bump", 0.0040, "Consumer Cyclical", short={"pct": 1.1, "n": 1, "cc": "GB"}, country="GB", pea=False)
add("REIT1", "surge", 0.0036, "Real Estate", industry="REIT - Diversified")
add("NOSEC", "surge bump", 0.0040, "")
add("INSB", "surge", 0.0036, "Industrials", ins={"buys": 2, "ceo": True, "multi": 2, "netSeller": False, "ceoSale": False})
add("INSS", "surge", 0.0036, "Industrials", ins={"buys": 0, "ceo": False, "multi": 0, "netSeller": True, "ceoSale": True})
add("BRK", "", 0.0, "Basic Materials", shape=breakout)
add("OKEA", "surge bump", 0.0040, "Energy")  # siège aux îles Marshall : ISIN MH, PEA d'après le pays du siège donné par Yahoo
add("BHI", "bumphi", 0.0036, "Industrials")       # bond sur 2,5 fois le volume au plus haut de l'année
add("BHLOW", "bumphi", -0.0015, "Utilities")      # même bond en baisse : pas au plus haut de l'année
BACKUP_ISINS = {"MHY641771016": ["OKEA", "NOK"], "FR0000000052": ["UP1", "EUR"]}
SHORTS_SYMBOLS = {"GB00BTQGS779": "UP2"}
inst = {
    "FR0000000011": {"ticker": "UP3", "name": "Up Trois SA", "peaStatus": "probable"},
    "FR0000000029": {"ticker": "UP5", "name": "Up Cinq SA", "peaStatus": "non_eligible"},
    "FR0000000037": {"ticker": "NOSEC", "name": "Sans Secteur SA", "peaStatus": "probable", "fund": {"sector": "Technology"}},
    "FR0000000045": {"ticker": "ILLIQ", "name": "Peu Liquide SA", "peaStatus": "probable"},
}
syms = list(co)

# 1. seuils lus dans le moteur
check(tw.CONST["VOL_WILD"] == 0.8 and tw.CONST["SHORT_MIN"] == 0.5 and tw.CONST["SHORT_EXCLUDE"] == {"FR"},
      "seuils ⚡ et 🐻 lus dans core.js")
check(tw.CONST["PICK"]["momMin"] == 60 and tw.CONST["PICK"]["momMax"] == 200 and tw.CONST["PICK"]["liqMin"] == 3e6
      and tw.CONST["PICK"]["volMin"] == 1.5 and tw.CONST["PICK"]["perSec"] == 2, "réglages de ES.pickThree lus dans core.js")
check(tw.CONST["SLOPE_STRONG"] == 1 and tw.CONST["SLOPE_MID"] == 0.3, "seuils de pente lus dans core.js")
try:
    tw.engine_constants(CORE.replace("ES.VOL_WILD = ", "ES.VOL_WILDE = "))
    check(False, "seuil introuvable : erreur attendue")
except ValueError:
    check(True, "seuil introuvable : erreur")

# 2. mêmes repères que ES.rankFeatures
js = node({"mode": "features", "series": [[co[s]["d"], co[s]["w"], co[s]["wv"]] for s in syms]})
bad = []
for s, f_js in zip(syms, js):
    f_py = tw.features(co[s]["d"], co[s]["w"], co[s]["wv"])
    for k in ("last", "mom", "sma50", "ratio", "trend", "vol", "vol52", "volx", "bump", "bumpHi", "brk", "dayJump"):
        a, b = f_js.get(k), f_py.get(k)
        if not ((a is None and b is None) or (a is not None and b is not None and a == b)):
            bad.append((s, k, a, b))
    a, b = f_js.get("slope"), f_py.get("slope")
    if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-12 * max(1, abs(a))):
        bad.append((s, "slope", a, b))
    a, b = f_js.get("jump"), f_py.get("jump")
    if (a is None) != (b is None) or (a and (a["x"] != b[0] or a["ago"] != b[1])):
        bad.append((s, "jump", a, b))
check(not bad, "repères identiques au moteur (" + str(len(syms)) + " séries)" + (f" : {bad[:4]}" if bad else ""))
feats = {s: f for s, f in zip(syms, js)}
check(any(f.get("bump") is not None for f in js) and any((f.get("volx") or 0) >= 1.5 for f in js)
      and any(f.get("brk") is not None for f in js) and any(f.get("jump") for f in js) and any(f.get("dayJump") for f in js)
      and feats["SHORTH"].get("mom") is None and feats["NOVOL"].get("volx") is None,
      "cas limites présents (bond, volumes, sortie de base, saut, variation d'un jour, historique court, volumes manquants)")
check(feats["BHI"].get("bumpHi") == 2 and feats["BHI"].get("bump") is None and feats["BHLOW"].get("bumpHi") is None,
      "📣 bond au plus haut de l'année sur 2,5 fois le volume : repéré il y a 2 semaines, pas en baisse ("
      + str(feats["BHI"].get("bumpHi")) + ", " + str(feats["BHLOW"].get("bumpHi")) + ")")

# 3. même classement, même sélection
payload = node({"mode": "rank", "co": co, "inst": inst, "extra": extra, "dDates": d_dates, "today": today.isoformat(),
                "backupIsins": BACKUP_ISINS, "shortsSymbols": SHORTS_SYMBOLS})
tmp = tempfile.mkdtemp(prefix="twin-")
try:
    def write(pl, catalogue):
        os.makedirs(os.path.join(tmp, "societes"), exist_ok=True)
        with open(os.path.join(tmp, "euro-signal.json"), "w", encoding="utf-8") as fh:
            json.dump(pl, fh)
        with open(os.path.join(tmp, "societes", "0.json"), "w", encoding="utf-8") as fh:
            json.dump({"wDates": w_dates, "dDates": d_dates, "items": catalogue}, fh)
        with open(os.path.join(tmp, "backup-isins.json"), "w", encoding="utf-8") as fh:
            json.dump({"date": today.isoformat(), "isins": BACKUP_ISINS}, fh)
        with open(os.path.join(tmp, "shorts-symbols.json"), "w", encoding="utf-8") as fh:
            json.dump(SHORTS_SYMBOLS, fh)

    write(payload, co)
    rep = tw.run(tmp)
    sel = payload["rank"]["selection"]["items"]
    check(rep["diffs"] == 0, f"classement identique au moteur ({rep['rows']} sociétés)"
          + (f" : {rep['byField']} {rep['examples'][:3]}" if rep["diffs"] else ""))
    check(rep["selection"]["same"] and len(sel) >= 3,
          f"sélection des 5 identique ({', '.join(rep['selection']['engine'])} / {', '.join(rep['selection']['twin'])})")
    check(rep["pick10"]["same"] and len(payload["rank"]["pick10"]) >= 8,
          f"10 🎯 identiques ({', '.join(rep['pick10']['engine'])} / {', '.join(rep['pick10']['twin'])})")
    keys = [x["key"] for x in sel]
    secs = [co[x["sym"]]["sector"] for x in sel]
    check(max(secs.count(s) for s in set(secs)) <= 2, "au plus 2 sociétés par secteur dans la sélection")
    check("SHFR" not in keys and "FR0000000029" not in keys and "WILD" not in keys and "HOT" not in keys,
          "écartées de la sélection : vendue à découvert (Paris), hors PEA, très volatile, plus de +200 %")
    rws = {r["key"]: r for r in payload["rank"]["rows"]}
    check(rws["OKEA"].get("pea") is False and rws["UP2"].get("pea") is False and rws["UP1"].get("pea") is None
          and "OKEA" not in keys and "OKEA" not in payload["rank"]["pick10"],
          "PEA d'après le pays de l'ISIN connu (îles Marshall, Royaume-Uni : hors PEA, jamais proposées)")
    rows = {r["key"]: r for r in payload["rank"]["rows"]}
    check(any(r["out"] and "cours figé" in " ".join(r["out"]) for r in rows.values())
          and any("saut de cours" in " ".join(r["out"]) for r in rows.values())
          and any(r.get("pea") is False for r in rows.values()), "cas limites du classement présents (cours figé, saut, hors PEA)")

    # 3 bis. 💎 : même sélection que ES.pickValue sur des lignes publiées construites (P/B, F-score, PEA, ⚡, 🐻, chutes, secteurs)
    rnd = random.Random(23)
    vrows = []
    for k in range(160):
        vrows.append({
            "key": "V%03d.PA" % k, "isin": None, "sym": "V%03d.PA" % k, "liq": rnd.choice([5e5, 2e6, 8e6, 3e7]),
            "pb": rnd.choice([None, -1.2] + [round(rnd.uniform(0.3, 4), 2)] * 6), "f9": rnd.choice([None, 5, 6, 7, 7, 8, 8, 9]),
            "out": rnd.choice([[]] * 6 + [["dernier exercice en perte (−3 M€)"], ["saut de cours anormal (×3)"], ["tiers le plus faible"]]),
            "pea": rnd.choice([None] * 6 + [False]), "mom": rnd.choice([None, -55.0, -10.0, 12.5, 12.5, 80.0]),
            "dj": rnd.choice([None] * 8 + [42.0]), "vo": rnd.choice([None, 35, 35, 35, 85]),
            "sh": rnd.choice([None] * 6 + [0.7]), "shc": rnd.choice(["FR", "DE"]),
            "secEn": rnd.choice(["Industrials", "Utilities", "Energy", None]), "sector": "Industrie",
        })
    js = subprocess.run(["node", "-e", "const ES=require(process.argv[1]);const r=JSON.parse(require('fs').readFileSync(0,'utf8'));"
                         "process.stdout.write(JSON.stringify(ES.pickValue(r,{n:10,peaOnly:true}).picks.map((x)=>x.key)))",
                         os.path.join(HERE, "core.js")], input=json.dumps(vrows), capture_output=True, text=True, check=True)
    eng_v = json.loads(js.stdout)
    bad = lambda r: any(t in tw.VALUE_BAD or tw.ACC_OUT.search(t) for t in tw.price_out(r["out"]) + r["out"])  # noqa: E731
    twin_v = [r["key"] for r in tw.pick_value([dict(r, bad=bad(r), sec=r["secEn"] or r["sector"]) for r in vrows], pea_only=True)]
    check(eng_v == twin_v and len(eng_v) >= 3, f"10 💎 : mêmes choix que le moteur ({eng_v} / {twin_v})")
    # P/B du soir : relevé ramené au dernier cours, borné, sans relevé ou sans série : tel quel
    dd = ["2026-10-0%d" % k for k in range(1, 6)]
    check(abs(tw.pb_now({"pb": 1.0, "pbAt": "2026-10-02", "d": [10, 10, 11, 12, 15]}, dd) - 1.5) < 1e-9, "P/B ramené au dernier cours")
    check(tw.pb_now({"pb": 1.0, "pbAt": "2026-10-02", "d": [10, 10, 11, 12, 60]}, dd) == 1.0, "rapport aberrant (×6) : P/B relevé gardé")
    check(tw.pb_now({"pb": 2.0, "d": [1, 1, 1, 1, 1]}, dd) == 2.0 and tw.pb_now(None, dd) is None, "sans date de relevé : tel quel")

    # 4. un écart est trouvé
    bad_pl = copy.deepcopy(payload)
    r0 = next(r for r in bad_pl["rank"]["rows"] if r["mom"] is not None and not r["out"])
    r0["mom"] = round(r0["mom"] + 5, 1)
    write(bad_pl, co)
    rep = tw.run(tmp)
    check(rep["byField"].get("mom") == 1 and rep["examples"][0]["field"] == "mom", "hausse fausse du moteur : écart trouvé")
    bad_pl = copy.deepcopy(payload)
    it = bad_pl["rank"]["selection"]["items"]
    it[0], it[1] = it[1], it[0]
    write(bad_pl, co)
    check(not tw.run(tmp)["selection"]["same"], "sélection du moteur dans un autre ordre : écart trouvé")
    bad_pl = copy.deepcopy(payload)
    bad_pl["rank"]["pick10"] = bad_pl["rank"]["pick10"][1:]
    write(bad_pl, co)
    check(not tw.run(tmp)["pick10"]["same"], "10 🎯 différents : écart trouvé")
    bad_co = copy.deepcopy(co)
    s0 = sel[0]["sym"]
    bad_co[s0]["w"][-53] = round(bad_co[s0]["w"][-53] * 0.7, 4)
    write(payload, bad_co)
    rep = tw.run(tmp)
    check(rep["byField"].get("mom") == 1 and rep["examples"][0]["field"] == "mom",
          f"cours différent de ceux du moteur : écart trouvé, la cause en premier ({s0} : {rep['byField']}, {rep['examples'][:2]})")
    bad_co = copy.deepcopy(co)
    bad_co[s0]["w"][-10] = None
    write(payload, bad_co)
    check(tw.run(tmp)["gaps"] == [sel[0]["name"]], "trou dans les cours d'une société de la sélection : signalé")

    # 5. données absentes : rapport en erreur
    os.remove(os.path.join(tmp, "euro-signal.json"))
    code = tw.main(["--data", tmp])
    with open(os.path.join(tmp, "diagnostics", "twin.json"), encoding="utf-8") as fh:
        rep = json.load(fh)
    check(code == 1 and rep.get("error") and "rows" not in rep, "données absentes : rapport en erreur, pas de « tout va bien »")
    write(payload, {})
    code = tw.main(["--data", tmp])
    with open(os.path.join(tmp, "diagnostics", "twin.json"), encoding="utf-8") as fh:
        rep = json.load(fh)
    check(code == 1 and "catalogue" in (rep.get("error") or ""), "catalogue vide : rapport en erreur")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"{ok} réussis, {len(fails)} échoués")
sys.exit(1 if fails else 0)
