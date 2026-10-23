"""Données piégées pour le contrôle de sécurité de la page (tools/inject_check.mjs) : à chaque texte affichable des fichiers
publiés (noms de sociétés et de dirigeants, titres de presse, descriptions, secteurs, raisons…) s'ajoute un morceau de code HTML
qui s'exécuterait s'il n'était pas neutralisé ; chaque lien externe devient un lien « javascript: ». Les identifiants (ISIN,
symboles, dates, nombres) restent intacts pour que la page fonctionne.

    python tools/poison.py data        (sur une copie des données : les fichiers sont réécrits)
"""
import glob
import json
import os
import re
import sys

ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?([T ][\d:.+Z-]*)?$")
TICK = re.compile(r"^[A-Z0-9^=][A-Z0-9.^=\-]{0,14}$")
NUM = re.compile(r"^[-+]?\d+([.,]\d+)?%?$")
URL_KEYS = {"u", "url", "sourceUrl", "web", "link", "href"}
PAYLOAD = "\"'><img src=x onerror=__xss(1)>"


def poison(o, key=None, n=None):
    if isinstance(o, dict):
        return {k: poison(v, k, n) for k, v in o.items()}
    if isinstance(o, list):
        return [poison(v, key, n) for v in o]
    if isinstance(o, str):
        if key in URL_KEYS and o.startswith("http"):
            n[1] += 1
            return "javascript:__xss(2)"
        if ISIN.match(o) or DATE.match(o) or TICK.match(o) or NUM.match(o) or o.startswith(("http", "data/")):
            return o
        if (" " in o and len(o) >= 4) or (len(o) >= 8 and re.search(r"[a-z]", o) and re.search(r"[A-Z]", o)):
            n[0] += 1
            return o + PAYLOAD
    return o


def main(data):
    files = [os.path.join(data, f) for f in ("euro-signal.json", "sectors.json", "societes-index.json", "news.json",
                                            os.path.join("diagnostics", "quality.json"), os.path.join("diagnostics", "ui-check.json"))]
    files += glob.glob(os.path.join(data, "societes", "*.json")) + glob.glob(os.path.join(data, "fiches", "*.json"))
    try:
        main_json = json.load(open(os.path.join(data, "euro-signal.json"), encoding="utf-8"))
        for k in ("longFile", "detailFile", "insidersFile"):
            f = main_json.get(k) or (main_json.get("history") or {}).get(k)
            if f:
                files.append(os.path.join(os.path.dirname(data.rstrip("/")) or ".", f))
    except Exception:
        pass
    n, done = [0, 0], 0
    for f in dict.fromkeys(files):
        if not os.path.exists(f):
            continue
        try:
            o = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        o2 = poison(o, None, n)
        if isinstance(o, dict) and "format" in o:
            o2["format"] = o["format"]
        json.dump(o2, open(f, "w", encoding="utf-8"), ensure_ascii=False)
        done += 1
    vf = os.path.join(data, "version.json")
    if os.path.exists(vf):
        os.remove(vf)  # empreintes devenues fausses : la page lit les fichiers sans cache
    print(f"Données piégées : {done} fichiers, {n[0]} textes, {n[1]} liens")
    return 0 if done and n[0] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data"))
