"""Yahoo donne-t-il les comptes trimestriels ou semestriels des sociétés européennes ? (25/11/2026, François : « Est-ce possible
d'ajouter la lecture des comptes publiés pour chaque entreprise à chaque publication et donner un conseil »). Échantillon de 8
sociétés par bourse parmi les mieux classées (data/euro-signal.json) : nombre de périodes infra-annuelles du compte de résultat, du
bilan et des flux de trésorerie, date de la dernière, écart moyen entre périodes (trimestre ou semestre). Rien n'est écrit dans out/.
"""
import collections
import json
import time

import yfinance as yf


def main():
    rows = json.load(open('../data/euro-signal.json', encoding='utf-8'))['rank']['rows']
    by = collections.defaultdict(list)
    for r in rows:
        s = str(r.get('sym') or '')
        if '.' in s and s.rsplit('.', 1)[1] in ('PA', 'DE', 'MC', 'AS', 'BR', 'LS', 'VI', 'HE', 'ST', 'CO', 'OL', 'IR', 'MI'):
            by[s.rsplit('.', 1)[1]].append(s)
    sample = [s for ex in sorted(by) for s in by[ex][:8]]
    print(f"{len(sample)} sociétés : " + ', '.join(f"{ex} {min(8, len(v))}" for ex, v in sorted(by.items())))
    stat = collections.defaultdict(lambda: collections.Counter())
    t0 = time.time()
    for s in sample:
        ex = s.rsplit('.', 1)[1]
        try:
            t = yf.Ticker(s)
            qi = t.quarterly_income_stmt
            qb = t.quarterly_balance_sheet
            qc = t.quarterly_cashflow
        except Exception as e:  # noqa: BLE001
            print(f"  {s} : {type(e).__name__}")
            continue
        cols = sorted(qi.columns) if qi is not None and not qi.empty else []
        gap = (sum((b - a).days for a, b in zip(cols, cols[1:])) / (len(cols) - 1)) if len(cols) > 1 else None
        kind = 'aucune' if not cols else ('trimestres' if gap and gap < 120 else 'semestres' if gap and gap < 220 else 'autre')
        stat[ex][kind] += 1
        rev = 'Total Revenue' in qi.index if qi is not None and not qi.empty else False
        print(f"  {s:12s} résultat {len(cols)} périodes ({kind}, dernière {str(cols[-1])[:10] if cols else '·'}, chiffre d'affaires {rev}) ; "
              f"bilan {0 if qb is None or qb.empty else qb.shape[1]} ; trésorerie {0 if qc is None or qc.empty else qc.shape[1]}")
        time.sleep(0.5)
    print("\nPar bourse : " + ' ; '.join(f"{ex} " + ', '.join(f"{k} {v}" for k, v in c.items()) for ex, c in sorted(stat.items())))
    tot = collections.Counter()
    for c in stat.values():
        tot.update(c)
    print(f"En tout : {dict(tot)} ; {time.time() - t0:.0f} s")


if __name__ == '__main__':
    main()
