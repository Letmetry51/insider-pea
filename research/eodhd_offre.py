"""Ce que la formule EODHD de François ouvre vraiment (22/11/2026, question : « Comment exploiter davantage les données disponibles avec
l'abonnement ? »). Un appel par service, environ 700 appels : comptes et résultats (aussi d'une société disparue), dividendes,
calendrier des résultats, cours de toute une bourse en un appel, cours dans la journée, indicateurs, actualités, initiés, jours
fériés, indices et taux, profondeur de l'historique avant 1998 (Paris, Francfort), Londres et Suisse. N'imprime que des comptes,
des dates et des noms de rubriques, jamais de cours ni la clé (en cas d'erreur, seul le code HTTP). Rien n'est écrit dans out/.
"""
import collections
import datetime as dt
import os
import sys

import requests

KEY = os.environ.get("EODHD_API_KEY", "").strip()
calls = [0]


def log(*a):
    print(*a, flush=True)


def get(path, **params):
    calls[0] += 1
    try:
        r = requests.get("https://eodhd.com/api/" + path, params={"api_token": KEY, "fmt": "json", **params}, timeout=120)
    except Exception as e:
        return None, type(e).__name__
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        return r.json(), None
    except Exception as e:
        return None, type(e).__name__


def first_last(rows, key='date'):
    d = sorted(str(r.get(key))[:10] for r in rows if isinstance(r, dict) and r.get(key))
    return (d[0], d[-1]) if d else ('·', '·')


def show(lab, x, err, extra=''):
    if err:
        log(f"  {lab:44s} non ({err})")
    else:
        log(f"  {lab:44s} oui{(' : ' + extra) if extra else ''}")


