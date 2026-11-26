"""Suivre l'argent « averti » américain en pratique : fonds cotés qui copient les gourous (26/11/2026, même demande que
us_secteurs.py). Rendement total (dividendes compris, Yahoo) depuis la création de chaque fonds, face au S&P 500 (SPY) :
GURU (Global X Guru : meilleures idées des hedge funds d'après leurs déclarations 13F, depuis juin 2012) ; NANC et KRUZ (achats
déclarés par les élus démocrates et républicains du Congrès, depuis février 2023). Rien n'est écrit.
"""
import yfinance as yf


def main():
    tick = ['GURU', 'NANC', 'KRUZ', 'SPY']
    px = yf.download(tick, start='2012-01-01', auto_adjust=True, progress=False)['Close']
    for t in ('GURU', 'NANC', 'KRUZ'):
        s = px[t].dropna()
        if s.empty:
            print(f"{t} : pas de cours")
            continue
        a, b = s.index[0], s.index[-1]
        spy = px['SPY'].loc[a:b].dropna()
        yrs = (b - a).days / 365.25
        r, m = s.iloc[-1] / s.iloc[0], spy.iloc[-1] / spy.iloc[0]
        print(f"{t} du {a.date()} au {b.date()} ({yrs:.1f} ans) : {(r - 1) * 100:+.0f} % ({(r ** (1 / yrs) - 1) * 100:+.1f} %/an) ; "
              f"S&P 500 {(m - 1) * 100:+.0f} % ({(m ** (1 / yrs) - 1) * 100:+.1f} %/an) ; écart {((r / m) ** (1 / yrs) - 1) * 100:+.1f} point(s) par an")
        for y0 in (2016, 2021):  # 10 et 5 dernières années pleines
            s2, m2 = s.loc[f'{y0}-11-01':], px['SPY'].loc[f'{y0}-11-01':].dropna()
            if len(s2) > 200 and t == 'GURU':
                n = (s2.index[-1] - s2.index[0]).days / 365.25
                g, k = s2.iloc[-1] / s2.iloc[0], m2.iloc[-1] / m2.iloc[0]
                print(f"   depuis le {s2.index[0].date()} : {(g ** (1 / n) - 1) * 100:+.1f} %/an contre {(k ** (1 / n) - 1) * 100:+.1f} %/an")


if __name__ == '__main__':
    main()
