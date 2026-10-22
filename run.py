"""
Euro Signal — collecte des déclarations de dirigeants publiées par l'AMF (étape 1 du workflow du soir).
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scrapers.france_amf import scrape_all_recent

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# Mapping ISIN -> ticker Yahoo Finance (pour enrichissement optionnel). Euro Signal (scrapers/prices.py) privilégie
# la recherche Yahoo par ISIN et n'utilise cette table qu'en secours (revue du 2026-10-08 : 5 erreurs corrigées).
# Plus on en ajoute, plus on aura d'infos analystes dans le dashboard.
# Pour les ISINs absents, seule la partie "achat d'initié" sera affichée (pas de potentiel analystes).
ISIN_TO_TICKER = {
    # CAC 40
    "FR0000120271": "TTE.PA", "FR0000131104": "BNP.PA", "FR0000120578": "SAN.PA",
    "FR0000121014": "MC.PA", "FR0000121972": "SU.PA", "FR0000120073": "AI.PA",
    "FR0000125338": "CAP.PA", "FR0000051807": "TEP.PA", "FR0000120693": "RI.PA",
    "FR0014003TT8": "DSY.PA", "FR0000120321": "OR.PA", "FR0000052292": "RMS.PA",
    "FR0000121485": "KER.PA", "FR0000045072": "ACA.PA", "FR0000120628": "CS.PA",
    "NL0000235190": "AIR.PA", "FR0000073272": "SAF.PA", "FR001400AJ45": "ML.PA",
    "FR0000125486": "DG.PA", "FR0000133308": "ORA.PA", "FR0010220475": "ALO.PA",
    "FR0000121667": "EL.PA", "FR0000120172": "CA.PA", "FR0000120644": "BN.PA",
    "FR0000130577": "PUB.PA",  # Publicis (était associé à Danone par erreur jusqu'au 23/10/2026)
    # SBF 120 / Mid caps où les insiders achètent souvent
    "FR0013230612": "TKO.PA",       # Tikehau Capital
    "FR0013269123": "RUI.PA",       # Rubis
    "FR0000054470": "UBI.PA",       # Ubisoft
    "FR0010588079": "FREY.PA",      # Frey
    "FR0000031775": "VCT.PA",       # Vicat
    "FR0000066755": "PIG.PA",       # Haulotte
    "FR0013344173": "RBO.PA",       # Roche Bobois
    "FR0000121709": "SK.PA",        # SEB (Groupe SEB)
    "FR0014000MR3": "ERF.PA",       # Eurofins Scientific
    "FR0004040608": "ABCA.PA",      # ABC Arbitrage (ISIN alternatif)
    "FR0011476928": "FNAC.PA",      # Fnac Darty
    "FR0000074148": "ASY.PA",       # Assystem (était associé à Fnac Darty par erreur jusqu'au 23/10/2026)
    "FR0000125007": "SGO.PA",       # Saint-Gobain
    "FR0000130809": "GLE.PA",       # Société Générale
    "FR0000120404": "AC.PA",        # Accor
    "FR0010208488": "ENGI.PA",      # Engie
    "FR0000053225": "MMT.PA",       # M6 Métropole Télévision
    "FR0010040865": "GFC.PA",       # Gecina
    # International
    "BE0974293251": "ABI.BR",       # AB InBev
    "NL0011821202": "INGA.AS",      # ING
    "NL0010273215": "ASML.AS",      # ASML
    "IT0005678104": "ALKLN.PA",     # Kaleon (Euronext Growth Paris)
}


def tx_key(t):
    """Même clé que le dédoublonnage du collecteur : numéro de déclaration, sinon date + dirigeant + montant."""
    return t.get("declaration_number") or (str(t.get("date")) + str(t.get("insider")) + str(t.get("amount")))


def merge_partial(fresh, old, cutoff):
    """Collecte interrompue ou anormalement courte : les déclarations de la veille non relues ce soir (dans la fenêtre) sont
    gardées. Sans cela, le fichier du soir les effacerait, et avec elles les cours des sociétés françaises (scrapers/prices.py
    tire sa liste de ce fichier)."""
    seen = {tx_key(t) for t in fresh}
    kept = [t for t in old if isinstance(t, dict) and tx_key(t) not in seen and str(t.get("date") or "") >= cutoff]
    merged = fresh + kept
    merged.sort(key=lambda t: (str(t.get("date") or ""), str(t.get("date_published") or "")), reverse=True)
    return merged, len(kept)


def main():
    """Collecte AMF des 180 derniers jours -> data/latest.json (lu par Euro Signal, euro_signal/build.mjs).
    L'ancien tableau de bord « Insider PEA V3 » (enrichissement Yahoo et score propres) a été retiré le 2026-10-13 :
    Euro Signal calcule cours, notes et avis lui-même ; la table ISIN_TO_TICKER reste utilisée par scrapers/prices.py."""
    print(f"Collecte AMF — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    days_back = 180  # Euro Signal ne garde que les publications utiles ; l'archive longue est dans data/history
    status = {}
    all_transactions = scrape_all_recent(days_back=days_back, max_pages=300, status=status)  # 300 pages : couvre réellement 180 jours
    collected = len(all_transactions)
    try:
        old = json.loads((DATA_DIR / "latest.json").read_text(encoding="utf-8")).get("transactions") or []
    except Exception:
        old = []
    partial = None
    if not status.get("complete", True):
        partial = "collecte interrompue (" + (status.get("error") or "fin de liste non atteinte") + ")"
    elif len(old) >= 200 and collected < 0.5 * len(old):
        partial = f"collecte anormalement courte : {collected} déclarations contre {len(old)} la veille"
    kept = 0
    if partial and old:
        cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        all_transactions, kept = merge_partial(all_transactions, old, cutoff)
    purchases = [t for t in all_transactions if t.get("is_purchase")]
    sells = [t for t in all_transactions if t.get("is_sell")]
    output = {
        "generated_at": datetime.now().isoformat(),
        "transactions_count": len(purchases),
        "sells_count": len(sells),
        "total_transactions": len(all_transactions),
        "days_covered": days_back,
        "transactions": all_transactions,
    }
    if partial:  # lu par euro_signal/build.mjs : source AMF « partielle » (ou « en échec » si rien n'a été lu ce soir)
        output["partial"] = {"note": partial, "collected": collected, "kept": kept, "pages": status.get("pages", 0)}
    tmp = DATA_DIR / "latest.json.tmp"
    tmp.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    tmp.replace(DATA_DIR / "latest.json")  # écriture atomique : jamais de fichier à moitié écrit
    print(f"Données écrites : {len(all_transactions)} déclarations, {len(purchases)} achats, {len(sells)} ventes")
    if partial:
        print(f"ATTENTION : {partial} ; {collected} déclarations lues ce soir, {kept} gardées de la veille")
    return 1 if partial and not collected else 0  # rien lu ce soir : étape en échec (email de contrôle)


if __name__ == "__main__":
    sys.exit(main())
