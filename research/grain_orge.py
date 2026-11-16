"""Sonde : page des prix physiques de l'orge brassicole chez terre-net (lecture seule)."""
import sys, time
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grain_signal"))
import collect  # noqa: E402

for url in ("https://www.terre-net.fr/marche-agricole/orge-brassicole/physique",
            "https://www.terre-net.fr/marche-agricole/orge-brassicole/physique/",
            "https://www.terre-net.fr/marche-agricole/orge-brassicole",
            "https://www.terre-net.fr/marche-agricole/orge-fourragere/physique"):
    for k in range(3):
        try:
            r = requests.get(url, headers=collect.UA, timeout=30)
            items = collect.parse_place_prices(r.text) if r.status_code == 200 else []
            print(url, r.status_code, len(r.text), "places:", len(items), (items[0] if items else ""))
        except Exception as e:
            print(url, "ERR", e)
        time.sleep(5)
