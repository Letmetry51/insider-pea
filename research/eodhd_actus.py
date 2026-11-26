"""Profondeur des actualités, du sentiment et des dividendes chez EODHD pour les sociétés de l'outil (26/11/2026, François :
« Est-ce qu'il y aurait d'autres idées? Approche? Méthode? Autre? »). Avant de proposer de tester la lecture de l'actualité par
l'IA et les dividendes sur l'historique, tant que l'abonnement court : combien d'années, pour quelles bourses ?

Échantillon : les 4 sociétés les mieux notées de chaque bourse du classement du soir (data/euro-signal.json), plus 3 sociétés
retirées de la cote (Alcatel-Lucent, Lafarge, Linde AG). Pour chacune : articles par an (« news »), jours avec un score de
sentiment (« sentiments »), dividendes (« div »). Rien n'est écrit (données EODHD gardées en mémoire seulement).
"""
import collections
import json
import time
from pathlib import Path

import survivant_eodhd as SE

DATA = Path(__file__).resolve().parent.parent / 'data'


def news_years(t):
    """Articles par année (pages de 1 000), date la plus ancienne ; (None, erreur) si refusé."""
    years, first, off = collections.Counter(), None, 0
    while off < 20000:
        x, err = SE.get('news', s=t, limit=1000, offset=off, **{'from': '2005-01-01', 'to': '2026-11-26'})
        if err:
            return None, err
        if not isinstance(x, list) or not x:
            break
        for a in x:
            d = str(a.get('date') or '')[:10]
            if len(d) == 10:
                years[d[:4]] += 1
                first = d if first is None or d < first else first
        if len(x) < 1000:
            break
        off += 1000
    return (years, first), None


def main():
    if not SE.KEY:
        print("Pas de clé EODHD")
        return 1
    rows = json.loads((DATA / 'euro-signal.json').read_text(encoding='utf-8'))['rank']['rows']
    by = collections.defaultdict(list)
    for r in sorted(rows, key=lambda r: -(r.get('note') or 0)):
        sym = str(r.get('sym') or '')
        if '.' not in sym:
            continue
        base, suf = sym.rsplit('.', 1)
        ex = {'DE': 'XETRA'}.get(suf, suf)
        if len(by[ex]) < 4:
            by[ex].append((base + '.' + ex, r.get('name') or sym))
    sample = [t for ex in sorted(by) for t in by[ex]] + [('ALU.PA', 'Alcatel-Lucent (retirée)'), ('LG.PA', 'Lafarge (retirée)'),
                                                         ('LIN.XETRA', 'Linde AG (retirée)')]
    t0 = time.time()
    per_ex = collections.defaultdict(list)
    for t, name in sample:
        ex = t.rsplit('.', 1)[1]
        nw, e1 = news_years(t)
        se, e2 = SE.get('sentiments', s=t, **{'from': '2005-01-01', 'to': '2026-11-26'})
        dv, e3 = SE.get('div/' + t, **{'from': '1985-01-01'})
        sl = []
        if isinstance(se, dict):
            for v in se.values():
                if isinstance(v, list):
                    sl += [str(x.get('date') or '')[:10] for x in v if isinstance(x, dict)]
        dd = [str(x.get('date') or '')[:10] for x in dv] if isinstance(dv, list) else []
        if e1:
            na = e1
        elif nw and nw[1]:
            na = f"{sum(nw[0].values())} articles depuis {nw[1]}, " + ', '.join(f"{y} {n}" for y, n in sorted(nw[0].items()) if y >= '2015')
        else:
            na = 'aucune'
        sa = e2 or (f"{len(sl)} jours depuis {min(sl)}" if sl else 'aucun')
        da = e3 or (f"{len(dd)} depuis {min(dd)}" if dd else 'aucun')
        line = f"{t:16s} {name[:28]:28s} | actualités : {na} | sentiment : {sa} | dividendes : {da}"
        print(line)
        per_ex[ex].append((nw[1] if nw and nw[1] else None, min(sl) if sl else None, min(dd) if dd else None,
                           sum(nw[0].values()) if nw else 0))
    print("\nPar bourse (date la plus ancienne médiane ; articles par société) :")
    for ex, v in sorted(per_ex.items()):
        def med(i):
            x = sorted(a[i] for a in v if a[i])
            return x[len(x) // 2] if x else '—'
        print(f"  {ex:6s} actualités depuis {med(0)} ({sum(a[3] for a in v) // max(len(v), 1)} articles en moyenne), "
              f"sentiment depuis {med(1)}, dividendes depuis {med(2)}")
    print(f"\n{SE.calls[0]} appels, {time.time() - t0:.0f} s")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
