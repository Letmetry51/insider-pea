# Recherche : d'où viennent les chiffres

Ces scripts ont produit les chiffres affichés dans l'onglet **Aide** de la page. Ce sont des scripts d'étude,
écrits pour explorer (variables courtes, enchaînements par `exec`), pas du code de production : ils ne sont ni testés
ni contrôlés automatiquement. Ils restent ici pour que chacun puisse refaire les calculs et les critiquer.

## Refaire les calculs

Les données ne sont pas fournies (cours Yahoo : redistribution non autorisée). Il faut les retélécharger :

```
pip install -r requirements.txt numpy pandas
cd research/backtest
python _long.py        # télécharge les cours hebdomadaires depuis 1985 (Yahoo, ~1 000 sociétés) → long.npz (~20 min)
python _vol.py         # volatilité annuelle → v52.npy (utilisé par d'autres scripts)
python _moment.py      # épisodes de plus hauts → ep.npy
python _timing.py      # puis n'importe quel script d'étude
python ../chiffres_cles.py long.npz    # les chiffres clés, du plus flatteur au plus prudent (lisible seul)
python valeur.py       # 💎 sur nos données (comptes 2022-2025 : ../../data, voir tools/donnees.sh)
```

`_long.py` lit la liste des sociétés dans `data/` (produit par le calcul du soir). Les scripts s'enchaînent :
`_vix.py` → `_detect.py` → `_highs.py` → `_moment.py` → `_timing.py` → `_timing2.py` → `_timing4.py` → études suivantes.
Mesure commune : écart de rendement à 6 mois (26 semaines) avec la moyenne des sociétés de la même semaine, valeurs
extrêmes écrêtées à 2 % et 98 %, part des « chutes » (−25 % ou pire), et résultat par période (1997-2008, 2009-2017, 2018-2026).

## Chaque chiffre, son script et sa solidité

Statuts : **testé** = mesuré sur nos données (avec le biais du survivant, voir plus bas) ; **fragile** = ne tient pas
dans toutes les périodes ou hors échantillon ; **publié** = repris d'études publiées, pas testé ici ; **indépendant** =
vérifié sur une source extérieure.

