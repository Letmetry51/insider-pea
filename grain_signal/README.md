# Bulletin des grains

Outil d'aide à la décision pour qui **vend des céréales** (blé tendre, escourgeon et orge de printemps brassicoles, colza,
maïs) et **achète de l'azote** : chaque matin, le marché décrit en une page
([grain-signal.html](https://letmetry51.github.io/insider-pea/grain-signal.html)) et un email, à partir de l'actualité, de
son impact sur les prix et de l'analyse technique.

> L'outil décrit le marché ; il ne conseille ni de vendre ni d'acheter, ni quand, ni combien. La décision appartient à
> l'exploitant.

La page tient en 3 onglets : **Marché** (une ligne par culture et une pour l'azote : cours, lecture technique, effet de
l'actualité, repères ; le détail d'une culture au toucher), **Actualité** (synthèse et nouvelles traduites en impact sur les
prix) et **Méthode** (calculs, backtests, historique, sources). L'email et la synthèse PDF reprennent les mêmes chiffres.

## Ce qui tourne, et quand

| Quand | Quoi |
|---|---|
| Du lundi au samedi, vers 7 h 30 | collecte, calcul, **rapport du matin** par email avec la synthèse PDF, publication (calcul lancé à 7 h 03 par une tâche planifiée Claude, GitHub en secours) |
| Chaque matin | **actualités traduites** : titres du jour classés par l'IA (quelques centimes) |
| Le lundi | **lecture du marché de la semaine** par l'API Claude avec recherche web (≈ 4 $) : arguments haussiers et baissiers par culture, à surveiller, calendrier |
| Dès qu'il se passe quelque chose | alerte dans le rapport : fait majeur dans l'actualité, seuil de prix franchi, plus haut ou plus bas de 3 mois, changement de lecture technique, source en panne |
| À la demande | onglet Actions → « Bulletin des grains » → Run workflow (cases « lecture » et « email de test ») |

## Lectures

- **Cours** : Euronext (blé, colza, maïs, prix de compensation via terre-net, historique officiel depuis 2019) ; escourgeon et
  orge de printemps : prix physique Creil (pas de marché à terme).
- **Technique** (`indicators.py`) : note de −2 à +2 (moyenne 50 séances et sa pente, MACD, RSI, divergences) lue « hausse »
  (≥ +0,75), « baisse » (≤ −0,75) ou « neutre » ; résistances et supports (moyennes 20 et 50, Fibonacci, extrêmes de 3 mois).
  Les orges prennent la lecture du blé, niveaux ramenés au prix physique.
- **Actualité** (`collect.py`, `actualites.py`) : titres de Google Actualités (17 recherches en français et en anglais) et de 7
  flux de presse agricole, classés par l'API Claude sans recherche web : thème, nature, importance 1-3, effet −2/+2 par culture
  et sur l'azote, impact en une phrase sans conseil. Pression sur 7 jours par culture ; un fait majeur part en alerte.
- **Repères** (`decisions.py`) : prix sur 5 ans en percentile, plus haut de la campagne, report de la courbe moins le coût du
  stockage (`config.json`, `stockage`), prime locale physique − Euronext, saisonnalité, météo de 16 zones (9 régions françaises, 7 zones mondiales), bilans USDA, positions
  des fonds (Euronext et CFTC), humeur du marché, risque géopolitique (Caldara et Iacoviello).
- **Azote** (`build.py`, `module_engrais`) : prix France (urée, ammonitrate, solution), ratio urée/blé en percentile sur 10 ans,
  écart gaz − urée sur 3 mois, gaz TTF, saison, forme la moins chère par unité d'azote.
- **Ce matin** (`decisions.py`, `ouverture`), sur la ligne de chaque culture de l'onglet Marché et dans l'email : orientation de la
  séance à venir (Euronext ouvre à 10 h 45), vote des trois indices affichés sur la ligne, chacun +1, 0 ou −1 : Chicago depuis
  la clôture d'Euronext (au-delà de ±0,5 %), la technique, l'effet de l'actualité (au moins 0,5 sur 2). Orges : celle du blé.
  Fiabilité passée de Chicago + technique mesurée chaque matin (`backtest.py`, `ouverture` : sur 2019-2026, un peu mieux que le
  hasard pour le maïs, presque pas pour le blé et le colza) ; l'orientation est notée au jour le jour (`etat.json`,
  `ouverture_journal`).
- **Vos seuils** (`config.json`, `seuils`) : prix au-dessus ou en dessous desquels être prévenu, par culture et pour l'urée.

Backtest (`backtest.py`, onglet Méthode) : pour la lecture technique, l'humeur du marché et le risque géopolitique, le cours a-t-il
ensuite évolué autrement que par hasard (seuil calculé sur des cours tirés au sort de même nervosité) ?

## Réglages

`config.json` : sources, seuils de prix, frais de stockage, seuils du module engrais, modèle de la lecture hebdomadaire
(`claude-opus-5-5`) et nombre de recherches web.

Secrets du dépôt :
- `GMAIL_USER`, `GMAIL_APP_PASSWORD` : compte Gmail d'envoi (le même qu'Euro Signal) ;
- `GRAIN_ALERT_TO` : destinataires du Bulletin des grains, séparés par des virgules. S'il est absent, ce sont ceux d'Euro Signal (`ALERT_TO`) ;
- `ANTHROPIC_API_KEY` : lecture hebdomadaire et traduction des actualités.

Les historiques bruts des cours restent dans le cache du workflow et ne sont jamais publiés.

## Tests

```
python grain_signal/test_grain.py
```

Une modification peut être essayée sans rien envoyer ni publier en la poussant sur la branche `grain-signal-essai`.
