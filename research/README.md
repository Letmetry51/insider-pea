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
| 😱 Thermomètre de panique (part des sociétés au plus bas de l'année, 23/10/2026) : panique générale au-delà de 20 % (d'habitude 4 à 5 %) ; marché ensuite comme d'habitude (+7,7 % à 6 mois) mais −8 % de plus en médiane ; positions 🎯 touchées (−15 % en 4 semaines) mieux reparties pendant une panique générale que seules (écart à 6 mois +3,8 / +5,9 / +10,8 points selon la période, contre −5,0 / +1,5 / +2,5) → tuile « pas de vente de panique » ; société seule à son plus bas, marché calme : −3,3 points (t −3,4) ; entre 10 et 20 %, 🎯 +3,2 contre +6,4 avec 2 fois plus de chutes (même signe dans les 3 périodes, 6 % des cas) | `_panique3.py`, `_panique4.py`, `_panique5.py` | testé (affichage seulement) |
| Point pour la revue du 31/01/2027 : protection −30 % pendant une panique générale. Positions à −30 % gardées : +13,8 % en 3 mois (68 % en hausse) pendant une panique, contre +4,6 % (52 %) en marché calme ; 11 % chutent encore de 25 % contre 17 %. Biais du survivant fort (faillites absentes) : à vérifier avant tout changement | `_panique4.py` | à tester |
| « Ces moments-là » (25/10/2026 : Wallenius, Repsol, Bravida, JCDecaux, consolidation puis départ) : Repsol a eu le feu vert ⏸️ au point entouré (21,8 le 03/07) ; Wallenius et Repsol sont ensuite sortis du 🎯 pendant leur base (pente sur 6 mois retombée sous +41 %) et revenus en septembre, 6 semaines et +13 % plus tard en médiane ; Bravida et JCDecaux n'avaient pas encore de momentum (12 mois +10 % et +35 %). Sortie de base seule : +1 à +2 points à 6 mois, 1 sur 6 rejoint le 🎯 ; anciennes 🎯 reprises à la sortie de base : +6,4 à +6,9 (t 1,9-2,2 ; nouvelle entrée 🎯 +5,9, moyenne 🎯 +8,1) ; 📣 bond hors 🎯 en tendance : +7,7 la semaine du bond (t 2,6), +5,8 dans les 4 semaines (t 3,2), +12,4 à 12 mois, positif dans chaque période, sans tendance −0,4 → affiché (📣 démarrage sur bond, hors note). Aucun des 4 n'avait de 📣 (volumes ×2,2 à ×2,3) : seuil gardé à ×3, pas réglé sur ces exemples | `_cercles.py`, `_sortie_base.py`, `_reprise.py`, `_bond.py`, `_bond2.py` | testé (affichage seulement) |
| « Ce tracé » (Bravida sur 5 ans, 27/10/2026) : plus haut de 5 ans vieux de 2 ans ou plus, creux de 35 % ou plus, puis retour à moins de 5 % de ce plus haut (1997-2026, une entrée par société et par semestre) : tous +1,5 point à 6 mois (1 395 cas), par un bond ≥ +10 % +4,0 (259 cas, nul en 1997-2008), progressif +0,5. Le tracé seul ne prédit rien ; ce qui compte est le bond sur volume au plus haut de l'année, avec ou sans longue base (+5,1 contre +5,2). Bonds ≥ +10 % sur volume ≥ 2× : au plus haut de l'année +5,5 (2 171 cas, t 8,4), 5 à 20 % dessous +1,1, plus de 20 % dessous −0,1 (16 % de chutes) ; sans tendance −0,2 | `_longue_base.py`, `_longue_base2.py` | testé |
| 📣 élargi (affichage, 27/10/2026) : semaine ≥ +8 % sur 3 fois le volume, ou sur 2 fois si elle fait un nouveau plus haut de l'année ; en tendance, société classée (hors tiers le plus faible : +3,0 seulement), hors 🎯 : +5,5 points à 6 mois (t 9,0, 2 264 cas), +11,2 à 12 mois, positif dans chaque période, 1 sur 4 à +50 % en un an, 4 sur 10 rejoignent le 🎯 dans les 6 mois ; l'ajout seul (2 à 3 fois) +5,3 et +10,7. Plus de volume, mieux (2-3× +4,5 ; 3-5× +6,6 ; ≥ 5× +8,1). Pas d'urgence : entrée 1 à 13 semaines après, +4,5 à +4,8 ; après 8 semaines, bond tenu +5,4, perdu +2,4. Ni la taille du bond, ni la période de résultats, ni un premier plus haut ne départagent. Bravida signalée le 20/02/2026 (≈ 101 SEK), 🎯 le 09/10 (≈ 146) ; Repsol le 06/03, JCDecaux le 13/03 ; Wallenius non | `_lb_grid.py`, `_lb_gagnantes.py`, `_lb_regle.py`, `_lb_final.py` | testé (affichage seulement) |
| Sélection 4 🎯 + 1 📣 (appliquée le 27/10/2026, gel des règles levé) : portefeuille simulé 1998-2026, règles de ES.pickN sans les comptes ni la liquidité, 5 lignes chaque semaine gardées 6 mois, frais 0,3 % par sens ; une place pour le meilleur 📣 démarrage (bond il y a 3 semaines au plus, 3 fois le volume ou 2 fois au plus haut de l'année, tendance, hors tiers le plus faible, 2 par secteur) : +1,3 point par an face à la sélection d'avant (t 2,3), −0,3 sur 1998-2008 (nul), +1,9 sur 2009-2017, +2,6 sur 2018-2026 ; avec une note minimale pour le 📣, +1,3 aussi ; sur 10 lignes, 8 + 2 : +0,9, positif dans chaque période. Moins bons : 📣 élargi dans l'ordre et le repêchage (+0,8, négatif en 1998-2008), 📣 admis au palier 0 (+0,9, idem). Place 📣 occupée 77 % des semaines dans la simulation (moins souvent en vrai : PEA, comptes lus, 3 M€/jour, note ≥ 70) | `_selection_sim.py` à `_selection_sim5.py` | testé |
| Seuil de hausse sur 12 mois du 🎯 abaissé de +60 % à +50 / +40 / +30 % (même portefeuille) : +0,1 / +0,3 / −0,1 point par an sur 5 lignes, −0,3 / −0,5 / −0,7 sur 10 lignes : gardé à +60 % (le palier assoupli prend déjà +30 à +60 % avec une pente moyenne) | `_selection_sim.py`, `_selection_sim2.py`, `_selection_sim4.py` | testé, rejeté |
| Signaux d'avance sur le prix (27/10/2026, une entrée par société et par semestre, écart à 6 mois) : force relative au plus haut de l'année quand le cours ne l'est pas encore −0,0 (en tendance, hors 🎯 : +0,6) ; meneuses quand le marché est à 10 % ou plus sous son plus haut +0,7 (−1,6 sur 2009-2017) ; volume cumulé (OBV) au plus haut avant le cours +0,3 (en tendance +1,0, t 1,7) ; accumulation (volumes des semaines de hausse ≥ 2 fois ceux des semaines de baisse sur 13 semaines, à moins de 15 % du plus haut, hors 🎯) +1,2 (t 4,7, positif dans chaque période) mais faible ; 8 à 15 % de ces signaux mènent au 🎯 dans les 6 mois. Rien d'utilisable pour arriver plus tôt que le 📣 (+5,6) | `_avance.py` | testé, rejeté |
| Qualité du 📣 (27/10/2026) : volume du bond 2-3× +5,3, 3-5× +7,5, ≥ 5× +9,0 ; accumulation dans les 13 semaines avant le bond +7,4 contre +3,8 sans ; 12 mois tiers fort +7,4 contre +4,8 ; deuxième bond en 6 mois +9,7 contre +4,8 pour le premier (positif dans chaque période). Dans la sélection simulée, ranger la place 📣 selon ces marques : +0,2 point par an (t 0,5) ; selon le seul volume du bond −0,9 ; 2 places 📣 au lieu d'une +0,2 : l'ordre actuel (🔊, 📣 sur 3 fois le volume, note) les capte déjà | `_avance2.py`, `_avance_sim.py` | testé, rien de plus |
| Piste pour la revue du 31/01/2027 : 📣 bond hors 🎯 comme deuxième porte d'entrée (+7,7 la semaine du bond, +5,8 dans les 4 semaines, t 3,2 ; version élargie du 27/10 : +5,5 à 6 mois, +11,2 à 12 mois, une entrée par bond) ; et garder une ancienne 🎯 dont seule la pente est retombée pendant une consolidation (+6,4 au-dessus de la moyenne 10 semaines, t 3,6, mais sous la moyenne 🎯) : à juger sur le portefeuille simulé de 10 lignes avant tout changement | `_bond.py`, `_reprise.py` | appliqué le 27/10/2026 (place 📣 réservée) ; le maintien d'une ancienne 🎯 reste à tester |
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
