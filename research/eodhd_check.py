"""
Vérification gratuite (clé EODHD gratuite, secret GitHub EODHD_API_KEY) : combien de sociétés européennes retirées de la cote
EODHD connaît-il, bourse par bourse ? Sert à décider si un mois payant (« Historian ») vaut la peine pour un test sans biais
du survivant. La clé n'est jamais affichée ni écrite. 13 appels environ (la formule gratuite en autorise 20 par jour).
"""
import json, os, sys
from collections import Counter
from pathlib import Path
import requests

KEY = os.environ.get("EODHD_API_KEY", "").strip()
OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(parents=True, exist_ok=True)
EX = {"PA": "Paris", "XETRA": "Francfort (Xetra)", "MI": "Milan", "MC": "Madrid", "AS": "Amsterdam", "BR": "Bruxelles", "LS": "Lisbonne",
      "VI": "Vienne", "HE": "Helsinki", "ST": "Stockholm", "CO": "Copenhague", "OL": "Oslo", "LSE": "Londres", "SW": "Suisse"}
lines = []
def log(s): print(s, flush=True); lines.append(s)
if not KEY:
    log("Secret EODHD_API_KEY absent : rien à vérifier."); (OUT / "eodhd.txt").write_text("\n".join(lines)); sys.exit(0)
tot = 0; sample = None
for code, name in EX.items():
    try:
        r = requests.get("https://eodhd.com/api/exchange-symbol-list/%s" % code, params={"api_token": KEY, "fmt": "json", "delisted": 1}, timeout=60)
        if r.status_code != 200:
            log("%-20s refusé (HTTP %d) : %s" % (name, r.status_code, r.text[:80].replace(KEY, "***"))); continue
        rows = r.json()
        stocks = [x for x in rows if str(x.get("Type", "")).lower() in ("common stock", "preferred stock")]
        tot += len(stocks)
        log("%-20s %5d sociétés retirées de la cote (%d lignes en tout)" % (name, len(stocks), len(rows)))
        if code == "PA" and stocks: sample = stocks[0].get("Code") + ".PA"
    except Exception as e:
        log("%-20s erreur %s" % (name, type(e).__name__))
log("TOTAL : %d sociétés européennes retirées de la cote connues d'EODHD" % tot)
if sample:
    try:
        r = requests.get("https://eodhd.com/api/eod/%s" % sample, params={"api_token": KEY, "fmt": "json", "from": "1998-01-01", "period": "w"}, timeout=60)
        d = r.json() if r.status_code == 200 else []
        log("Essai d'historique (%s) : %s" % (sample, ("%d semaines, du %s au %s" % (len(d), d[0]["date"], d[-1]["date"])) if isinstance(d, list) and d else "refusé ou vide (HTTP %d) — historique réservé à la formule payante ?" % r.status_code))
    except Exception as e:
        log("Essai d'historique : erreur %s" % type(e).__name__)
(OUT / "eodhd.txt").write_text("\n".join(lines) + "\n")