def main():
    if not KEY:
        log("Secret EODHD_API_KEY absent.")
        sys.exit(0)
    u, err = get("user")
    if u:  # seulement la formule et les quotas : jamais le nom, l'adresse ni le moyen de paiement (journal public)
        log(f"Formule « {u.get('subscriptionType')} », {u.get('dailyRateLimit')} appels par jour, {u.get('apiRequests')} déjà utilisés aujourd'hui")
    log("\nServices (Air Liquide, AI.PA, sauf mention) :")
    f, err = get("fundamentals/AI.PA")
    ex = ''
    if isinstance(f, dict):
        fin = f.get('Financials') or {}
        bs = (fin.get('Balance_Sheet') or {})
        yr, qt = bs.get('yearly') or {}, bs.get('quarterly') or {}
        eh = ((f.get('Earnings') or {}).get('History') or {})
        ex = (f"rubriques {', '.join(sorted(f))} ; bilans annuels {len(yr)} (depuis {min(yr) if yr else '·'}), trimestriels {len(qt)} "
              f"(depuis {min(qt) if qt else '·'}) ; résultats publiés {len(eh)} (depuis {min(eh) if eh else '·'}), avec estimation "
              f"{sum(1 for v in eh.values() if isinstance(v, dict) and v.get('epsEstimate') is not None)}")
    show("comptes et résultats", f, err, ex)
    # une société disparue de Paris : ses comptes sont-ils gardés ?
    L, err = get("exchange-symbol-list/PA", delisted=1)
    gone = [r for r in (L or []) if r.get('Type') == 'Common Stock' and r.get('Isin')][:40]
    ok_gone, tried = 0, 0
    for r in gone[::8][:4]:
        tried += 1
        g, e = get(f"fundamentals/{r['Code']}.PA")
        if isinstance(g, dict) and ((g.get('Financials') or {}).get('Balance_Sheet') or {}).get('yearly'):
            ok_gone += 1
    log(f"  {'comptes des sociétés disparues':44s} {ok_gone} sur {tried} essayées avec des bilans")
    x, err = get("div/AI.PA", **{'from': '1990-01-01'})
    show("dividendes", x, err, f"{len(x)} versements, de {first_last(x)[0]} à {first_last(x)[1]}" if isinstance(x, list) else '')
    x, err = get("calendar/earnings", symbols="AI.PA", **{'from': '1995-01-01', 'to': '2026-12-31'})
    E = (x or {}).get('earnings') if isinstance(x, dict) else None
    show("calendrier des résultats (une société)", x, err, f"{len(E)} publications, de {first_last(E, 'report_date')[0]} à "
         f"{first_last(E, 'report_date')[1]}, dont {sum(1 for e in E if e.get('estimate') is not None)} avec estimation" if E else '')
    x, err = get("calendar/earnings", **{'from': '2026-11-02', 'to': '2026-11-20'})
    E = (x or {}).get('earnings') if isinstance(x, dict) else None
    if E:
        c = collections.Counter(str(e.get('code', '')).rsplit('.', 1)[-1] for e in E)
        log(f"  {'calendrier des résultats (toutes, 3 semaines)':44s} {len(E)} publications ; Paris {c.get('PA', 0)}, Francfort "
            f"{c.get('XETRA', 0)}, Madrid {c.get('MC', 0)}, Amsterdam {c.get('AS', 0)}, Stockholm {c.get('ST', 0)}")
    x, err = get("eod-bulk-last-day/PA", date="2026-11-20")
    show("cours de toute une bourse en un appel", x, err, f"{len(x)} lignes pour Paris le 20/11/2026" if isinstance(x, list) else '')
    ts = lambda d: str(int(dt.datetime(*d, tzinfo=dt.timezone.utc).timestamp()))  # noqa: E731
    for iv in ('1h', '5m'):
        x, err = get("intraday/AI.PA", interval=iv, **{'from': ts((2026, 11, 9)), 'to': ts((2026, 11, 21))})
        show(f"cours dans la journée ({iv})", x, err, f"{len(x)} barres sur 2 semaines" if isinstance(x, list) else '')
    x, err = get("intraday/AI.PA", interval='1h', **{'from': ts((2005, 1, 3)), 'to': ts((2005, 1, 15))})
    show("cours dans la journée (1h) en janvier 2005", x, err, f"{len(x)} barres" if isinstance(x, list) else '')
    x, err = get("technical/AI.PA", function="sma", period=50, **{'from': '2026-10-01'})
    show("indicateurs techniques", x, err)
    x, err = get("news", s="AI.PA", limit=10)
    show("actualités", x, err, f"{len(x)} articles, de {first_last(x)[0]} à {first_last(x)[1]}" if isinstance(x, list) else '')
    x, err = get("sentiments", s="AI.PA", **{'from': '2026-10-01'})
    show("sentiment des actualités", x, err)
    x, err = get("insider-transactions", code="AI.PA", limit=10)
    show("transactions d'initiés", x, err, f"{len(x)} lignes" if isinstance(x, list) else '')
    x, err = get("historical-market-cap/AI.PA", **{'from': '2000-01-01'})
    show("capitalisation historique", x, err, f"{len(x)} points" if isinstance(x, (list, dict)) else '')
    x, err = get("exchange-details/PA", **{'from': '2026-01-01', 'to': '2026-12-31'})
    show("horaires et jours fériés (Paris)", x, err, f"{len((x or {}).get('ExchangeHolidays') or {})} jours fériés en 2026" if isinstance(x, dict) else '')
    for code in ('FCHI.INDX', 'GDAXI.INDX', 'STOXX50E.INDX', 'SXXP.INDX', 'STOXX.INDX', 'FR10Y.GBOND', 'DE10Y.GBOND'):
        x, err = get(f"eod/{code}", period='m', **{'from': '1970-01-01'})
        show(f"série {code}", x, err, f"de {first_last(x)[0][:7]} à {first_last(x)[1][:7]}" if isinstance(x, list) and x else '')
    log("\nProfondeur de l'historique (sociétés cotées ce jour-là, cours de toute la bourse en un appel) :")
    for exch in ('PA', 'XETRA', 'AS', 'MC'):
        cells = []
        for d in ('1990-06-01', '1993-06-01', '1995-06-01', '1997-06-02', '2000-06-01'):
            x, err = get(f"eod-bulk-last-day/{exch}", date=d)
            cells.append(f"{d[:4]} {len(x) if isinstance(x, list) else err}")
        log(f"  {exch:6s} " + ' · '.join(cells))
    log("\nLondres et Suisse (actions ordinaires) :")
    for exch in ('LSE', 'SW'):
        cells = []
        for dl in (0, 1):
            x, err = get(f"exchange-symbol-list/{exch}", **({"delisted": 1} if dl else {}))
            cs = [r for r in (x or []) if isinstance(r, dict) and r.get('Type') == 'Common Stock']
            cells.append(f"{'retirées' if dl else 'cotées'} {len(cs) if x else err}")
        x, err = get(f"eod-bulk-last-day/{exch}", date="2000-06-01")
        log(f"  {exch:4s} {' · '.join(cells)} ; cotées le 01/06/2000 : {len(x) if isinstance(x, list) else err}")
    u, err = get("user")
    log(f"\n{calls[0]} requêtes" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
