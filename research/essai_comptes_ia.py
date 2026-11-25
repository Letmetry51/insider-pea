"""Essai de la lecture des comptes par l'IA (scrapers/comptes_ia.py) avant sa mise en service, 25/11/2026 (François : « Oui avec
haiku ») : 12 sociétés (4 du 🎯, 2 du 💎, Husqvarna, une banque, une foncière, des comptes en dégradation, Francfort, Paris), leurs
trimestres lus en direct chez Yahoo (financials.quarters_of), le texte envoyé pour deux d'entre elles, les lectures de Claude Haiku,
le conseil qui en découle, la durée et le coût. Rien n'est écrit (ni data/, ni out/). Lancé cinq fois le 25/11/2026 avec le secret
ANTHROPIC_API_KEY ajouté pour l'essai à research.yml, puis retiré : à rajouter le temps d'un nouvel essai.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
import comptes_ia as C  # noqa: E402
import financials as F  # noqa: E402
from news_ia import appel, cout, lire  # noqa: E402


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("Pas de secret ANTHROPIC_API_KEY : essai impossible")
        return 1
    fin = json.loads((C.DATA / "financials.json").read_text(encoding="utf-8"))["items"]
    dash = json.loads((C.DATA / "euro-signal.json").read_text(encoding="utf-8"))
    rank = dash["rank"]
    est = json.loads((C.DATA / "sectors" / "estimates.json").read_text(encoding="utf-8"))
    ctx, picks = C.contexte()

    def fk(k):
        return k if k in fin else ("@" + k if "@" + k in fin else None)
    want = list(rank.get("pick10") or [])[:4] + list(rank.get("value10") or [])[:2] + ["SE0001662230", "FR0000131104"]
    for test in (lambda r: r.get("sector") == "Immobilier", lambda r: r.get("acc") == "bad",
                 lambda r: str(r.get("sym", "")).endswith(".DE"), lambda r: str(r.get("sym", "")).endswith(".PA")):
        k = next((r["key"] for r in rank["rows"] if test(r) and r["key"] not in want and fk(r["key"])), None)
        if k:
            want.append(k)
    keys = [k for k in dict.fromkeys(want) if fk(k)]
    items, t0 = {}, time.time()
    for k in keys:
        f = dict(fin[fk(k)])
        try:
            f["quarters"] = F.quarters_of(f["ticker"])
        except Exception as e:  # noqa: BLE001
            print("  %s : trimestres illisibles (%s)" % (k, type(e).__name__))
        items[k] = f
        time.sleep(0.5)
    print("%d sociétés, trimestres lus en %.0f s : %s" % (len(items), time.time() - t0, ", ".join(
        "%s %d" % ((ctx.get(k) or {}).get("symbole") or k, len(v.get("quarters") or [])) for k, v in items.items())))
    todo = {k: C.derniere(v) for k, v in items.items()}
    for k in [k for k in keys if k == "SE0001662230"]:
        print("\n--- Texte envoyé pour %s ---\n%s" % (k, C.bloc(k, items[k], ctx, todo[k][0], todo[k][1], {}, est)))
    cfg = C.config()
    store, usage, t1 = {}, {}, time.time()
    for i in range(0, len(keys), 4):
        lot = keys[i:i + 4]
        texte = "\n\n".join(C.bloc(k, items[k], ctx, todo[k][0], todo[k][1], {}, est) for k in lot)
        t = time.time()
        try:
            res = appel(key, cfg, texte, C.SYSTEME)
        except Exception as e:  # noqa: BLE001
            print("Lot %d : erreur %s" % (i // 4 + 1, str(e)[:40]))
            continue
        for k_, v_ in (res.get("usage") or {}).items():
            if isinstance(v_, (int, float)):
                usage[k_] = usage.get(k_, 0) + v_
        text = "".join(b.get("text", "") for b in res.get("content") or [] if b.get("type") == "text")
        n = C.applique(store, lire(text), {k: (todo[k][0], todo[k][1], None) for k in lot}, time.strftime("%Y-%m-%d"), cfg["modele"])
        u = res.get("usage") or {}
        print("Lot %d : %d lectures sur %d en %.1f s (arrêt : %s ; jetons : entrée %s, cache %s, sortie %s dont réflexion %s)" % (
            i // 4 + 1, n, len(lot), time.time() - t, res.get("stop_reason"), u.get("input_tokens"), u.get("cache_read_input_tokens"),
            u.get("output_tokens"), (u.get("output_tokens_details") or {}).get("thinking_tokens")))
        if not n:
            print("  Réponse : " + text[:600].replace("\n", " "))
    print("\n=== Lectures (%s, %.0f s, environ %.4f $ pour %d sociétés) ===" % (cfg["modele"], time.time() - t1, cout(usage, cfg["modele"]), len(store)))
    for k in keys:
        r, c = store.get(k), ctx.get(k) or {}
        if not r:
            print("\n%s : pas de lecture" % k)
            continue
        print("\n%s (%s, %s) — %s close le %s%s" % (c.get("nom") or k, c.get("symbole"), c.get("secteur"), r["nat"], r["per"],
                                                     " — 🎯/💎" if k in picks else ""))
        print("  Effet possible : %s · avis : %s" % (r["i"], r["a"]))
        print("  " + r["res"])
        for t in r["f"]:
            print("  + " + t)
        for t in r["w"]:
            print("  − " + t)
        if r.get("al"):
            print("  ⚠️ " + r["al"])
        print("  Conseil : " + C.conseil(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
