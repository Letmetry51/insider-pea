"""Compteur d'appels EODHD du jour (27/11/2026) : à quelle date et à quelle heure il repart à zéro, avant de relancer
survivant_comptes2.py (environ 27 000 appels, limite 100 000 par jour). N'affiche que le type de formule, le nombre d'appels, la date
du compteur et les limites : jamais le nom, l'adresse ni le moyen de paiement du compte.
"""
import time

import survivant_eodhd as SE


def main():
    u, err = SE.get('user')
    if not u:
        print("Compte : " + str(err))
        return 1
    keep = ('subscriptionType', 'apiRequests', 'apiRequestsDate', 'dailyRateLimit', 'extraLimit')
    print(time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()) + " : " + ", ".join(f"{k} {u.get(k)}" for k in keep if k in u))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
