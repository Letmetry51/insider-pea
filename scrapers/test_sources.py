"""
Tests hors ligne des pannes muettes des sources (aucun accès réseau) : collecte AMF interrompue ou anormalement courte
(déclarations de la veille gardées), fichier de ventes à découvert lu mais plus mis à jour par le régulateur, liste FSMA
limitée à une page (fenêtres de dates plus anciennes, trou signalé).

  python scrapers/test_sources.py
"""
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scrapers"))
import run as R  # noqa: E402
import shorts as SH  # noqa: E402
import europe_insiders as EU  # noqa: E402
from scrapers import france_amf as AMF  # noqa: E402

results = []


def case(name):
    def deco(fn):
        try:
            fn()
            results.append(("OK  ", name, ""))
        except Exception as e:  # noqa: BLE001
            results.append(("ÉCHEC", name, repr(e)))
        return fn
    return deco


def tx(n, d):
    return {"declaration_number": n, "date": d, "date_published": d, "insider": "X", "amount": 1, "is_purchase": True}


@case("AMF : déclarations de la veille gardées (fenêtre, doublons, ordre)")
def _():
    fresh = [tx("A", "2026-10-20"), tx("B", "2026-10-19")]
    old = [tx("B", "2026-10-19"), tx("C", "2026-09-01"), tx("D", "2026-01-01"), "abîmé"]
    m, kept = R.merge_partial(fresh, old, "2026-04-26")
    assert [t["declaration_number"] for t in m] == ["A", "B", "C"] and kept == 1


class FakeResp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code != 200:
            raise AMF.requests.HTTPError(str(self.status_code))


def run_amf(pages, fail_from=None, old=None):
    """Collecte AMF simulée : `pages` pages de 10 déclarations, panne à partir de la page `fail_from`."""
    calls = {"n": 0}

    def get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        p = params["f_page"]
        if fail_from and p >= fail_from:
            raise AMF.requests.ConnectionError("coupure")
        return FakeResp(f"<p>page {p} </p>" + ("<p>Page suivante</p>" if p < pages else ""))

    def extract(soup):
        p = int(soup.get_text().split()[1])
        return [tx(f"P{p}-{k}", (date(2026, 10, 22) - timedelta(days=p)).isoformat()) for k in range(10)]

    saved = (AMF.requests.get, AMF._extract_transactions_from_soup, AMF.time.sleep, R.DATA_DIR)
    tmp = Path(tempfile.mkdtemp())
    try:
        AMF.requests.get, AMF._extract_transactions_from_soup, AMF.time.sleep = get, extract, lambda s: None
        R.scrape_all_recent = AMF.scrape_all_recent
        R.DATA_DIR = tmp
        if old is not None:
            (tmp / "latest.json").write_text(json.dumps({"transactions": old}), encoding="utf-8")
        code = R.main()
        return code, json.loads((tmp / "latest.json").read_text(encoding="utf-8"))
    finally:
        AMF.requests.get, AMF._extract_transactions_from_soup, AMF.time.sleep, R.DATA_DIR = saved


@case("AMF : collecte complète, aucune mention partielle")
def _():
    st = {}
    code, out = run_amf(3)
    assert code == 0 and "partial" not in out and out["total_transactions"] == 30
    saved = (AMF.requests.get, AMF._extract_transactions_from_soup, AMF.time.sleep)
    try:
        AMF.requests.get = lambda url, params=None, headers=None, timeout=None: FakeResp("x" + ("Page suivante" if params["f_page"] < 2 else ""))
        AMF._extract_transactions_from_soup = lambda soup: [tx("Z", "2026-10-21")]
        AMF.time.sleep = lambda s: None
        AMF.scrape_all_recent(days_back=30, max_pages=5, status=st)
    finally:
        AMF.requests.get, AMF._extract_transactions_from_soup, AMF.time.sleep = saved
    assert st["complete"] is True and st["error"] is None and st["pages"] == 2


@case("AMF : collecte interrompue → déclarations de la veille gardées, source partielle")
def _():
    old = [tx(f"P{p}-{k}", (date(2026, 10, 22) - timedelta(days=p)).isoformat()) for p in range(1, 6) for k in range(10)]
    old = [dict(t, date=(date.today() - timedelta(days=int(t["declaration_number"][1]))).isoformat()) for t in old]
    code, out = run_amf(5, fail_from=3, old=old)
    assert code == 0, code  # pages 1 et 2 lues : étape réussie, source « partielle »
    p = out["partial"]
    assert p["collected"] == 20 and p["kept"] == 30 and "page 3" in p["note"], p
    assert out["total_transactions"] == 50


