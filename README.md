# Euro Signal

Tableau de bord gratuit pour les actions européennes éligibles au PEA : chaque soir, il applique des règles
**testées sur 29 ans de cours** (momentum, plus un complément « valeur »), publie une sélection et envoie
les emails utiles (sélection du lundi, feu vert, protection −30 %, rappel à 6 mois, alerte krach…).

> **Avertissement.** Euro Signal applique automatiquement des règles statistiques à des données publiques.
> Ce n'est ni un conseil en investissement, ni une recommandation personnalisée, et les performances passées
> ne préjugent pas des performances futures. Les chiffres des tests sont optimistes (voir « Limites »).

*English summary: Euro Signal is a free, self-hosted dashboard for European (PEA-eligible) stocks. Every evening a
GitHub Actions workflow collects public data, ranks ~3,800 listed companies with momentum rules back-tested on
1997–2026 weekly prices (plus a small Piotroski-style value sleeve), publishes a static page on GitHub Pages and sends
email alerts. Not investment advice. Code under the MIT licence; data files belong to their sources.*

## Ce que fait l'outil

| | |
|---|---|
| 🎯 **Momentum** | sociétés en forte hausse sur 12 mois (+60 à +200 %), pente forte, comptes solides ; priorité aux volumes en hausse (🔊) et aux bonds sur gros volume (📣) ; 2 par secteur ; écarte les cours très volatils (⚡) et les sociétés parisiennes très vendues à découvert (🐻) |
| 💎 **Valeur** | complément : sociétés bon marché (cours / fonds propres) aux comptes solides (F-score de Piotroski ≥ 7) |
| 📋 **Sélection du lundi** | 5 🎯 + 2 💎, avec ✅ feu vert ou ⏸️ en attente (sous la moyenne 10 semaines) |
| 📧 **Emails** | sélection, feu vert, paliers de −10 %, protection −30 %, rappel à 6 mois, krach, auto-surveillance, bilan trimestriel |
| 🧭 **Secteurs**, 👔 **dirigeants** | radar des secteurs en tendance ; déclarations d'achats et de ventes des dirigeants (consultation) |
| 🔎 **Auto-contrôle** | chaque soir : tests, contrôle des fichiers et de l'affichage ; chaque règle est vérifiée sur les vraies sélections |

## La méthode en bref, et ses limites

Les règles viennent de tests sur les cours hebdomadaires de 1 067 sociétés européennes de 1997 à 2026 (écart à 6 mois
avec la société moyenne de la même semaine). Le détail chiffré est dans l'onglet **Aide** de la page.

**Limites à connaître :**
- **biais du survivant** : seules les sociétés encore cotées aujourd'hui sont dans les tests, les chiffres absolus sont donc
  embellis (l'effet momentum lui-même est confirmé par le facteur européen de Kenneth French) ;
- **beaucoup de variantes testées** : certaines règles peuvent devoir leur résultat au hasard. Contrôle hors échantillon
  (réglages choisis sur 1997-2012, mesurés sur 2013-2026) : +7,1 points contre +7,3 à +7,9 pour les meilleurs réglages ;
  la priorité 📣 n'y résiste pas, elle reste à confirmer par le suivi réel ;
- ni frais, ni impôts, ni dividendes dans les tests ; le 💎 n'a pas été testé sur ces données (études publiées) ;
- le suivi réel des sélections a commencé le 18/10/2026.

## Organisation du code

```
euro-signal.html        coque de la page (charge les fichiers ci-dessous, avec leur empreinte ?v=…)
app/                    interface : scripts chargés dans l'ordre (1-base … 8-actions) et feuille de style
euro_signal/
  core.js               moteur de calcul : fonctions pures, partagé par la page et par Node
  build.mjs             calcul du soir : classement, sélection, suivi réel, emails à envoyer
  tests.js              tests du moteur (npm test)
  check_outputs.mjs     contrôle des fichiers produits ; ui_check.mjs : contrôle de l'affichage (Playwright)
  send_alerts.py        envoi des emails (Gmail) ; positions.py : alertes sur vos positions ; send_health.py : email technique
  config.json           réglages (barème, sélection, alertes)
scrapers/               collecteurs : déclarations (AMF, FI, FSMA, AFM), ventes à découvert, cours et comptes (Yahoo), secteurs, presse
research/               scripts des études (voir research/README.md)
tools/stamp.mjs         empreintes des fichiers de la page (npm run stamp)
.github/workflows/      update-data.yml (chaque soir), history.yml (chaque jour), tests.yml (chaque modification)
data/                   données produites chaque soir (non couvertes par la licence)
```

## Installer sa propre instance

1. **Forker** ce dépôt (public : GitHub Pages et Actions sont alors gratuits).
2. **Settings → Pages** : publier depuis la branche `main`, dossier racine. La page est alors à
   `https://<vous>.github.io/<dépôt>/euro-signal.html` ; mettez cette adresse dans `euro_signal/config.json` (`dashboardUrl`).
3. **Settings → Secrets and variables → Actions** (facultatif, pour les emails) : `GMAIL_USER`, `GMAIL_APP_PASSWORD`
   (mot de passe d'application Google) et `ALERT_TO`. Sans eux, les emails sont seulement simulés.
4. **Actions** : activer les workflows, puis lancer « Update data » une première fois (environ 40 minutes).

Vos positions (« Je l'ai acheté ») partent par email vers votre propre boîte et ne sont jamais écrites dans le dépôt.

## Développer

Node 20 et Python 3.11.

```
npm ci                    # outils (ESLint, Prettier)
npm test                  # tests du moteur
npm run lint              # erreurs de code
npm run format            # mise en forme (Prettier)
npm run stamp             # après toute modification de app/ ou de core.js
pip install -r requirements.txt
python euro_signal/test_positions.py && python scrapers/test_sectors.py   # (et les autres test_*.py)
python -m http.server     # puis http://localhost:8000/euro-signal.html (nécessite un dossier data/ rempli)
```

Chaque modification poussée sur `main` ou proposée (pull request) passe automatiquement ces contrôles (workflow « Tests »).

## Sources de données

Les collecteurs lisent des sources publiques ; **vérifiez leurs conditions d'utilisation avant de republier les données**.

| Source | Usage | À savoir |
|---|---|---|
| Yahoo Finance (via `yfinance`) | cours, volumes, comptes, résultats, avis d'analystes | usage personnel ; la redistribution des données n'est en principe pas autorisée |
| AMF (France), Finansinspektionen (Suède), FSMA (Belgique), AFM (Pays-Bas) | déclarations des dirigeants | registres publics ; contiennent des noms de personnes (RGPD) |
| AMF, Consob, CNMV, AFM, FSMA, Bundesanzeiger, FCA | ventes à découvert déclarées | registres publics |
| Google News (flux RSS) | titres de presse des sociétés suivies | titres et liens seulement |
| Kenneth R. French Data Library | contrôle indépendant du facteur momentum européen | citer la source |

## Licence

Code sous licence **MIT** (voir `LICENSE`). Les données du dossier `data/` appartiennent à leurs sources et ne sont pas
couvertes par cette licence.
