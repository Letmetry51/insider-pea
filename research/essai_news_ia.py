"""Essai de la lecture des titres par l'IA (scrapers/news_ia.py) sur l'actualité publiée, sans rien écrire (25/11/2026) : Husqvarna
et une vingtaine d'autres sociétés ; imprime chaque titre avec sa lecture. Le secret ANTHROPIC_API_KEY n'est passé qu'à cet essai."""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
import news_ia as NI  # noqa: E402


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("pas de clé")
        return
    data = json.loads(NI.OUT.read_text(encoding="utf-8"))
    items = data.get("items") or {}
    ctx = NI.contexte()
    keys = ["SE0001662230"] + [k for k in items if k != "SE0001662230"][:24]
    sub = {k: items[k] for k in keys if k in items}
    cfg = NI.config()
    t0, usage = time.time(), {}
    for lot in NI.lots(sub, ctx, int(cfg["lot"])):
        res = NI.appel(key, cfg, NI.message(lot, sub, ctx))
        for k_, v_ in (res.get("usage") or {}).items():
            if isinstance(v_, (int, float)):
                usage[k_] = usage.get(k_, 0) + v_
        text = "".join(b.get("text", "") for b in res.get("content") or [] if b.get("type") == "text")
        NI.applique(sub, NI.lire(text))
    for k, lst in sub.items():
        print("\n" + (ctx.get(k) or {}).get("nom", k))
        for g in NI.ordre(lst):
            lab = "non lu" if g.get("v") != NI.VERSION else ("SANS RAPPORT" if not g.get("p") else {"up": "↑ HAUSSE", "down": "↓ BAISSE"}.get(g.get("i"), "→ neutre"))
            print(f"  {lab:12s} {g['t'][:110]}  —  {g.get('r', '')}  [mots-clés : {g.get('k') or '·'}]")
    print(f"\n{sum(len(v) for v in sub.values())} titres, {time.time() - t0:.0f} s, environ {NI.cout(usage, cfg['modele']):.4f} $ ({cfg['modele']})")


if __name__ == "__main__":
    main()