| Règle ou chiffre | Script | Statut |
|---|---|---|
| Classement 12 mois, pente forte, +60 à +200 % : ≈ +8 points à 6 mois, 2 fois sur 3 en hausse | `_long.py`, `pente2.py`, `_timing.py`, `_acad.py` | testé |
| **Chiffre prudent** : +7,1 sur les années jamais vues (t 3,3), +6,1 après 1 % de frais, +3,8 avec 2 % de faillites supposées | `../chiffres_cles.py` | testé (hypothèses affichées) |
| Contrôle hors échantillon (réglages choisis sur 1997-2012, mesurés sur 2013-2026) | `_oos.py` | testé |
| 🔊 volumes en hausse (×1,5 sur 10 semaines) en priorité | `p3vol.py`, `_vol.py`, `_timing2.py` | testé |
| 📣 bond sur gros volume (+8 % et ×3 le volume) en priorité, repêchage des règles assouplies | `_timing2.py`, `_timing3.py`, `_timing4.py` | **fragile** : nul avant 2009 et hors échantillon |
| ⏸️ attendre au-dessus de la moyenne 10 semaines | `_timing.py`, `_oos.py` | testé, faible depuis 2013 |
| ⚡ écarter les cours très volatils (≥ 80 %/an) | `vol_crash.py`, `_oos.py` | testé, faible depuis 2013 |
| 🐻 écarter les sociétés parisiennes très vendues à découvert (2013-2026) | `../shorts.py` | testé (Paris seulement) |
| Alerte krach (marché −20 % sur un an) | `_crash.py`, `_vix.py` | testé |
| Garder 6 mois, protection −30 %, tailles de ligne, pause pendant un krach | `stress2.py`, `_sizing.py`, `_sorties.py`, `_sorties2.py` | testé |
| Effet momentum confirmé par le facteur européen de Kenneth French (+9,7 %/an contre +10,0 %) | `_wml.py`, `../french_compare.py` | indépendant |
| Mêmes règles 🎯 sur les États-Unis (≈ 1 500 sociétés du S&P 1500, aucun réglage) : +3,6 points à 6 mois sur 1997-2026 (t 2,3), +2,5 sur 2013-2026 (t 1,0), ≈ 0 avec frais et faillites supposées | `../us_check.py` (workflow « Recherche (à la demande) ») | indépendant : nettement plus faible qu'en Europe |
| 💎 Valeur (Piotroski) : 10 premières +5,1 points à 6 mois, 2 fois moins de chutes (départs 2024-2026) | `valeur.py` | **fragile** : 2 ans seulement (t 1,7) |
| Dosage 70 % 🎯 / 30 % 💎 | `../french_combo.py`, `factors.py`, `factors2.py` | publié (Piotroski 2000) + facteurs de Kenneth French |
| Pistes écartées : VIX, plus hauts répétés, moment d'achat, indicateurs du plan d'entrée (RSI, MACD, canal, support/résistance), achats de dirigeants croisés avec le 🎯 (bonus à réexaminer à la revue du 31/01/2027), bêta et pistes académiques, résultats, secteurs émergents ou en tendance (réserver à ces secteurs les 5 sociétés de la semaine : +8,5 points à 6 mois contre +10,5 sur 2013-2026, +7,2 contre +11,0 avant), signaux de début de hausse | `_vix.py`, `_highs.py`, `_moment.py`, `_indic.py`, `_insider_cross.py`, `_acad.py`, `_beta.py`, `_pead.py`, `_earn.py`, `_emerg.py`, `_sect5.py`, `_premices.py`, `_tard.py`, `_croise.py`, `early.py` | testé, sans effet stable |
| Tout croiser à la fois (modèle d'arbres de décision sur 24 éléments, appris sur 1997-2012, jugé sur 2013-2026) : version la plus solide (rangs de la semaine, objectif « 10 % meilleures », réappris chaque année, choisie sur 1997-2012) : dans le 🎯, tiers favorable +9 points contre +5, fortes hausses 17 % contre 6 %, t 2,6 ; pour les 5 sociétés de la semaine, +9,4 contre +9,6 avec la priorité 🔊 (t 0,3) | `_combine.py`, `_combine2.py` (scikit-learn) | testé, rien de plus que la priorité 🔊 |
| Creux et essoufflement, indicateurs de la bibliothèque ProRealCode (23/10/2026) : retournements (entrée en étape 2 de Weinstein, MACD-V qui repasse au-dessus de 0, divergence haussière du RSI, creux de −30 % puis croisement des moyennes) de −1,7 à −3,5 points à 6 mois, 9 à 14 % de chutes, 8 à 12 % menant au 🎯 ; creux en « V » (−30 %, rebond de +25 %, 🔊) au mieux +4,9 (t 1,3) ; essoufflement parmi les 🎯 (RSI ≥ 80, divergence baissière, MACD-V, 9 semaines de hausse, ralentissement, volumes en baisse) sans effet à 3 et 6 mois ; force du signal : seul 🔊 (+12,0 contre +7,1), 4-5 repères contre 0-2 +0,9 (t 0,5) | `_depart.py`, `_depart2.py`, `_depart3.py`, `_depart4.py` | testé, sans effet stable |
| Humeur du marché et paniques (23/10/2026) : marché pessimiste +10,4 % à 6 mois sur 2013-2026 contre +7,7 % euphorique, +2,2 contre +8,6 sur 2000-2012 (conseils d'entrée retirés de la page) ; panique (≥ 20 % des sociétés au plus bas de l'année) : comme d'habitude, −7 % de plus en médiane ; panique puis reprise (≤ 5 % en 8 semaines) : 15 épisodes, +11,4 % contre +7,1 %, de +4 à +17 % selon le réglage (t ≤ 1,5) ; 🎯 +8,5 pendant, +11,4 après ; 🚀 + pente forte 1 sur 6 à +40 % (1 sur 5,5 hors euphorie) | `_panique.py`, `_panique2.py`, `_regime.py`, `_brk26.py` | testé, sans effet stable |
| Piste pour la revue du 31/01/2027 : dosage selon l'agitation de la stratégie (Barroso et Santa-Clara 2015), sans levier ; à exposition moyenne égale, même rendement, pire baisse −38 % au lieu de −43 % (agitation mesurée sur 3 mois, 2000-2026) | `_volman.py` (après `_wml.py`) | testé, gain modeste sur le risque |
| Point pour la revue du 31/01/2027 : les comptes annuels ne comptent que 120 jours après la clôture (prudence des tests : jamais de comptes pas encore publiés). En direct, des comptes déjà publiés sont donc ignorés : 14 sociétés le 22/10/2026 (exercices clos en juin), plusieurs centaines de février à avril (exercices clos en décembre, publiés en février ou mars). À tester : délai de 60 ou 90 jours sur 1997-2026, ou comptes pris dès leur arrivée chez Yahoo | `euro_signal/build.mjs` (`accAt`), `ES.accountsAnalysis` (`asOf` − 120 jours) | à tester (stress test du 23/10/2026) |
| Achats de dirigeants (≈ 4 000 achats France et Suède : pas mieux qu'un titre pris au hasard) | calcul du soir (`euro_signal/build.mjs`, étude de l'historique long) | testé |
| Cours de secours : liste Euronext et Nasdaq Nordic identiques à Yahoo sur la même séance ; Stooq et Google Finance inutilisables depuis GitHub | `../source_probe.py`, `../backup_check.py` | testé |

## Limites communes

- **Biais du survivant** : seules les sociétés encore cotées en 2026 sont dans les données ; les sociétés disparues
  (faillites, rachats) manquent. Les chiffres absolus sont donc embellis ; les comparaisons entre règles le sont moins.
  Garde-fous : faillites supposées dans le chiffre prudent (`../chiffres_cles.py`) et facteur momentum de Kenneth French.
- **Données Yahoo** : cours ajustés des divisions et des dividendes (dividendes inclus), parfois erronés (sauts non
  ajustés coupés par `_long.py`).
- **Frais** : déduits dans le chiffre prudent (1 % par achat-vente) et dans les portefeuilles simulés, pas dans les études
  de règles (elles comparent des groupes entre eux). Impôts : aucun dans un PEA tant que l'argent y reste.
- **Beaucoup de variantes essayées** : une règle qui ne tient que sur une période peut devoir son résultat au hasard.
  Seuil retenu : t ≥ 3 (Harvey, Liu et Zhu, 2016) sur des années jamais vues ; le suivi réel des sélections (depuis le
  18/10/2026) est vérifié chaque soir, règle par règle.
