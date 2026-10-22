# Contribuer à Euro Signal

Merci de votre intérêt. Euro Signal est un outil gratuit sous licence MIT ; toute aide est bienvenue : une erreur repérée,
une idée à tester, du code ou de la documentation. *English summary at the end.*

## Par où commencer

- **Une question, une idée** : onglet [Discussions](https://github.com/Letmetry51/insider-pea/discussions).
- **Une erreur** (cours faux, chiffre incohérent, affichage cassé) : ouvrez un ticket avec le modèle « Erreur » : la société,
  l'endroit, ce que vous voyez et ce que vous attendiez.
- **Envie de coder** : les tickets [good first issue](https://github.com/Letmetry51/insider-pea/labels/good%20first%20issue)
  sont de petites tâches pour débuter ; la [feuille de route](https://github.com/Letmetry51/insider-pea/labels/feuille%20de%20route)
  liste ce qui est prévu ou à trancher.

## Les règles de la méthode, avant de proposer une règle de sélection

- Une règle n'entre dans l'outil que si elle est **testée sur l'historique** (cours hebdomadaires 1997-2026) avec la mesure
  commune : écart de rendement à 6 mois avec la société moyenne de la même semaine, et part des chutes de 25 % ou plus.
- Elle doit **tenir sur des années jamais vues** : réglée sur 1997-2012, vérifiée sur 2013-2026, avec t ≥ 3 (seuil exigeant
  de Harvey, Liu et Zhu, 2016, car beaucoup de variantes ont été essayées). Scripts et chiffres : `research/README.md`.
- **Le barème est gelé jusqu'à la revue du 31/01/2027** : les pistes prometteuses y sont proposées, pas ajoutées au fil de l'eau.
- Une piste testée sans effet est documentée (onglet Comment ça marche, « Testé et retiré »), jamais supprimée en silence.

## Proposer une modification de code

1. Forkez le dépôt et créez une branche.
2. Installez les outils (Node 20, Python 3.11) : `npm ci` et `pip install -r requirements.txt ruff`.
3. Vérifiez avant d'envoyer (les mêmes contrôles tournent sur chaque pull request) :

```
npm test                       # moteur
npm run lint                   # erreurs de code JavaScript
npm run format:check           # mise en forme (npm run format pour corriger)
node tools/stamp.mjs --check   # versions des fichiers de la page (npm run stamp après une modification de app/ ou core.js)
ruff check --select F scrapers euro_signal run.py
python euro_signal/test_positions.py && python euro_signal/test_health.py && python euro_signal/test_twin.py
python scrapers/test_financials.py && python scrapers/test_prices.py && python scrapers/test_yahoo.py
python scrapers/test_sectors.py && python scrapers/test_backup.py && python scrapers/test_sources.py
```

4. Pour voir la page avec les vraies données : `tools/donnees.sh` (données du dernier calcul), puis `python -m http.server`
   et http://localhost:8000/euro-signal.html. Pour l'affichage sur téléphone : `node euro_signal/ui_check.mjs` (Playwright).
5. Ouvrez la pull request : pourquoi, ce qui change, ce que vous avez vérifié. Un sujet par pull request.

## À ne jamais envoyer

- Des données : `data/` est publié sur la branche `site`, jamais dans `main`.
- Des positions, adresses email, clés d'API ou mots de passe : les secrets vont dans Settings → Secrets du dépôt.
- Des données dont la redistribution n'est pas autorisée (voir README, « Sources de données »).

## Style

- Interface et textes en français simple, sans jargon ; un chiffre testé plutôt qu'une promesse.
- Pensé d'abord pour le téléphone : chaque soir, toutes les fiches sont ouvertes à 390 px de large et contrôlées.
- JavaScript : ESLint et Prettier ; Python : ruff ; commentaires en français.

## Merci

Chaque contribution acceptée est citée dans le README (section « Contribuer »).

---

## English summary

Euro Signal is a free, MIT-licensed, self-hosted dashboard for European (PEA-eligible) stocks: a nightly GitHub Actions
workflow collects public data, ranks about 3,800 listed companies with momentum and value rules back-tested on 1997–2026,
publishes a static page on GitHub Pages and sends email alerts. JavaScript (engine and page) and Python (collectors,
research). The interface and docs are in French; issues and pull requests in English are welcome.

- **Questions and ideas**: Discussions. **Bugs**: open an issue (template provided). **First tasks**: issues labelled
  `good first issue`; roadmap: label `feuille de route`.
- **New selection rules** must be back-tested on 1997–2026 weekly prices with the common measure (6-month excess return over
  the average company, share of −25 % crashes) and hold on unseen years (tuned on 1997–2012, checked on 2013–2026, t ≥ 3).
  The rule set is frozen until the 31 January 2027 review. See `research/README.md`.
- **Quick start**: fork, `npm ci`, `pip install -r requirements.txt ruff`, then run the checks listed above (they also run on
  every pull request). Local page: `tools/donnees.sh`, `python -m http.server`, open http://localhost:8000/euro-signal.html.
- **Your own instance**: README, « Installer sa propre instance » (fork, GitHub Pages on the `site` branch, optional Gmail
  secrets, run the « Mise à jour quotidienne des données » workflow).
- Never commit data, personal positions, email addresses or API keys.
