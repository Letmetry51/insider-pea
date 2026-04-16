"""
Scraper France - AMF via LesTransactions.fr
API gratuite et documentée : https://lestransactions.fr/api
Requête: POST avec paramètre isin=XXXXXXXXXXXX
Retour: JSON {"0": {...}, "1": {...}, ...}
"""
import requests
from datetime import datetime

API_URL = "https://lestransactions.fr/api"

# Transactions qui sont des ACHATS réels (signal positif)
PURCHASE_NATURES = {
    "Acquisition",
    "Acquisition à titre onéreux",
    "Souscription",
    "Achat",
}

# À ignorer : exercice de stock-options (pas un achat volontaire)
EXCLUDE_NATURES = {
    "Exercice",
    "Cession",
    "Cession à titre gratuit",
    "Attribution",
    "Attribution à titre gratuit",
}


def scrape_france(isin: str, cutoff_date: datetime) -> list[dict]:
    """
    Récupère les transactions d'un ISIN depuis lestransactions.fr.
    
    Args:
        isin: Code ISIN de la société (ex: FR0000120271)
        cutoff_date: Ne garder que les transactions après cette date
    
    Returns:
        Liste de dicts avec les transactions normalisées
    """
    try:
        response = requests.post(
            API_URL,
            data={"isin": isin},
            timeout=30,
            headers={"User-Agent": "insider-pea-personal/1.0"},
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"Erreur réseau pour {isin}: {e}")
        return []
    except ValueError as e:
        print(f"Erreur JSON pour {isin}: {e}")
        return []

    if not isinstance(data, dict):
        return []

    transactions = []
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    for key, raw in data.items():
        # La clé est "0", "1", etc.
        if not isinstance(raw, dict):
            continue

        # Filtrer par date
        tx_date = raw.get("date_transac", "")
        if tx_date < cutoff_str:
            continue

        nature = raw.get("nature", "")
        is_purchase = nature in PURCHASE_NATURES
        
        # On garde aussi les cessions pour le contexte, mais elles ne compteront
        # pas dans le score
        if nature in EXCLUDE_NATURES and not is_purchase:
            # Skip les exercices d'options qui ne sont pas de vrais achats
            if "Exercice" in nature or "Attribution" in nature:
                continue

        # Parser le gérant - format : "PRÉNOM NOM, Fonction"
        manager_raw = raw.get("manager", "")
        if "," in manager_raw:
            insider_name, role = manager_raw.split(",", 1)
            insider_name = insider_name.strip().title()
            role = role.strip()
        else:
            insider_name = manager_raw.strip().title()
            role = "N/D"

        price = float(raw.get("price") or 0)
        qty = float(raw.get("qty") or 0)
        total = float(raw.get("total") or (price * qty))

        # Ignorer les transactions vides ou bizarres
        if total < 1:
            continue

        transactions.append({
            "source": "AMF/lestransactions.fr",
            "isin": isin,
            "date": tx_date,
            "company_name": raw.get("company", ""),
            "insider": insider_name,
            "role": role,
            "nature": nature,
            "instrument": raw.get("instrument", ""),
            "price": price,
            "quantity": qty,
            "amount": total,
            "currency": raw.get("currency", "Euros"),
            "is_purchase": is_purchase,
            "reference_url": raw.get("ref", ""),
        })

    return transactions


if __name__ == "__main__":
    # Test rapide
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=180)
    txs = scrape_france("FR0000120271", cutoff)  # TotalEnergies
    print(f"Trouvé {len(txs)} transactions")
    for tx in txs[:5]:
        print(f"  {tx['date']} - {tx['insider']} ({tx['role']}) - {tx['amount']:.0f}€ - {tx['nature']}")
