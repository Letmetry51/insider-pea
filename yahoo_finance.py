"""
Enrichissement Yahoo Finance via yfinance.
Récupère: prix, objectif analystes, P/E, dividende, RSI, SMA200, position 52 sem.
"""
import yfinance as yf
from datetime import datetime


def enrich_with_yahoo(ticker: str) -> dict | None:
    """
    Récupère les données de marché pour un ticker Yahoo Finance.
    
    Args:
        ticker: Symbol Yahoo (ex: TEP.PA, SAP.DE, ASML.AS)
    
    Returns:
        Dict avec les données, ou None en cas d'erreur
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info

        # Prix et objectifs
        current_price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not current_price:
            return None

        target_mean = info.get("targetMeanPrice")
        target_high = info.get("targetHighPrice")
        target_low = info.get("targetLowPrice")
        num_analysts = info.get("numberOfAnalystOpinions")
        rec_key = info.get("recommendationKey")
        rec_mean = info.get("recommendationMean")

        # Fondamentaux
        pe = info.get("trailingPE")
        div_yield = info.get("dividendYield")
        if div_yield and div_yield > 1:
            div_yield = div_yield  # Yahoo renvoie parfois en %, parfois en ratio
        elif div_yield:
            div_yield = div_yield * 100

        market_cap = info.get("marketCap")
        currency = info.get("currency", "EUR")

        # Range 52 semaines
        high_52 = info.get("fiftyTwoWeekHigh")
        low_52 = info.get("fiftyTwoWeekLow")

        # Moyennes mobiles
        sma_50 = info.get("fiftyDayAverage")
        sma_200 = info.get("twoHundredDayAverage")

        # Calcul RSI simple (14 jours) depuis l'historique
        rsi = None
        try:
            hist = t.history(period="3mo")
            if len(hist) >= 15:
                rsi = compute_rsi(hist["Close"].tolist(), period=14)
        except Exception:
            pass

        # Calcul position dans le range 52 semaines (0-100%)
        position_52w = None
        if high_52 and low_52 and high_52 > low_52:
            position_52w = (current_price - low_52) / (high_52 - low_52) * 100

        # Upside potentiel sur 12 mois (objectif analystes)
        upside = None
        if target_mean and current_price:
            upside = (target_mean - current_price) / current_price * 100

        return {
            "ticker": ticker,
            "currentPrice": round(current_price, 2),
            "currency": currency,
            "targetMean": round(target_mean, 2) if target_mean else None,
            "targetHigh": round(target_high, 2) if target_high else None,
            "targetLow": round(target_low, 2) if target_low else None,
            "upside": round(upside, 2) if upside is not None else None,
            "numAnalysts": num_analysts,
            "recommendationKey": rec_key,
            "recommendationMean": round(rec_mean, 2) if rec_mean else None,
            "pe": round(pe, 2) if pe else None,
            "dividendYield": round(div_yield, 2) if div_yield else None,
            "marketCap": market_cap,
            "high52": round(high_52, 2) if high_52 else None,
            "low52": round(low_52, 2) if low_52 else None,
            "sma50": round(sma_50, 2) if sma_50 else None,
            "sma200": round(sma_200, 2) if sma_200 else None,
            "rsi": round(rsi, 1) if rsi else None,
            "position52w": round(position_52w, 1) if position_52w is not None else None,
            "nearLow52": position_52w < 25 if position_52w is not None else None,
            "aboveSma200": current_price > sma_200 if (current_price and sma_200) else None,
        }
    except Exception as e:
        print(f"Erreur Yahoo pour {ticker}: {e}")
        return None


def compute_rsi(prices: list, period: int = 14) -> float:
    """Calcul RSI classique sur une liste de prix de clôture."""
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i-1]
        if delta > 0:
            gains.append(delta)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-delta)
    
    # Moyenne initiale
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # Moyenne lissée (Wilder's smoothing)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


if __name__ == "__main__":
    # Test rapide
    result = enrich_with_yahoo("TEP.PA")
    if result:
        print(f"Teleperformance:")
        print(f"  Prix: {result['currentPrice']}€")
        print(f"  Objectif 12M: {result['targetMean']}€ (consensus {result['numAnalysts']} analystes)")
        print(f"  Upside: {result['upside']}%")
        print(f"  Recommandation: {result['recommendationKey']}")
        print(f"  RSI: {result['rsi']}")
        print(f"  Position 52w: {result['position52w']}%")
    else:
        print("Échec de la récupération")
