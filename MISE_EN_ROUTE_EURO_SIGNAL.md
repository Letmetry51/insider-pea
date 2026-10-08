# Euro Signal — mise en route (une seule fois, environ 20 minutes)

Euro Signal s'ajoute à ton dépôt `insider-pea`, qui tourne déjà chaque soir sur GitHub.
Après cette mise en route, **tout est automatique**. Chaque soir de semaine, GitHub :

- collecte les déclarations des dirigeants en **France (AMF)**, **Belgique (FSMA)** et **Pays-Bas (AFM)**,
  et, avec ta clé Insider Screener, en **Allemagne (BaFin)**, **Espagne (CNMV)** et **Italie (Consob)** ;
- récupère les **cours**, les **résultats** (BPA publié et consensus), les **communiqués** des sociétés
  (rachats d'actions, perspectives relevées ou abaissées) et les **révisions des analystes** ;
- calcule les scores, t'envoie les alertes par email et met à jour le tableau de bord.

Tu n'as plus rien à saisir.

Tableau de bord : **https://letmetry51.github.io/insider-pea/euro-signal.html**
(ton tableau de bord Insider PEA actuel reste à sa place, sur `index.html`).

---

## Étape 1 — Déposer les fichiers dans le dépôt (5 min)

1. Décompresse le zip sur ton ordinateur : tu obtiens un dossier `insider-pea`.
2. Ouvre https://github.com/Letmetry51/insider-pea
3. Clique sur **Add file** → **Upload files**.
4. Ouvre le dossier `insider-pea` décompressé, sélectionne **tout son contenu** (y compris le dossier
   `.github` : sous Windows, il est visible normalement) et fais-le glisser dans la page GitHub.
5. En bas, clique sur **Commit changes**.

Les fichiers `run.py`, `.gitignore` et `.github/workflows/update-data.yml` remplacent les anciens :
c'est voulu. `run.py` ne change que sur un point : il lit 300 pages au lieu de 80, pour couvrir
réellement 180 jours (avant, la collecte s'arrêtait vers 3 mois et demi).

## Étape 2 — Créer un mot de passe d'application Gmail (5 min)

Ce mot de passe spécial permet à GitHub d'envoyer des emails depuis ton compte. Ce n'est pas ton
mot de passe Gmail, et tu peux le révoquer à tout moment.
**Ne le colle jamais dans une conversation**, seulement dans GitHub (étape 3).

1. La validation en deux étapes doit être active sur ton compte Google
   (https://myaccount.google.com/security).
2. Ouvre https://myaccount.google.com/apppasswords
3. Nom de l'application : `Euro Signal`, puis **Créer**.
4. Google affiche un code de 16 lettres : garde la page ouverte pour l'étape 3.

## Étape 3 — Enregistrer trois secrets dans GitHub (3 min)

Dans le dépôt : **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Crée ces trois secrets, un par un :

| Nom (exactement) | Valeur |
|---|---|
| `GMAIL_USER` | ton adresse Gmail (celle du mot de passe d'application) |
| `GMAIL_APP_PASSWORD` | le code de 16 lettres de l'étape 2 |
| `ALERT_TO` | l'adresse qui reçoit les alertes ; plusieurs adresses possibles, séparées par des virgules |

Les secrets sont chiffrés par GitHub : personne ne peut les relire, même dans un dépôt public.
**Créer ces secrets vaut activation de l'envoi réel.** Sans eux, Euro Signal reste en simulation :
il journalise les alertes sans rien envoyer.

## Étape 3 bis — Allemagne, Espagne, Italie avec ta clé Insider Screener (3 min)

Ces trois pays ne sont pas collectables gratuitement et légitimement (BaFin : robots.txt qui interdit la
collecte ; CNMV : serveurs de GitHub bloqués ; Consob : plus de tableau publié). Insider Screener relève ces
registres toutes les heures et revend l'accès par API ; l'offre **API Starter** (1 000 crédits par mois) suffit.

1. Sur https://www.insiderscreener.com/api-access (Compte → API Access), copie ta clé.
   Elle n'est affichée en entier qu'une fois : si tu ne l'as plus, clique sur « rotate » pour en créer une
   nouvelle (l'ancienne cesse alors de fonctionner).
2. Dans GitHub : **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
3. Name : `INSIDERSCREENER_API_KEY` — Secret : ta clé, sans espace avant ni après — **Add secret**.

**Ne colle jamais cette clé ailleurs que dans ce champ GitHub** (ni dans une conversation, ni dans un fichier).

Ce que fait Euro Signal avec la clé, chaque soir :

- Allemagne, Espagne, Italie : il récupère les nouvelles déclarations depuis le soir précédent.
- Belgique, Pays-Bas : **en secours seulement**. Si la collecte directe FSMA ou AFM du soir n'est pas
  complète, il comble le trou par Insider Screener (les doublons entre les deux sont écartés).
- Consommation : environ 200 crédits pour le rattrapage des 4 derniers mois (répartis sur les premiers soirs,
  120 au plus par soir), puis 15 à 25 par soir, soit 350 à 550 par mois.
- **Garde-fou** : jamais plus de 900 crédits par mois. Si ce plafond est atteint, les pays concernés passent
  « partiels » et leurs alertes sont bloquées jusqu'au mois suivant, sans fausse conclusion « aucun achat ».

Sans ce secret, ces trois pays apparaissent « Non configurés » dans l'onglet Comment ça marche, rubrique État des données. Pour arrêter : supprime
le secret, puis résilie l'abonnement.

## Étape 4 — Premier lancement avec email de test (10 min d'attente)

1. Onglet **Actions** → **Mise à jour quotidienne des données** → bouton **Run workflow**.
2. Coche **Envoyer aussi un email de test**, puis **Run workflow**.
3. Attends la coche verte. Les premiers soirs, comptez 35 à 50 minutes : la FSMA impose une requête
   toutes les 30 secondes, et Euro Signal rattrape les 4 derniers mois par lots de 36 fiches.
   Tant que ce rattrapage n'est pas fini, la source FSMA apparaît « partielle » et les alertes des
   sociétés belges restent bloquées. Ensuite, comptez une vingtaine de minutes.
4. Vérifie ta boîte mail : un message « [Euro Signal] Email de test » doit être arrivé.
5. Ouvre https://letmetry51.github.io/insider-pea/euro-signal.html. Sur téléphone, installe-la comme une
   application : menu du navigateur → « Ajouter à l'écran d'accueil » (Android, Chrome) ou bouton Partager →
   « Sur l'écran d'accueil » (iPhone, Safari). Elle s'ouvre alors en plein écran avec son icône, et le dernier
   classement reste consultable sans connexion.

C'est terminé. Ensuite, tout tourne seul du lundi au vendredi à 18 h UTC (19 h ou 20 h à Paris).

## Le tableau de bord en 4 onglets

- **Opportunités** : les sociétés où un dirigeant a acheté, classées par décote (prix payé par rapport au plus haut
  des 52 semaines). Touchez une ligne pour la fiche complète (graphique, déclarations, conseil d'achat et de revente).
- **Achats des dirigeants** : toutes les déclarations des 3 derniers mois.
- **Alertes et suivi** : les emails envoyés et leur évolution depuis l'envoi.
- **Comment ça marche** : la méthode en 5 étapes, puis, repliés, le barème du score, l'état des sources,
  les résultats passés (auto-apprentissage) et la liste des titres suivis.

La page s'ouvre vite, même sur téléphone : le classement se charge d'abord, le détail des fiches (cours et
déclarations complètes) seulement quand vous en ouvrez une.

## Seuil des achats significatifs

Seuls comptent les achats d'au moins **100 000 €** par dirigeant (cumulés sur 14 jours). Les petits achats
symboliques sont ignorés dans le score, le classement et les alertes. Pour changer :
`"minBuyerEur": 100000` dans `euro_signal/config.json`, rubrique `insiders`.

---

## Ce que tu reçois

Par défaut, trois sortes d'emails seulement :

- **chaque lundi, la sélection de la semaine** (les 5 meilleurs dossiers, avec les nouveautés signalées et le bilan
  des sélections précédentes comparé au CAC 40) ;
- **les alertes de revente** sur les achats que tu as déclarés (objectif atteint, seuil de protection franchi…) ;
- **les signaux de sortie** sur ces mêmes achats déclarés (vente d'un dirigeant, MM50 repassée sous la MM200, recul de 20 %).

Les dossiers « très forts » ne font plus l'objet d'un email séparé : ils sont repris dans la sélection du lundi et
visibles chaque soir dans le tableau de bord. Pour retrouver un email par alerte d'achat :
`"buyEmails": true` dans la rubrique `alerts` de `euro_signal/config.json`. Les conditions d'une alerte d'achat sont :

- titre liquide (au moins 1 M€ échangés par jour en moyenne sur 20 séances) et 200 séances de cours ;
- cours à jour et collecte AMF à jour ;
- note ≥ 75/100 (100 = dossier idéal réaliste ; en pratique, seuls les 2 ou 3 meilleurs dossiers du moment l'atteignent) ;
- au moins deux familles de signaux indépendantes (initiés, rachats, résultats, marché), dont un événement publié depuis moins de 14 jours ;
- aucune déclaration ambiguë ;
- information nouvelle : jamais deux fois la même alerte.

L'email détaille le score ligne par ligne, les achats (date, déclarant, prix, lien vers le PDF de
l'AMF), la comparaison au cours actuel et aux plus hauts et plus bas sur 52 semaines, ainsi que les
risques.

## La sélection de la semaine (chaque lundi)

Même quand aucune alerte ne part, tu reçois chaque lundi soir un email « Sélection de la semaine » avec les
5 meilleurs dossiers du moment : achat d'au moins 100 000 € par un dirigeant ces 30 derniers jours, titre liquide,
données fiables, société solide, note d'au moins 50/100, classés par note puis par décote. C'est une liste courte
à étudier, pas un ordre d'achat. La même liste est en tête de l'onglet Opportunités. Si aucune société ne remplit
les critères, l'email le dit : mieux vaut ne rien faire que forcer un choix. Réglages : rubrique `selection` de
`euro_signal/config.json` (`size`, `minScore`, `recentDays`, `weekday`, `enabled`).

## Acheter cette semaine ou attendre ? Le repère historique

Chaque soir, Euro Signal rejoue les sélections des lundis passés (jusqu'à 52 semaines), avec seulement l'information
connue ce jour-là. Chaque dossier de la sélection est situé par rapport à ces sélections passées :

- 🟢 **Remarquable** : parmi les 10 % meilleurs dossiers des sélections passées ;
- 🟡 **Bon** : au-dessus de la moyenne ;
- ⚪ **Ordinaire** : sous la moyenne, rien ne presse.

L'email et le tableau de bord donnent aussi un verdict pour la semaine entière : 🟢 semaine exceptionnelle (le meilleur
dossier bat 80 % des semaines passées), 🟡 semaine dans la moyenne, ⚪ semaine faible (mieux vaut attendre). Ce repère
mesure la force du signal, pas un rendement promis : le bilan des sélections passées (comparé au CAC 40) dira avec le temps
si les semaines « exceptionnelles » rapportent vraiment plus.

## Informations croisées

- **Valorisation par rapport aux pairs** : VE/EBITDA (à défaut PER prévisionnel ; cours/actif net pour banques, assurances
  et foncières) comparé à la médiane d'au moins 5 sociétés de la même industrie, sinon du même secteur.
- **Positions vendeuses des fonds** (≥ 0,5 % du capital), publiées par l'AMF, le Bundesanzeiger, la CNMV, la Consob, l'AFM
  et la FSMA : un dirigeant qui achète pendant que des fonds parient à la baisse est signalé dans la fiche et la sélection.

- **Position concurrentielle** : rang par chiffre d'affaires dans son industrie parmi les sociétés européennes suivies
  (au moins 5) : Leader (n° 1), Challenger (n° 2 et 3), Suiveur, Acteur de niche (moins de 3 % du total).

## Analyse des comptes (📊)

Pour chaque société suivie, Euro Signal lit les 4 derniers exercices publiés (compte de résultat, bilan, flux de
trésorerie) et affiche dans la fiche : chiffre d'affaires, marge opérationnelle, résultat net, trésorerie disponible,
dette nette / EBITDA et rentabilité des fonds propres, avec leur tendance, puis le **F-score de Piotroski** (0 à 9) point
par point : 7 à 9 = comptes solides et en amélioration, 0 à 3 = en dégradation. Un F-score faible rend l'avis plus prudent
(0 ou 1 : « éviter »). Non applicable aux banques et assurances. Les comptes sont relus tous les 30 jours ; la première
collecte se complète sur quelques soirs, en commençant par les sociétés où un dirigeant a acheté. Le F-score est aussi mesuré
« en observation » (comptes publiés à la date de chaque achat) avant de peser dans la note.

## L'avis croisé et les symboles

Pour chaque société où un dirigeant a acheté, Euro Signal croise la note, le repère historique, la solidité financière,
la valorisation, les ventes à découvert, la tendance et le calendrier, et donne un avis (aide à la décision, jamais un ordre) :
🟢 à étudier en priorité · 🟡 à surveiller · ⚪ attendre · 🔴 éviter pour l'instant (société fragile, hors PEA, dirigeants
vendeurs nets ou titre peu liquide). La fiche dit aussi pourquoi une société n'est pas dans la sélection de la semaine.

Symboles : 👔 DG ou DAF · 👥 plusieurs dirigeants · 💰 gros montant · 🏷️ forte décote · 😱 achat dans la panique ·
📈 tendance haussière · 🔻 cours en repli · 💶 moins chère que ses pairs · 💸 plus chère · 🏆 leader ou challenger ·
⚠️ ventes à découvert (rouge au-delà de 5 % du capital) · ⚡ duel : des fonds parient à la baisse pendant que les
dirigeants achètent fort. Le duel n'est ni bon ni mauvais en soi : l'issue est binaire (rebond violent si les dirigeants ont
raison, chute si les fonds ont vu un problème), donc position réduite.

La rubrique « Méthode et preuves » (onglet Comment ça marche) résume la logique et les résultats mesurés sur nos données.

## Les étoiles

★★★★★ très fort et remarquable dans l'historique · ★★★★ très fort (note ≥ 75) · ★★★ fort (50 à 74) · ★★ moyen ·
★ faible. Elles s'affichent pour les sociétés où un dirigeant a acheté, dans le classement, la sélection, la fiche et
les emails.

## Critères en observation

Rotation sectorielle (secteur plus fort que le marché sur 6 mois), achats de dirigeants dans plusieurs sociétés du même
secteur, petites et moyennes valeurs, montant de l'achat rapporté à la capitalisation, valorisation sous les pairs, positions
vendeuses : ces critères sont mesurés chaque soir contre le CAC 40 (rubrique Résultats passés), **sans effet sur la note**.
Un critère n'entre dans la note que s'il montre un avantage net sur au moins 60 cas, à la revue de janvier.

## Après l'alerte : suivi et signaux de sortie

Chaque alerte envoyée est suivie pendant un an (onglet Alertes et suivi) : évolution depuis l'envoi, comparaison au CAC 40.
Un email « Signal de sortie » part une seule fois par signal si un dirigeant vend, si la MM50 repasse sous la MM200,
si le cours tombe plus de 10 % sous le prix payé par les dirigeants ou s'il recule de 20 % depuis son plus haut.
Ce ne sont pas des ordres de vente.

## Vos achats : conseil de revente et alertes personnelles

Dans la fiche d'un titre, l'encadré « Conseil d'achat et de revente » donne des repères pour entrer et pour sortir.
Si vous achetez, ouvrez « Je l'ai acheté : me prévenir pour revendre », indiquez votre prix, votre objectif de hausse
(par exemple +20 %) et votre seuil de protection (par exemple −15 %), puis envoyez l'email préparé (il vous est adressé).
Chaque soir, Euro Signal relit ces emails dans vos « Envoyés » et vous écrit une seule fois par événement : objectif atteint,
seuil de protection franchi, vente d'un dirigeant, MM50 repassée sous la MM200, recul de 20 % depuis le plus haut.
Le bouton « Je l'ai vendu » arrête le suivi. Vos positions ne sont jamais écrites dans le dépôt ni sur le tableau de bord
(qui sont publics) et ces emails ne vont qu'à vous. Pour changer un objectif, renvoyez simplement un nouvel email.

## L'outil apprend de ses résultats

Chaque mois, Euro Signal compare chaque composante du score (décote, panique, DG, cluster, tendance MM50 > MM200, force relative)
aux résultats réels, 60 séances après chaque achat de dirigeant. Un poids ne bouge que d'un point par mois, seulement si
l'écart est net sur au moins 60 cas, et reste entre 0 et 2 fois sa valeur d'origine. Chaque ajustement est annoncé par email
et visible dans l'onglet Comment ça marche, rubrique Résultats passés. Pour désactiver : `"learning": {"mode": "off"}` dans `euro_signal/config.json`.

## Ce que l'outil ne fait pas (à savoir)

- **Allemagne, Espagne, Italie** : couvertes par l'API Insider Screener (étape 3 bis, payante).
  Le format exact de ses réponses n'étant pas public, un échantillon est déposé dans
  `data/diagnostics/insiderscreener.json` au premier appel, pour vérification.
- **Rachats et perspectives** : lus dans les **titres** des communiqués de l'émetteur, en 6 langues. Un
  titre ambigu n'est pas compté. Le montant d'un rachat n'est connu que s'il figure dans le titre.
- **Résultats** : surprise sur le BPA uniquement, avec le consensus Yahoo figé à la publication. Il n'y a
  pas de consensus de chiffre d'affaires, et beaucoup de petites capitalisations n'ont pas de consensus du tout.
- **Éligibilité PEA** : jamais devinée. Elle est indiquée « à vérifier » dans chaque email ;
  vérifie-la avant d'acheter.
- **Le score n'est pas une probabilité de hausse** et aucun ordre n'est passé. La rubrique Résultats passés (onglet Comment ça marche)
  mesure, au fil des mois, ce qu'ont donné les achats passés ; les premiers mois, les effectifs sont
  trop faibles pour conclure.
- **Données publiques** : le tableau de bord est visible par toute personne qui connaît l'adresse,
  comme ton dashboard actuel. Il ne contient ni ton adresse email ni tes secrets.

## Premier passage : vérification des formats

Les registres belge et néerlandais n'étaient pas accessibles depuis l'environnement où l'outil a été
construit. Leurs collecteurs s'adaptent aux colonnes trouvées et déposent un court échantillon dans
`data/diagnostics/` (fichiers `fsma.json` et `afm.json`). Il en va de même pour `insiderscreener.json` si l'API est configurée. Après le premier lancement,
demande à Claude de « vérifier les diagnostics Euro Signal » : le dépôt étant public, il peut les lire et ajuster les
collecteurs si un format diffère. En attendant, une source mal lue apparaît « partielle » ou
« en échec » dans l'onglet Comment ça marche, rubrique État des données, et ses alertes restent bloquées.

## Modifier un réglage

Fichier `euro_signal/config.json` : clique sur le crayon (Edit), modifie, puis **Commit changes**.
Exemples : `"minScore": 60` (seuil d'alerte) ou `"minAdv20Eur": 1000000` (liquidité minimale).
`"excludeLegalEntities": true` : les achats de sociétés (fonds, investisseurs, l'émetteur lui-même) sont exclus, mais la holding personnelle d'un dirigeant compte comme lui. `"strict"` exclut toutes les sociétés, `false` les compte toutes.

## En cas de problème

| Ce que tu vois | Ce qu'il faut faire |
|---|---|
| Croix rouge dans Actions | Clique dessus puis sur l'étape en rouge : le journal explique l'erreur. |
| Pas d'email de test | Vérifie les 3 secrets (noms exacts) et le code à 16 lettres ; recrée-le si besoin. |
| État des données : AMF « En échec » | Le site source n'a pas répondu. Les alertes sont bloquées, sans fausse conclusion « aucun achat ». Ça repart au prochain soir. |
| Un titre « sans ticker Yahoo » | Ajoute la correspondance ISIN → ticker dans `ISIN_TO_TICKER` de `run.py` (ex. `"FR0000062234": "ODET.PA"`). |
| Alerte « Statut incertain » | Gmail a peut-être accepté le message avant une coupure. Elle n'est jamais renvoyée : regarde ton dossier Envoyés. |
| Étape « 2b » : `clé absente` | Le secret `INSIDERSCREENER_API_KEY` n'est pas lu : vérifie son nom exact, puis relance. |
| Étape « 2b » : `clé refusée ou inactive (HTTP 401)` | Recolle la clé dans le secret (crayon → nouvelle valeur) et vérifie que l'abonnement API est actif. |
| Étape « 2b » : `HTTP 403` | Ton offre n'inclut pas ce marché : vérifie l'offre sur insiderscreener.com/api-access. |
| Étape « 2b » : `HTTP 429` ou `budget mensuel` | Crédits ou débit dépassés : rien à faire, ça repart au soir suivant ou au mois suivant. |
| Étape « 2b » : `HTTP 400` ou `réponse illisible` | Demande à Claude de « vérifier les diagnostics Euro Signal ». |
| Révoquer l'accès Gmail | https://myaccount.google.com/apppasswords → supprimer « Euro Signal ». |
