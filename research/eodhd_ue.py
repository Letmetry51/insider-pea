"""Bourses de l'Union européenne et de l'EEE (sociétés éligibles au PEA) absentes de l'outil : ce qu'EODHD en a (23/11/2026, François :
« D'autres idées pendant que j'ai l'abonnement ? »). Pour chaque bourse d'un pays de l'UE ou de l'EEE hors des 12 de l'étude : actions
ordinaires cotées et retirées de la cote (ISIN du pays), sociétés avec un cours en juin 2005 et en juin 2015 (cours de toute la bourse
en un appel). N'imprime que des comptes ; rien n'est écrit dans out/ ; la clé n'est jamais affichée.
"""
import survivant_eodhd as SE

log = SE.log
DONE = {'PA', 'XETRA', 'MC', 'AS', 'BR', 'LS', 'VI', 'HE', 'ST', 'CO', 'OL', 'IR', 'F', 'BE', 'STU', 'DU', 'HM', 'HA', 'MU'}
UE = {'Poland': 'PL', 'Greece': 'GR', 'Czech Republic': 'CZ', 'Hungary': 'HU', 'Estonia': 'EE', 'Latvia': 'LV', 'Lithuania': 'LT',
      'Romania': 'RO', 'Croatia': 'HR', 'Slovenia': 'SI', 'Slovakia': 'SK', 'Bulgaria': 'BG', 'Cyprus': 'CY', 'Malta': 'MT',
      'Luxembourg': 'LU', 'Iceland': 'IS', 'Italy': 'IT', 'Portugal': 'PT', 'Ireland': 'IE', 'Denmark': 'DK', 'Liechtenstein': 'LI'}


def main():
    if not SE.KEY:
        log("Secret EODHD_API_KEY absent.")
        return
    x, err = SE.get('exchanges-list')
    if not x:
        log(f"liste des bourses : {err}")
        return
    cand = [e for e in x if isinstance(e, dict) and e.get('Country') in UE and e.get('Code') not in DONE]
    log(f"Bourses de l'UE et de l'EEE hors de l'étude chez EODHD : {', '.join(str(e.get('Code')) + ' (' + str(e.get('Country')) + ')' for e in cand)}")
    for e in cand:
        ex, cc = e['Code'], UE[e['Country']]
        cells = []
        for dl in (0, 1):
            y, err = SE.get(f"exchange-symbol-list/{ex}", **({'delisted': 1} if dl else {}))
            cs = [r for r in (y or []) if isinstance(r, dict) and r.get('Type') == 'Common Stock']
            own = [r for r in cs if str(r.get('Isin') or '')[:2] == cc]
            cells.append(f"{'retirées' if dl else 'cotées'} {len(own)} (toutes : {len(cs) if y else err})")
        hist = []
        for d in ('2005-06-01', '2015-06-01'):
            b, err = SE.get(f"eod-bulk-last-day/{ex}", date=d)
            hist.append(f"{d[:4]} {len(b) if isinstance(b, list) else err}")
        log(f"  {ex:6s} {e.get('Name')} ({e.get('Country')}, {e.get('Currency')}) : actions ordinaires du pays {' · '.join(cells)} ; "
            f"avec un cours en {' · '.join(hist)}")
    u, err = SE.get('user')
    log(f"\n{SE.calls[0]} requêtes" + (f" ; compteur EODHD du jour {u.get('apiRequests')}" if u else ''))


if __name__ == '__main__':
    main()
