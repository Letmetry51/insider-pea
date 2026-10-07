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
| `ALERT_TO` | l'adresse qui reçoit les alertes (la même, en général) |

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

Sans ce secret, ces trois pays apparaissent « Non configurés » dans l'onglet Sources. Pour arrêter : supprime
le secret, puis résilie l'abonnement.

## Étape 4 — Premier lancement avec email de test (10 min d'attente)

1. Onglet **Actions** → **Mise à jour quotidienne des données** → bouton **Run workflow**.
2. Coche **Envoyer aussi un email de test**, puis **Run workflow**.
3. Attends la coche verte. Les premiers soirs, comptez 35 à 50 minutes : la FSMA impose une requête
   toutes les 30 secondes, et Euro Signal rattrape les 4 derniers mois par lots de 36 fiches.
   Tant que ce rattrapage n'est pas fini, la source FSMA apparaît « partielle » et les alertes des
   sociétés belges restent bloquées. Ensuite, comptez une vingtaine de minutes.
4. Vérifie ta boîte mail : un message « [Euro Signal] Email de test » doit être arrivé.
5. Ouvre https://letmetry51.github.io/insider-pea/euro-signal.html. Sur téléphone, ajoute-la à
   l'écran d'accueil depuis le menu du navigateur.

C'est terminé. Ensuite, tout tourne seul du lundi au vendredi à 18 h UTC (19 h ou 20 h à Paris).

---

## Ce que tu reçois

Un email seulement quand **toutes** les conditions sont réunies :

- titre liquide (au moins 1 M€ échangés par jour en moyenne sur 20 séances) et 200 séances de cours ;
- cours à jour et collecte AMF à jour ;
- score ≥ 60/100 ;
- au moins deux familles de signaux indépendantes (initiés, rachats, résultats, marché), dont un événement publié depuis moins de 14 jours ;
- aucune déclaration ambiguë ;
- information nouvelle : jamais deux fois la même alerte.

L'email détaille le score ligne par ligne, les achats (date, déclarant, prix, lien vers le PDF de
l'AMF), la comparaison au cours actuel et aux plus hauts et plus bas sur 52 semaines, ainsi que les
risques.

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
- **Le score n'est pas une probabilité de hausse** et aucun ordre n'est passé. L'onglet Validation
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
« en échec » dans l'onglet Sources, et ses alertes restent bloquées.

## Modifier un réglage

Fichier `euro_signal/config.json` : clique sur le crayon (Edit), modifie, puis **Commit changes**.
Exemples : `"minScore": 60` (seuil d'alerte) ou `"minAdv20Eur": 1000000` (liquidité minimale).

## En cas de problème

| Ce que tu vois | Ce qu'il faut faire |
|---|---|
| Croix rouge dans Actions | Clique dessus puis sur l'étape en rouge : le journal explique l'erreur. |
| Pas d'email de test | Vérifie les 3 secrets (noms exacts) et le code à 16 lettres ; recrée-le si besoin. |
| Onglet Sources : AMF « En échec » | Le site source n'a pas répondu. Les alertes sont bloquées, sans fausse conclusion « aucun achat ». Ça repart au prochain soir. |
| Un titre « sans ticker Yahoo » | Ajoute la correspondance ISIN → ticker dans `ISIN_TO_TICKER` de `run.py` (ex. `"FR0000062234": "ODET.PA"`). |
| Alerte « Statut incertain » | Gmail a peut-être accepté le message avant une coupure. Elle n'est jamais renvoyée : regarde ton dossier Envoyés. |
| Étape « 2b » : `clé absente` | Le secret `INSIDERSCREENER_API_KEY` n'est pas lu : vérifie son nom exact, puis relance. |
| Étape « 2b » : `clé refusée ou inactive (HTTP 401)` | Recolle la clé dans le secret (crayon → nouvelle valeur) et vérifie que l'abonnement API est actif. |
| Étape « 2b » : `HTTP 403` | Ton offre n'inclut pas ce marché : vérifie l'offre sur insiderscreener.com/api-access. |
| Étape « 2b » : `HTTP 429` ou `budget mensuel` | Crédits ou débit dépassés : rien à faire, ça repart au soir suivant ou au mois suivant. |
| Étape « 2b » : `HTTP 400` ou `réponse illisible` | Demande à Claude de « vérifier les diagnostics Euro Signal ». |
| Révoquer l'accès Gmail | https://myaccount.google.com/apppasswords → supprimer « Euro Signal ». |
