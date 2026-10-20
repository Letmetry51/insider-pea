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
| Pistes écartées : VIX, plus hauts répétés, moment d'achat, indicateurs du plan d'entrée (RSI, MACD, canal, support/résistance), achats de dirigeants croisés avec le 🎯 (bonus à réexaminer à la revue du 31/01/2027), bêta et pistes académiques, résultats, secteurs émergents, signaux de début de hausse | `_vix.py`, `_highs.py`, `_moment.py`, `_indic.py`, `_insider_cross.py`, `_acad.py`, `_beta.py`, `_pead.py`, `_earn.py`, `_emerg.py`, `_premices.py`, `_tard.py`, `_croise.py`, `early.py` | testé, sans effet stable |
| Piste pour la revue du 31/01/2027 : dosage selon l'agitation de la stratégie (Barroso et Santa-Clara 2015), sans levier ; à exposition moyenne égale, même rendement, pire baisse −38 % au lieu de −43 % (agitation mesurée sur 3 mois, 2000-2026) | `_volman.py` (après `_wml.py`) | testé, gain modeste sur le risque |
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
