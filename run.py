"""
Orchestrateur principal - Insider PEA
Exécute tous les scrapers, fusionne les données, enrichit avec Yahoo Finance,
calcule les scores, écrit un JSON consolidé.

Usage: python run.py
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Assurer que les scrapers sont trouvables
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.france_amf import scrape_france
from scrapers.yahoo_finance import enrich_with_yahoo
from scrapers.scoring import compute_insider_score, compute_tech_guard, compute_verdict

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# Liste ISIN cibles (actions PEA principales).
# Étendre cette liste pour suivre plus d'entreprises.
TARGETS = [
    # France - FR tickers sur Yahoo Finance = .PA
    {"isin": "FR0000120271", "name": "TotalEnergies", "ticker": "TTE.PA", "country": "FR", "sector": "Énergie"},
    {"isin": "FR0000131104", "name": "BNP Paribas", "ticker": "BNP.PA", "country": "FR", "sector": "Finance"},
    {"isin": "FR0000120578", "name": "Sanofi", "ticker": "SAN.PA", "country": "FR", "sector": "Santé"},
    {"isin": "FR0000121014", "name": "LVMH", "ticker": "MC.PA", "country": "FR", "sector": "Luxe"},
    {"isin": "FR0000121972", "name": "Schneider Electric", "ticker": "SU.PA", "country": "FR", "sector": "Industrie"},
    {"isin": "FR0000120073", "name": "Air Liquide", "ticker": "AI.PA", "country": "FR", "sector": "Industrie"},
    {"isin": "FR0000125338", "name": "Capgemini", "ticker": "CAP.PA", "country": "FR", "sector": "Technologie"},
    {"isin": "FR0000051807", "name": "Teleperformance", "ticker": "TEP.PA", "country": "FR", "sector": "Technologie"},
    {"isin": "FR0000120693", "name": "Pernod Ricard", "ticker": "RI.PA", "country": "FR", "sector": "Alimentation"},
    {"isin": "FR0014003TT8", "name": "Dassault Systèmes", "ticker": "DSY.PA", "country": "FR", "sector": "Technologie"},
    {"isin": "FR0000120321", "name": "L'Oréal", "ticker": "OR.PA", "country": "FR", "sector": "Luxe"},
    {"isin": "FR0000052292", "name": "Hermès", "ticker": "RMS.PA", "country": "FR", "sector": "Luxe"},
    {"isin": "FR0000121485", "name": "Kering", "ticker": "KER.PA", "country": "FR", "sector": "Luxe"},
    {"isin": "FR0000045072", "name": "Crédit Agricole", "ticker": "ACA.PA", "country": "FR", "sector": "Finance"},
    {"isin": "FR0000120628", "name": "AXA", "ticker": "CS.PA", "country": "FR", "sector": "Finance"},
    {"isin": "NL0000235190", "name": "Airbus", "ticker": "AIR.PA", "country": "FR", "sector": "Industrie"},
    {"isin": "FR0000073272", "name": "Safran", "ticker": "SAF.PA", "country": "FR", "sector": "Industrie"},
    {"isin": "FR001400AJ45", "name": "Michelin", "ticker": "ML.PA", "country": "FR", "sector": "Automobile"},
    {"isin": "FR0000125486", "name": "Vinci", "ticker": "DG.PA", "country": "FR", "sector": "Industrie"},
    {"isin": "FR0000133308", "name": "Orange", "ticker": "ORA.PA", "country": "FR", "sector": "Télécoms"},
    {"isin": "FR0010220475", "name": "Publicis", "ticker": "PUB.PA", "country": "FR", "sector": "Technologie"},
    {"isin": "NL0000235190", "name": "STMicroelectronics", "ticker": "STMPA.PA", "country": "FR", "sector": "Technologie"},
    {"isin": "FR0000121667", "name": "EssilorLuxottica", "ticker": "EL.PA", "country": "FR", "sector": "Santé"},
    {"isin": "FR0000120172", "name": "Carrefour", "ticker": "CA.PA", "country": "FR", "sector": "Alimentation"},
    {"isin": "FR0000130577", "name": "Danone", "ticker": "BN.PA", "country": "FR", "sector": "Alimentation"},
]

def main():
    print("=" * 60)
    print(f"INSIDER PEA - Mise à jour {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Fenêtre temporelle pour les achats d'initiés
    days_back = 120
    cutoff = datetime.now() - timedelta(days=days_back)

    # 1. Scraping France AMF via lestransactions.fr
    print(f"\n[1/3] Scraping France AMF (fenêtre: {days_back} jours)...")
    all_insider_tx = []
    fr_targets = [t for t in TARGETS if t["country"] == "FR"]
    
    for i, target in enumerate(fr_targets, 1):
        print(f"  [{i}/{len(fr_targets)}] {target['name']}... ", end="", flush=True)
        try:
            txs = scrape_france(target["isin"], cutoff)
            # Enrichir avec les infos de la cible
            for tx in txs:
                tx["ticker"] = target["ticker"]
                tx["country"] = target["country"]
                tx["sector"] = target["sector"]
                tx["company_name"] = target["name"]
            all_insider_tx.extend(txs)
            print(f"{len(txs)} tx")
        except Exception as e:
            print(f"ERREUR: {e}")

    print(f"\nTotal transactions collectées: {len(all_insider_tx)}")

    # Filtrer achats uniquement (nature = Acquisition) et montant > 10000€
    purchases = [
        tx for tx in all_insider_tx
        if tx.get("is_purchase") and tx.get("amount", 0) >= 10000
    ]
    print(f"Achats significatifs (>10k€): {len(purchases)}")

    # 2. Enrichissement Yahoo Finance
    print("\n[2/3] Enrichissement Yahoo Finance...")
    company_data = {}
    for target in TARGETS:
        key = target["isin"]
        try:
            quote = enrich_with_yahoo(target["ticker"])
            if quote:
                company_data[key] = {**target, "quote": quote}
                print(f"  ✓ {target['name']}: {quote.get('currentPrice', 'N/A')}")
            else:
                company_data[key] = {**target, "quote": None}
                print(f"  ✗ {target['name']}: échec")
        except Exception as e:
            company_data[key] = {**target, "quote": None}
            print(f"  ✗ {target['name']}: {e}")

    # 3. Calcul des scores et agrégation par entreprise
    print("\n[3/3] Calcul des scores...")
    
    # Grouper les achats par ISIN
    purchases_by_isin = {}
    for tx in purchases:
        isin = tx["isin"]
        if isin not in purchases_by_isin:
            purchases_by_isin[isin] = []
        purchases_by_isin[isin].append(tx)

    recommendations = []
    for isin, txs in purchases_by_isin.items():
        if isin not in company_data:
            # Cette ISIN n'est pas dans nos cibles, on l'ajoute quand même
            # avec les infos disponibles dans la première transaction
            first_tx = txs[0]
            company_data[isin] = {
                "isin": isin,
                "name": first_tx.get("company_name", "Inconnue"),
                "ticker": None,
                "country": first_tx.get("country", "FR"),
                "sector": first_tx.get("sector", "Autre"),
                "quote": None,
            }

        co = company_data[isin]
        ins_score = compute_insider_score(txs)
        tech = compute_tech_guard(co.get("quote"))
        total = max(ins_score, ins_score + tech["adj"])
        verdict = compute_verdict(total)

        unique_insiders = len(set(tx["insider"] for tx in txs))
        total_amount = sum(tx["amount"] for tx in txs)
        last_buy = max(tx["date"] for tx in txs)
        top_tx = max(txs, key=lambda t: t["amount"])

        recommendations.append({
            "isin": isin,
            "name": co["name"],
            "ticker": co.get("ticker"),
            "country": co["country"],
            "sector": co["sector"],
            "insider_score": ins_score,
            "tech_adj": tech["adj"],
            "tech_detail": tech,
            "total_score": total,
            "verdict": verdict,
            "tx_count": len(txs),
            "total_amount": total_amount,
            "unique_insiders": unique_insiders,
            "last_buy": last_buy,
            "top_insider": top_tx["insider"],
            "top_role": top_tx.get("role", ""),
            "quote": co.get("quote"),
        })

    # Trier par score décroissant
    recommendations.sort(key=lambda r: r["total_score"], reverse=True)

    # 4. Écriture du JSON final
    output = {
        "generated_at": datetime.now().isoformat(),
        "transactions_count": len(purchases),
        "companies_tracked": len(TARGETS),
        "recommendations": recommendations,
        "transactions": sorted(purchases, key=lambda t: t["date"], reverse=True),
        "company_data": company_data,
    }

    output_path = DATA_DIR / "latest.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    print(f"\n✅ Données écrites dans {output_path}")
    print(f"   Recommandations: {len(recommendations)}")
    print(f"   Transactions: {len(purchases)}")

    # Stats rapides
    strong = [r for r in recommendations if r["total_score"] >= 85]
    buys = [r for r in recommendations if 65 <= r["total_score"] < 85]
    print(f"   🟢 Achat Fort: {len(strong)}")
    print(f"   🟡 Achat: {len(buys)}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
