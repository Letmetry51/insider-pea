"""Varsovie (et Athènes si elle a assez de sociétés) sans biais du survivant (23/11/2026, François : « D'autres idées pendant que
j'ai l'abonnement ? … Oui »). La Pologne et la Grèce sont dans l'Union européenne : leurs sociétés sont éligibles au PEA, mais
l'outil ne les a jamais vues. Même calcul que survivant_londres.py (toutes les actions ordinaires du pays chez EODHD, cotées ou
retirées de la cote, liquidité en euros connue à la date, mêmes règles, 2001-2026, protection −30 %, frais 0,3 % par sens),
univers A, B et C à 3 M€ par jour et, ces places étant moins liquides, C aussi à 1 M€ ; Athènes : univers C seulement, s'il
compte au moins 80 sociétés investissables en 2010 (à 3 M€, ou à défaut à 1 M€). Les cours restent en mémoire ; la clé n'est
jamais affichée. Lancé par « Recherche (à la demande) » (script survivant_varsovie.py), environ 15 minutes, 1 500 appels EODHD.
"""
import time

import survivant_eodhd as SE
import survivant_londres as L

log = SE.log
MARKETS = (dict(name='Varsovie', ex='WAR', isin=('PL',), cur={'PLN': 1.0}, fx='EURPLN.FOREX',
                bench=('Bourse de Varsovie (WIG, dividendes compris)', ('WIG.INDX', 'WIG20TR.INDX', 'WIG20.INDX')), ysuf='WA', abc=True,
                lq1=True),
           dict(name='Athènes', ex='AT', isin=('GR',), cur={'EUR': 1.0}, fx=None,
                bench=("Bourse d'Athènes (indice général)", ('GD.INDX', 'ATG.INDX', 'FTASE.INDX')), ysuf='AT', abc=False, lq1=True))


def main():
    if not SE.KEY:
        log("Secret EODHD_API_KEY absent : rien à faire.")
        return
    t00 = time.time()
    for m in MARKETS:
        L.run(m)
    u, err = SE.get('user')
    log(f"\nterminé en {time.time() - t00:.0f} s ; {SE.calls[0]} appels" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
