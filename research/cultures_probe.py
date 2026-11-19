"""Sonde 2 : API publique Céré'Obs (méthodes, paramètres, réponses)."""
import re
import json
import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/124", "Accept": "application/json, text/plain, */*"})
B = "https://cereobs.franceagrimer.fr/cereobs-sp/"
idx = S.get(B, timeout=30).text
main = re.search(r'src="(main-es2015[^"]+\.js)"', idx).group(1)
js = S.get(B + main, timeout=60).text
for nom in ["culturesRetenues", "getPublicationParDerniereSemaine", "getPublicationsCondCulture", "getPublicationsBySemaineObservation",
            "publications/tableau", "dateDernierePublication", "getDebutFinSemaineObservation", "enResume", "rapportExcel"]:
    for m in list(re.finditer(re.escape("api/public/" + nom), js))[:2]:
        print(f"\n=== {nom} ===\n", js[max(0, m.start() - 350): m.end() + 250].replace("\n", " "))


def essai(meth, chemin, **kw):
    try:
        r = S.request(meth, B + chemin, timeout=30, **kw)
        print(f"\n{meth} {chemin} {kw or ''} -> {r.status_code} {r.headers.get('content-type')} {len(r.content)} o")
        t = r.text
        print(t[:1500])
        return r
    except Exception as e:
        print(meth, chemin, "ERREUR", e)


essai("GET", "api/public/culturesRetenues")
essai("GET", "api/public/accueil/dateDernierePublication")
essai("GET", "api/public/publications/getPublicationParDerniereSemaine")
essai("GET", "api/public/publications/getPublicationsCondCulture")
essai("GET", "api/public/semaineobservation/getDebutFinSemaineObservation")
essai("GET", "api/public/publications/enResume")
