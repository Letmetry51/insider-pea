# Grain Signal

Aide à la décision pour **vendre ses céréales** (blé tendre, escourgeon et orge de printemps brassicoles, colza, maïs) et
**acheter ses engrais azotés**, sur le modèle d'Euro Signal : calcul automatique chaque matin, page web
([grain-signal.html](https://letmetry51.github.io/insider-pea/grain-signal.html)), emails quand il se passe quelque chose,
et un comité de 11 experts réuni par l'API Claude.

> Aide à la décision automatique, pas un conseil en investissement. La décision finale revient à l'exploitant.

La page tient en 4 onglets : **Aujourd'hui** (une ligne par culture : que faire, combien, à quel prix ; l'avis du comité),
**Cultures** (une culture à la fois : graphique, 4 repères, plan ; le reste replié), **Actualité** (synthèse et nouvelles
qui comptent) et **Méthode** (fonctionnement, backtest, carnet de bord, sources, tout replié). Emails et synthèse PDF
reprennent les mêmes mots et les mêmes chiffres.

## Ce qui tourne, et quand

| Quand | Quoi |
|---|---|
| Du mardi au samedi, 5h47 (heure d'hiver) | collecte, calcul, déclencheurs, email s'il y a lieu, publication |
| Le lundi, même heure | idem + **comité complet** (rapport envoyé par email) |
| Chaque matin, avant le comité | **actualités traduites** : titres du jour classés par l'IA (quelques centimes) |
| Quand un déclencheur important saute ou qu'un fait majeur tombe | **comité d'alerte**, au plus 2 fois par semaine |
| À la demande | onglet Actions → « Grain Signal » → Run workflow (cases « comité » et « email de test ») |

## Sources

Euronext blé, colza et maïs (prix de compensation, via terre-net ; secours : Euronext live ; historique depuis novembre 2019 : fichiers statistiques quotidiens publics d'Euronext, avec contrôle croisé) · Yahoo Finance (blé CBOT et KC, maïs,
soja, huile de soja, canola, gaz TTF, Brent, EUR/USD) · Euronext (rapport hebdomadaire des positions, fonds d'investissement, PDF officiel) · CFTC (positions des fonds, *managed money*) · terre-net (urée, ammonitrate,
solution azotée, urée Égypte, prix physiques) · Banque mondiale (Pink Sheet mensuel, licence CC BY 4.0). Les historiques bruts
des cours restent dans le cache du workflow et ne sont jamais publiés.

Aides à la décision (grain_signal/decisions.py) : prix sur 5 ans en percentile, stocker ou vendre (frais réglables dans
config.json, section stockage), prime locale physique − Euronext, saisonnalité (Chicago depuis 2000), météo Open-Meteo de 10
zones (15 % de la lecture de marché), carnet de bord des avis du comité jugés à 4 et 8 semaines (data/grain/carnet.json).
La page s'installe sur le téléphone (grain-signal.webmanifest).

Actualité, géopolitique et psychologie (onglet Actualité) : titres de Google Actualités (17 recherches en français et en anglais)
et de 7 flux de presse agricole, gardés 7 jours sans doublon (`collect.py`), classés chaque matin par l'API Claude sans
recherche web (`actualites.py`, modèle `actualites.modele`, ≈ 0,05 $ par jour) : thème, nature, importance 1-3, effet −2/+2
par culture et sur l'azote, impact en une phrase. Pression de l'actualité sur 7 jours par culture ; un fait majeur envoie une
alerte et convoque le comité. Indice de risque géopolitique de Caldara et Iacoviello (quotidien et par pays). Humeur du marché
(RSI, écart à la MM200, élan 20 séances, fonds) et biais d'ancrage (plus haut de campagne, « encore 5 € »). Backtest
(`backtest.py`) : ni l'indice géopolitique ni l'humeur n'annoncent les prix mieux que le hasard (seuil calculé sur des cours
tirés au sort) ; ils éclairent le comité et le rythme des ventes, sans entrer dans la note de marché.
Synthèse PDF A4 (grain_signal/rapport_pdf.py) jointe aux emails du comité (lundi, alertes) et à l'email de test.

Note des fonds : rapport Euronext 70 %, CFTC 30 % (indice Euronext calculé à partir de 26 semaines d'historique, rattrapé
progressivement sur 3 ans). Une source en échec deux jours distincts de suite déclenche un email « Source en panne » (une seule
fois par incident), puis un email « Source rétablie ».

## Règles

- **Technique** (`indicators.py`) : RSI 14, MACD 12/26/9, moyennes mobiles 20/50/200, Bollinger 20/2, Fibonacci du dernier
  mouvement, divergences RSI. Elle sert au **timing** : pas de vente en survente ou au bas du range de 3 mois, accélération en
  surachat qui s'essouffle ; ordres proposés au-dessus du cours (MM20, Fibonacci) et seuil de révision sous le plus bas de 3 mois.
- **Signal par culture** : celui du dernier comité (valable 8 jours). Chaque matin, son score est actualisé par la variation de la
  technique, des fonds et de la macro (10 % chacun) ; un changement de case dans la matrice (≤ −1 vendre, ≥ +0,5 attendre) marque
  la culture « à revoir » et demande un comité d'alerte. Sans comité valide : « tenir le plan ».
- **Plan de vente** (`config.json`, `calendrier`) : tranches par défaut pour chaque culture (au plus 35 % avant la moisson ;
  orge de printemps en partie par contrat malterie). Chaque carte affiche la tranche due pour chaque récolte en cours de vente
  et l'action : vendre, avancer, décaler, couvrir, ou placer un ordre au-dessus du marché quand le cours est au creux. Pour
  une récolte à venir, les ordres sont décalés de l'écart entre son échéance (septembre, août, novembre) et celle du jour.
- **Engrais** (`build.py`, `module_engrais`) : ratio urée/blé en percentile sur 10 ans (≤ 20 acheter large, 20-60 suivre le plan,
  60-80 fractionner, ≥ 80 attendre), écart de rattrapage gaz − azote sur 3 mois (±15 pts : avancer ou retarder d'un cran, sauf
  si le gaz repasse sous sa MM20), saisonnalité, seuils du gaz (> 100 €/MWh, < 75 pendant 10 séances). Base : analyse
  Banque mondiale 2000-2024 (gaz → urée avec ≈ 1 mois de décalage ; aucun pouvoir prédictif des engrais sur le blé).
- **Comité** (`comite.py`, `prompt.md`) : reçoit les chiffres du matin, cherche sur le web ce que l'outil ne mesure pas (bilans,
  mer Noire, météo, demande, actualité) et rend un rapport complet suivi d'un bloc JSON (signaux, ordres, déclencheurs, calendrier).

## Réglages

`config.json` : sources, poids, seuils engrais, modèle du comité (`claude-opus-5-5` par défaut, ≈ 1 à 2 $ par comité ;
`claude-sonnet-5-5` divise le coût par deux environ), nombre de recherches web, fréquence des comités d'alerte.

Secrets du dépôt :
- `GMAIL_USER`, `GMAIL_APP_PASSWORD` : compte Gmail d'envoi (le même qu'Euro Signal) ;
- `GRAIN_ALERT_TO` : destinataires de Grain Signal, séparés par des virgules. S'il est absent, ce sont ceux d'Euro Signal (`ALERT_TO`) ;
- `ANTHROPIC_API_KEY` : comité IA et traduction des actualités.

## Tests

```
python grain_signal/test_grain.py
```

Une modification peut être essayée sans rien envoyer ni publier en la poussant sur la branche `grain-signal-essai`.