@case("AMF : site en panne dès la première page → rien d'effacé, étape en échec")
def _():
    old = [tx(f"O{k}", (date.today() - timedelta(days=k)).isoformat()) for k in range(1, 40)]
    code, out = run_amf(5, fail_from=1, old=old)
    assert code == 1 and out["partial"]["collected"] == 0 and out["total_transactions"] == 39


@case("AMF : collecte anormalement courte (moins de la moitié de la veille) → fusion")
def _():
    old = [tx(f"O{k}", (date.today() - timedelta(days=k % 150)).isoformat()) for k in range(400)]
    code, out = run_amf(3, old=old)
    assert code == 0 and "anormalement courte" in out["partial"]["note"] and out["total_transactions"] == 430


@case("Ventes à découvert : fichier lu mais plus mis à jour → « perime » (pas en Allemagne ni au Royaume-Uni)")
def _():
    d = date(2026, 10, 22)
    recs = [{"date": "2026-10-01"}, {"date": "2026-09-20"}, {"date": None}]
    assert SH.freshness("FR", recs, d) == ("2026-10-01", True)
    assert SH.freshness("FR", [{"date": "2026-10-15"}], d) == ("2026-10-15", False)
    assert SH.freshness("BE", [{"date": "2026-10-10"}], d) == ("2026-10-10", False)  # Belgique : écarts de 9 jours observés
    assert SH.freshness("BE", [{"date": "2026-10-01"}], d)[1] is True
    assert SH.freshness("DE", [{"date": "2025-01-01"}], d)[1] is False
    assert SH.freshness("FR", [], d) == (None, False)


class FakeFsma:
    """Liste FSMA simulée : 50 fiches au plus par réponse, les plus récentes d'abord ; pagination sans effet (comme le site)."""

    def __init__(self, fiches, date_filter=True):
        self.fiches, self.date_filter, self.calls = fiches, date_filter, 0

    def get(self, url, params=None):
        self.calls += 1
        lst = sorted(self.fiches.items(), key=lambda kv: kv[1], reverse=True)
        if self.date_filter and params and params.get("date[max]"):
            lo, hi = params["date[min]"], params["date[max]"]
            lst = [kv for kv in lst if lo <= kv[1] <= hi]
        rows = "".join(f'<tr><td><a href="/en/manager-transaction/{u}">x</a></td><td>{"/".join(reversed(d.split("-")))}</td></tr>'
                       for u, d in lst[:EU.FSMA_PAGE])
        return FakeResp("<table>" + rows + "</table>")


def fiches(n, start, per_day=3):
    return {f"f{k}": (start - timedelta(days=k // per_day)).isoformat() for k in range(n)}


@case("FSMA : soir normal → une seule liste, pas de trou")
def _():
    today = date.today()
    site = FakeFsma(fiches(200, today))
    since = today - timedelta(days=EU.WINDOW_DAYS)
    links, tried, _, fmt = EU.fsma_list(site, since)
    calls = site.calls
    oldest, gap = EU.fsma_walk_back(site, since, links, tried, fmt, (today - timedelta(days=4)).isoformat())
    assert fmt == "%Y-%m-%d" and len(links) == 50 and not gap and site.calls == calls


@case("FSMA : après 5 semaines de panne → fenêtres plus anciennes, toutes les fiches listées")
def _():
    today = date.today()
    site = FakeFsma(fiches(200, today))
    since = today - timedelta(days=EU.WINDOW_DAYS)
    links, tried, _, fmt = EU.fsma_list(site, since)
    need = (today - timedelta(days=35)).isoformat()
    oldest, gap = EU.fsma_walk_back(site, since, links, tried, fmt, need)
    assert not gap and oldest <= need and len(links) >= 105, (len(links), oldest, need)


@case("FSMA : filtre de dates inopérant → trou signalé (fiches jamais listées)")
def _():
    today = date.today()
    site = FakeFsma(fiches(200, today), date_filter=False)
    since = today - timedelta(days=EU.WINDOW_DAYS)
    links, tried, _, fmt = EU.fsma_list(site, since)
    oldest, gap = EU.fsma_walk_back(site, since, links, tried, fmt, (today - timedelta(days=35)).isoformat())
    assert gap and len(links) == 50


if __name__ == "__main__":
    for r in results:
        print(*r)
    bad = [r for r in results if r[0] != "OK  "]
    print(f"\n{len(results) - len(bad)}/{len(results)} tests réussis")
    sys.exit(1 if bad else 0)
