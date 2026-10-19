import yfinance as yf, time, collections
from yfinance import EquityQuery as Q
from yfinance.const import EQUITY_SCREENER_EQ_MAP as M
print('places suisses connues :', M.get('exchange', {}).get('ch'), '| britanniques :', M.get('exchange', {}).get('gb'))
for name, q in (("ch région seule", Q("and", [Q("eq", ["region", "ch"]), Q("gt", ["intradaymarketcap", 1e6])])),):
    off, total, rows = 0, None, []
    while total is None or off < total:
        try: r = yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False)
        except Exception as e: print(name, 'erreur', str(e)[:120]); break
        qs = r.get("quotes") or []; total = r.get("total") or len(qs); rows += qs; off += 250
        if not qs: break
        time.sleep(0.4)
    print(name, 'total', total, 'reçues', len(rows), collections.Counter(x.get('exchange') for x in rows))
    sw = [x for x in rows if x.get('currency') == 'CHF']
    print(' CHF', len(sw), [x.get('symbol') + ' ' + (x.get('shortName') or '')[:18] for x in sw[:40]])
