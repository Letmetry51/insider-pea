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
| 📅 **Agenda des résultats** | publications des 6 prochaines semaines (sélection, 🎯 et 💎 proposées, vos suivis) et surprises des 14 derniers jours ; simple repère : acheter juste avant n'a pas été moins bon (2020-2026) |
| 📧 **Emails** | sélection, feu vert, paliers de −10 %, protection −30 %, rappel à 6 mois, krach, auto-surveillance, bilan trimestriel |
| 🧭 **Secteurs**, 👔 **dirigeants** | radar des secteurs en tendance ; déclarations d'achats et de ventes des dirigeants (consultation) |
| 🔎 **Auto-contrôle** | chaque soir : tests, contrôle des fichiers et de l'affichage ; chaque règle est vérifiée sur les vraies sélections |

## La méthode en bref, et ses limites

Les règles viennent de tests sur les cours hebdomadaires de 1 067 sociétés européennes de 1997 à 2026 (écart à 6 mois
avec la société moyenne de la même semaine). Le détail chiffré est dans l'onglet **Aide** de la page.

**Du chiffre flatteur au chiffre prudent** (🎯, écart à 6 mois avec la société moyenne de la même semaine, dividendes inclus) :

| Étape | Écart |
|---|---|
| tout l'historique, 1997-2026 | +8,1 points |
| années jamais vues au réglage, 2013-2026 | +7,1 (t = 3,3 : passe le seuil exigeant de 3) |
| moins 1 % de frais par achat-vente | +6,1 |
| moins 2 % de sélections supposées en faillite (−100 %) | **+3,8** (≈ +8 par an) |

- **biais du survivant** : les sociétés disparues manquent ; d'où la faillite supposée ci-dessus, et le contrôle par le facteur
  momentum européen de Kenneth French, calculé avec les disparues : +9,7 % par an contre +10,0 % pour nous (1998-2026) ;
- **beaucoup de variantes testées** (512 réglages) : chiffre retenu sur des années jamais vues ; la priorité 📣 n'y résiste pas,
  elle reste à confirmer par le suivi réel ;
- **frais et impôts** : 0,5 à 2 % par achat-vente selon le courtier ; dans un PEA, 18,6 % de prélèvements sociaux sur les gains
  à la sortie (taux 2026), comme pour un fonds indiciel ;
- **💎 valeur** : premier test sur nos données (comptes 2022-2025, départs de mai 2024 à avril 2026) : +5,1 points à 6 mois pour
  les 10 premières, deux fois moins de chutes, mais 2 ans seulement (t = 1,7) ;
- **suivi réel** automatique des sélections depuis le 18/10/2026 (premiers résultats à 3 mois en janvier 2027) ;
- **l'outil lui-même** : données de Yahoo Finance par un accès non officiel (s'il est coupé, l'outil perd l'essentiel),
  erreurs de Yahoo reprises (en partie corrigées), mise à jour une fois par soir, sans support. Ce qu'il fait de plus ou de
  moins que Yahoo Finance et les sites gratuits : onglet **Comment ça marche** (pli « 🆚 Face à Yahoo Finance… »).

Tout se recalcule : `research/chiffres_cles.py` (ce tableau), `research/backtest/valeur.py` (💎), détail dans `research/README.md`.
Toutes les sources de données, les études académiques (avec ce qui en a été retenu) et les méthodes de calcul sont listées
dans l'onglet **Comment ça marche** de la page (pli « 📚 Sources, études et méthodes »).

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
.github/workflows/      update-data.yml (chaque soir), history.yml (chaque jour), tests.yml (chaque modification),
                        publish.yml (republie la page après une modification du code)
.github/actions/        restore-data (données de la veille), publish-site (publication sur la branche « site »)
tools/donnees.sh        copie locale des données du dernier calcul
```

La branche `main` ne contient que le code. Chaque calcul publie la page et ses données sur la branche **`site`**, en une
seule version sans historique (le dépôt ne grossit pas) ; GitHub Pages sert cette branche. Les fichiers qu'aucun calcul ne
peut refaire (journal des alertes, suivi réel, historiques) sont aussi gardés 30 jours en copie de secours (Actions → artefacts).

## Installer sa propre instance

1. **Forker** ce dépôt (public : GitHub Pages et Actions sont alors gratuits).
2. **Settings → Pages** : publier depuis la branche `site`, dossier racine (elle est créée par le premier calcul). La page est alors à
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
tools/donnees.sh          # données du dernier calcul (branche site) dans data/
python -m http.server     # puis http://localhost:8000/euro-signal.html
```

Chaque modification poussée sur `main` ou proposée (pull request) passe automatiquement ces contrôles (workflow « Tests »).

## Sources de données

Les collecteurs lisent des sources publiques ; **vérifiez leurs conditions d'utilisation avant de republier les données**.

| Source | Usage | À savoir |
|---|---|---|
| Yahoo Finance (via `yfinance`) | cours, volumes, comptes, résultats, avis d'analystes, description d'activité | usage personnel ; la redistribution des données n'est en principe pas autorisée |
| AMF (France), Finansinspektionen (Suède), FSMA (Belgique), AFM (Pays-Bas) | déclarations des dirigeants | registres publics ; contiennent des noms de personnes (RGPD) |
| AMF, Consob, CNMV, AFM, FSMA, Bundesanzeiger, FCA | ventes à découvert déclarées | registres publics |
| Google News (flux RSS) | titres de presse des sociétés suivies | titres et liens seulement |
| Kenneth R. French Data Library | contrôle indépendant du facteur momentum européen | citer la source |

## Licence

Code sous licence **MIT** (voir `LICENSE` ; portée et avertissement dans `NOTICE.md`). Les données du dossier `data/` appartiennent à leurs sources et ne sont pas
couvertes par cette licence.
