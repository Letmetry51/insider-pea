# Insider PEA — Dashboard personnel 🇫🇷

Outil personnel gratuit de suivi des achats d'initiés sur les actions PEA françaises, avec scoring basé sur la recherche académique.

## 🎯 Ce que fait cet outil

- **Récupère automatiquement** les déclarations d'achats d'initiés auprès de l'AMF (via lestransactions.fr)
- **Enrichit les données** avec Yahoo Finance : cours actuels, objectifs analystes 12 mois, RSI, P/E, dividendes
- **Calcule un score Insider-First** (0-100 + garde technique ±15)
- **Affiche un dashboard web** avec recommandations triées
- **Mise à jour quotidienne automatique** via GitHub Actions (gratuit)
- **Coût total : 0 €**

## ✅ Prérequis

Tu as besoin de **trois choses gratuites** :

1. Un compte **GitHub** (5 min à créer : https://github.com/signup)
2. Un navigateur web (Chrome, Firefox, Safari...)
3. **Rien d'autre**. Pas besoin d'installer Python, pas besoin de serveur.

---

## 📋 Installation pas-à-pas

### Étape 1 — Créer ton repo GitHub (2 min)

1. Connecte-toi sur https://github.com
2. En haut à droite, clique sur le **"+"** puis sur **"New repository"**
3. Nom du repo : `insider-pea` (ou ce que tu veux)
4. Coche **"Public"** (important pour avoir GitHub Pages et Actions gratuits)
5. Coche **"Add a README file"**
6. Clique **"Create repository"**

### Étape 2 — Uploader les fichiers (5 min)

Dans ton nouveau repo, tu vas uploader tous les fichiers fournis dans le zip.

1. Sur la page du repo, clique sur **"Add file"** → **"Upload files"**
2. Glisse-dépose **tous les fichiers** du zip (garde la structure des dossiers)
3. En bas, clique sur **"Commit changes"**

La structure finale doit ressembler à ça :

```
insider-pea/
├── .github/
│   └── workflows/
│       └── update-data.yml      ← Le planificateur automatique
├── scrapers/
│   ├── __init__.py
│   ├── france_amf.py             ← Scraper AMF/lestransactions.fr
│   ├── yahoo_finance.py          ← Enrichissement Yahoo
│   └── scoring.py                ← Calcul du score
├── data/
│   └── .gitkeep                  ← Sera rempli automatiquement
├── index.html                    ← Le dashboard
├── run.py                        ← Script principal
├── requirements.txt              ← Dépendances Python
└── README.md                     ← Ce fichier
```

### Étape 3 — Activer GitHub Actions (1 min)

1. Dans ton repo, clique sur l'onglet **"Actions"** en haut
2. Si GitHub te demande "I understand my workflows, go ahead and enable them", clique dessus
3. Dans la liste à gauche, tu dois voir **"Mise à jour quotidienne des données"**

### Étape 4 — Lancer le premier scraping manuellement (3 min)

Le workflow est programmé pour tourner chaque jour à 19h, mais tu peux le lancer tout de suite :

1. Clique sur **"Mise à jour quotidienne des données"** (dans l'onglet Actions)
2. À droite, clique sur le bouton **"Run workflow"**
3. Dans le menu déroulant, clique sur **"Run workflow"** (vert)
4. **Attends 2-3 minutes** : un point orange qui tourne → un ✅ vert

Si ça passe au vert, le fichier `data/latest.json` a été créé dans ton repo !

### Étape 5 — Activer GitHub Pages pour le dashboard (2 min)

1. Dans ton repo, clique sur **"Settings"** (en haut à droite)
2. Dans la barre latérale gauche, clique sur **"Pages"**
3. Sous **"Build and deployment"** → **"Source"**, choisis **"Deploy from a branch"**
4. Sous **"Branch"**, choisis **"main"** et dossier **"/ (root)"**
5. Clique **"Save"**
6. Attends 1-2 minutes
7. Rafraîchis la page — en haut tu vois : **"Your site is live at https://TON_USERNAME.github.io/insider-pea/"**

### Étape 6 — Voir ton dashboard 🎉

Ouvre l'URL dans ton navigateur :

```
https://TON_USERNAME.github.io/insider-pea/
```

Ajoute cette URL à tes favoris.

**C'est fini.** À partir de maintenant, tout se met à jour automatiquement.

---

## 🔄 Fonctionnement automatique

- **Tous les jours du lundi au vendredi à 19h** (heure de Paris), GitHub lance le scraper
- Les données récupérées sont commitées dans `data/latest.json`
- GitHub Pages met à jour le dashboard automatiquement en quelques secondes
- **Tu n'as rien à faire**

## 📊 Ajouter / retirer des entreprises

1. Dans ton repo, ouvre `run.py`
2. Clique sur l'icône crayon ✏️ en haut à droite pour éditer
3. Dans la liste `TARGETS`, ajoute ou retire des lignes :
   ```python
   {"isin": "FR0000045072", "name": "Crédit Agricole", "ticker": "ACA.PA", "country": "FR", "sector": "Finance"},
   ```
4. Trouve l'ISIN sur https://live.euronext.com (chaque action a son ISIN à 12 caractères)
5. Trouve le ticker Yahoo sur https://finance.yahoo.com (ex : TEP.PA, SAP.DE)
6. Clique "Commit changes" en bas
7. Au prochain lancement (19h) les nouvelles entreprises seront incluses

## 🐛 Dépannage

### "Le workflow a échoué"

Va dans l'onglet Actions, clique sur le workflow qui a échoué, puis sur **"update-data"** pour voir les logs. Les causes fréquentes :

- **lestransactions.fr est temporairement down** → ça repartira le lendemain
- **Yahoo Finance rate limit** → même chose, résolu tout seul
- **Erreur de syntaxe Python** → si tu as modifié du code, reviens en arrière

### "Mon dashboard affiche 'Erreur: Fichier introuvable'"

Le premier scraping n'a pas encore tourné. Retourne à l'**Étape 4** et lance-le manuellement.

### "Pas de nouvelles données"

Les déclarations d'initiés sont **publiées avec délai** par l'AMF (3-4 jours ouvrés après la transaction). Pendant les vacances ou les périodes calmes, il n'y a parfois aucun nouvel achat pendant plusieurs jours. C'est normal.

## 📚 Sources de données

- **Achats d'initiés France** : [LesTransactions.fr](https://lestransactions.fr) (API gratuite documentée, agrégateur de la base BDIF de l'AMF)
- **Prix et analystes** : [Yahoo Finance](https://finance.yahoo.com) via la librairie Python [yfinance](https://github.com/ranaroussi/yfinance)

## ⚙️ Extensions futures possibles

- **Ajouter l'Allemagne** : scraper `portal.mvp.bafin.de` (export CSV quotidien)
- **Ajouter les alertes email** : utiliser un nouveau workflow GitHub Actions avec `smtplib`
- **Ajouter le backtest** : comparer les rendements passés aux scores

## 📖 Méthodologie de scoring

### Score Insider (0-100 pts — 70% du poids)

- **Cluster d'achats** (40 pts max) : plus il y a d'achats sur peu de temps, plus le signal est fort. Basé sur Kang, Kim, Wang (2018) qui montrent que les cluster buys génèrent +3.8% sur 90j vs +2% pour les achats isolés.
- **Volume cumulé** (30 pts max) : la conviction se mesure au montant engagé.
- **Qualité des insiders** (20 pts max) : un CEO vaut plus qu'un administrateur indépendant. Harvard 2022 montre que les achats de C-level génèrent +6% annualisé sur 3 ans.
- **Récence** (10 pts max) : les achats récents sont plus informatifs.

### Garde Technique (±15 pts max)

Ne peut **jamais** faire descendre le score en dessous du score insider pur. Elle sert uniquement à :
- **Confirmer** un signal : RSI survendu ou proche du bas 52 semaines = meilleur point d'entrée
- **Alerter** sur un timing moins favorable : RSI suracheté

**Règle absolue** : `Score final = max(insider, insider + tech)`. Un bon signal insider n'est jamais annulé.

## ⚠️ Avertissement

Cet outil est une **aide à la décision** basée sur des données publiques. Ce n'est **pas un conseil en investissement**. Les performances passées (académiques ou autres) ne préjugent pas des performances futures. Les dirigeants peuvent aussi se tromper, et leurs achats ne garantissent rien. Fais toujours tes propres recherches avant tout investissement.

## 📄 Licence

Usage personnel uniquement. Respecte les conditions d'utilisation des sources :
- lestransactions.fr : données publiques AMF
- Yahoo Finance : [Terms of Service](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) — usage personnel autorisé
