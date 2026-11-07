# Grain Signal

Aide à la décision pour **vendre ses céréales** (blé tendre, escourgeon et orge de printemps brassicoles, colza, maïs) et
**acheter ses engrais azotés**, sur le modèle d'Euro Signal : calcul automatique chaque matin, page web
([grain-signal.html](https://letmetry51.github.io/insider-pea/grain-signal.html)), emails quand il se passe quelque chose,
et un comité de 10 experts réuni par l'API Claude.

> Aide à la décision automatique, pas un conseil en investissement. La décision finale revient à l'exploitant.

## Ce qui tourne, et quand

| Quand | Quoi |
|---|---|
| Du mardi au samedi, 5h47 (heure d'hiver) | collecte, calcul, déclencheurs, email s'il y a lieu, publication |
| Le lundi, même heure | idem + **comité complet** (rapport envoyé par email) |
| Quand un déclencheur important saute | **comité d'alerte**, au plus 2 fois par semaine |
| À la demande | onglet Actions → « Grain Signal » → Run workflow (cases « comité » et « email de test ») |

## Sources

Euronext blé, colza et maïs (prix de compensation, via terre-net ; secours : Euronext live) · Yahoo Finance (blé CBOT et KC, maïs,
soja, huile de soja, canola, gaz TTF, Brent, EUR/USD) · CFTC (positions des fonds, *managed money*) · terre-net (urée, ammonitrate,
solution azotée, urée Égypte, prix physiques) · Banque mondiale (Pink Sheet mensuel, licence CC BY 4.0). Les historiques bruts
des cours restent dans le cache du workflow et ne sont jamais publiés.

## Règles

- **Technique** (`indicators.py`) : RSI 14, MACD 12/26/9, moyennes mobiles 20/50/200, Bollinger 20/2, Fibonacci du dernier
  mouvement, divergences RSI. Elle sert au **timing** : pas de vente en survente ou au bas du range de 3 mois, accélération en
  surachat qui s'essouffle ; ordres proposés au-dessus du cours (MM20, Fibonacci) et seuil de révision sous le plus bas de 3 mois.
- **Signal par culture** : celui du dernier comité (valable 8 jours). Chaque matin, son score est actualisé par la variation de la
  technique, des fonds et de la macro (10 % chacun) ; un changement de case dans la matrice (≤ −1 vendre, ≥ +0,5 attendre) marque
  la culture « à revoir » et demande un comité d'alerte. Sans comité valide : « tenir le plan ».
- **Engrais** (`build.py`, `module_engrais`) : ratio urée/blé en percentile sur 10 ans (≤ 20 acheter large, 20-60 suivre le plan,
  60-80 fractionner, ≥ 80 attendre), écart de rattrapage gaz − azote sur 3 mois (±15 pts : avancer ou retarder d'un cran, sauf
  si le gaz repasse sous sa MM20), saisonnalité, seuils du gaz (> 100 €/MWh, < 75 pendant 10 séances). Base : analyse
  Banque mondiale 2000-2024 (gaz → urée avec ≈ 1 mois de décalage ; aucun pouvoir prédictif des engrais sur le blé).
- **Comité** (`comite.py`, `prompt.md`) : reçoit les chiffres du matin, cherche sur le web ce que l'outil ne mesure pas (bilans,
  mer Noire, météo, demande, actualité) et rend un rapport complet suivi d'un bloc JSON (signaux, ordres, déclencheurs, calendrier).

## Réglages

`config.json` : sources, poids, seuils engrais, modèle du comité (`claude-opus-5-5` par défaut, ≈ 1 à 2 $ par comité ;
`claude-sonnet-5-5` divise le coût par deux environ), nombre de recherches web, fréquence des comités d'alerte.

Secrets du dépôt : `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_TO` (les mêmes qu'Euro Signal) et `ANTHROPIC_API_KEY` pour le comité.

## Tests

```
python grain_signal/test_grain.py
```

Une modification peut être essayée sans rien envoyer ni publier en la poussant sur la branche `grain-signal-essai`.
