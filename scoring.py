"""
Module de scoring Insider-First.
- Score insider: 0-100 pts (le signal principal)
- Garde technique: -15 à +15 pts (ne peut jamais annuler le signal insider)
- Score final = max(insider, insider + tech)
"""
from datetime import datetime

C_LEVEL_ROLES = {"CEO", "CFO", "DG", "Président", "Directeur Général", "President"}


def compute_insider_score(transactions: list[dict]) -> int:
    """
    Score 0-100 basé sur la recherche académique.
    
    - Cluster buys (Kang, Kim, Wang 2018): signal le plus fort
    - Volume cumulé (Lakonishok 2001): +4.82% sur 6 mois pour strong buys
    - Qualité insiders (Harvard 2022): C-level = +6% annualisé
    - Récence: signal frais = plus informatif
    """
    if not transactions:
        return 0

    count = len(transactions)
    total_amount = sum(tx.get("amount", 0) for tx in transactions)
    
    # Détection C-level
    has_c_level = any(
        any(role.lower() in (tx.get("role", "") or "").lower() for role in C_LEVEL_ROLES)
        for tx in transactions
    )
    
    unique_insiders = len(set(tx.get("insider", "") for tx in transactions))
    has_multi = unique_insiders >= 2

    # Achats récents (< 30 jours)
    now = datetime.now()
    recent_count = 0
    for tx in transactions:
        try:
            tx_date = datetime.fromisoformat(tx["date"][:10])
            if (now - tx_date).days <= 30:
                recent_count += 1
        except (ValueError, KeyError):
            pass

    score = 0

    # Cluster (40 pts max)
    if count >= 5:
        score += 40
    elif count >= 3:
        score += 32
    elif count >= 2:
        score += 22
    else:
        score += 12

    # Volume (30 pts max)
    if total_amount >= 2_000_000:
        score += 30
    elif total_amount >= 1_000_000:
        score += 25
    elif total_amount >= 500_000:
        score += 20
    elif total_amount >= 100_000:
        score += 14
    elif total_amount >= 50_000:
        score += 8
    else:
        score += 4

    # Qualité insiders (20 pts max)
    if has_c_level and has_multi:
        score += 20
    elif has_c_level:
        score += 15
    elif has_multi:
        score += 12
    else:
        score += 5

    # Récence (10 pts max)
    if recent_count >= 3:
        score += 10
    elif recent_count >= 1:
        score += 7
    else:
        score += 2

    return min(score, 100)


def compute_tech_guard(quote: dict | None) -> dict:
    """
    Garde technique: -15 à +15 pts seulement.
    Sert à confirmer ou alerter, jamais à écraser le signal insider.
    """
    if not quote:
        return {"adj": 0, "rsi": None, "nearLow52": None, "aboveSma200": None, "reason": "Pas de données marché"}

    rsi = quote.get("rsi")
    near_low = quote.get("nearLow52")
    above_sma = quote.get("aboveSma200")

    adj = 0
    reasons = []

    # RSI
    if rsi is not None:
        if rsi <= 30:
            adj += 8
            reasons.append(f"RSI {rsi:.0f} survendu (+8)")
        elif rsi <= 45:
            adj += 4
            reasons.append(f"RSI {rsi:.0f} plutôt bas (+4)")
        elif rsi >= 75:
            adj -= 8
            reasons.append(f"RSI {rsi:.0f} suracheté (-8)")
        elif rsi >= 65:
            adj -= 3
            reasons.append(f"RSI {rsi:.0f} chaud (-3)")

    # Position 52 semaines
    if near_low is True:
        adj += 5
        reasons.append("Proche bas 52s (+5)")
    elif near_low is False:
        adj -= 2

    # Tendance SMA200
    if above_sma is True:
        adj += 2
        reasons.append("> SMA200 (+2)")
    elif above_sma is False:
        adj -= 2
        reasons.append("< SMA200 (-2)")

    # Clamp à [-15, +15]
    adj = max(-15, min(15, adj))

    return {
        "adj": adj,
        "rsi": rsi,
        "nearLow52": near_low,
        "aboveSma200": above_sma,
        "reasons": reasons,
    }


def compute_verdict(total_score: int) -> dict:
    """Verdict final basé sur le score total."""
    if total_score >= 85:
        return {"label": "ACHAT FORT", "color": "#34d399", "icon": "🟢"}
    if total_score >= 65:
        return {"label": "ACHAT", "color": "#4ade80", "icon": "🟡"}
    if total_score >= 45:
        return {"label": "INTÉRESSANT", "color": "#facc15", "icon": "🔵"}
    return {"label": "FAIBLE", "color": "#4e5768", "icon": "⚪"}


if __name__ == "__main__":
    # Test
    test_txs = [
        {"insider": "Jean Dupont", "role": "CEO", "amount": 500000, "date": "2026-04-01"},
        {"insider": "Marie Martin", "role": "CFO", "amount": 200000, "date": "2026-04-05"},
        {"insider": "Paul Durand", "role": "Administrateur", "amount": 100000, "date": "2026-04-10"},
    ]
    score = compute_insider_score(test_txs)
    print(f"Score insider: {score}/100")
    
    verdict = compute_verdict(score)
    print(f"Verdict: {verdict['icon']} {verdict['label']}")
