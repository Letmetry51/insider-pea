# 🚀 Guide de démarrage rapide — 15 minutes chrono

Ce guide te mène de **"j'ai le zip"** à **"mon dashboard marche tout seul"** en 6 étapes.

## Étape 1 — Compte GitHub (2 min) ⏱️

Si tu n'as pas encore de compte :
1. Va sur https://github.com/signup
2. Entre ton email, choisis un mot de passe, un username
3. Valide ton email

Si tu as déjà un compte, saute cette étape.

---

## Étape 2 — Créer le repo (1 min) ⏱️

1. Une fois connecté, clique sur le **"+"** en haut à droite → **"New repository"**
2. Remplis le formulaire :
   - **Repository name** : `insider-pea`
   - **Description** : `Mon dashboard personnel`
   - Coche **🔘 Public** (obligatoire pour GitHub Pages gratuit)
   - ⚠️ **NE COCHE PAS** "Add a README file" (on a déjà le nôtre)
3. Clique sur **"Create repository"** (bouton vert en bas)

Tu arrives sur une page grise avec des instructions. **Ignore-les**, passe à l'étape 3.

---

## Étape 3 — Uploader les fichiers (3 min) ⏱️

1. Sur la page du repo vide, clique sur le lien bleu **"uploading an existing file"**
2. **Extrais le zip** que tu as téléchargé sur ton bureau (clic droit → Extraire tout)
3. Tu obtiens un dossier `insider-pea-backend` qui contient :
   - `.github/` (dossier)
   - `data/` (dossier)
   - `scrapers/` (dossier)
   - `index.html`
   - `run.py`
   - `requirements.txt`
   - `README.md`
   - `QUICKSTART.md`

4. **Sélectionne TOUT ce qu'il y a DANS le dossier** (pas le dossier lui-même) et **glisse-dépose** dans la zone "Drag files here" de GitHub
   - Sur Mac : Cmd+A dans le dossier → glisser
   - Sur Windows : Ctrl+A dans le dossier → glisser

5. Attends le upload (barre de progression en bas)
6. Tout en bas, laisse le message par défaut et clique **"Commit changes"** (bouton vert)

### ✅ Vérification

Recharge la page. Tu dois voir à la racine :

```
📁 .github
📁 data
📁 scrapers
📄 README.md
📄 QUICKSTART.md
📄 index.html
📄 requirements.txt
📄 run.py
```

**Si `.github` n'apparaît pas** : c'est parce que GitHub cache parfois les dossiers commençant par un point. Clique sur `run.py` pour vérifier que tu vois bien du code Python — si oui, tout est OK.

---

## Étape 4 — Activer GitHub Actions (1 min) ⏱️

1. En haut de la page du repo, clique sur l'onglet **"Actions"**
2. Tu vois peut-être un bouton jaune **"I understand my workflows, go ahead and enable them"** → clique dessus
3. Dans la liste à gauche, tu dois voir **"Mise à jour quotidienne des données"**

---

## Étape 5 — Premier scraping manuel (3 min) ⏱️

Le workflow est programmé pour tourner seul tous les jours à 19h, mais tu dois le lancer une première fois pour créer les données.

1. Clique sur **"Mise à jour quotidienne des données"** (dans l'onglet Actions)
2. À droite, clique sur le bouton **"Run workflow"** (encadré blanc avec flèche)
3. Dans le menu qui s'ouvre, laisse "Branch: main" et clique sur le bouton vert **"Run workflow"**
4. Attends ~30 secondes, puis **recharge la page**
5. Tu vois apparaître une ligne avec :
   - 🟡 Un point jaune qui tourne (en cours)
   - ⏱️ Attends 2-3 minutes
   - ✅ Un check vert = succès

### 🐛 Si ça passe en ❌ rouge

Clique sur la ligne rouge → clique sur **"update-data"** → tu verras les logs. Les erreurs les plus fréquentes :
- **"Network timeout"** : réessaie (bouton "Re-run all jobs" en haut à droite)
- **"No module named X"** : le fichier `requirements.txt` n'est pas bien remonté, réupload-le

---

## Étape 6 — Activer GitHub Pages (2 min) ⏱️

C'est ici que le dashboard devient accessible sur le web.

1. Dans ton repo, clique sur l'onglet **"Settings"** (tout à droite en haut)
2. Dans la barre latérale gauche, scroll et clique sur **"Pages"**
3. Sous **"Source"**, choisis **"Deploy from a branch"**
4. Deux menus déroulants apparaissent :
   - **Branch** : choisis `main`
   - **Folder** : laisse `/ (root)`
5. Clique **"Save"**
6. **Attends 1-2 minutes**, puis recharge la page

En haut, tu verras apparaître :

> 🎉 **Your site is live at https://TON_USERNAME.github.io/insider-pea/**

(remplace TON_USERNAME par ton vrai pseudo GitHub)

---

## ✅ C'est fini !

1. Ouvre cette URL dans ton navigateur
2. **Ajoute-la à tes favoris**
3. À partir de maintenant :
   - 🤖 Les données se mettent à jour **automatiquement** chaque jour à 19h
   - 📊 Ton dashboard affiche toujours les dernières données
   - 💰 Tu ne paies **rien**, jamais

---

## 🎛️ Utilisation quotidienne

### Consulter le dashboard
Ouvre simplement ton URL favorite. Ça charge en 2 secondes.

### Ajouter une entreprise à suivre
1. Va sur ton repo GitHub
2. Ouvre `run.py`
3. Clique sur le crayon ✏️ en haut à droite
4. Dans la liste `TARGETS`, ajoute une ligne comme les autres :
   ```python
   {"isin": "FR0000045072", "name": "Crédit Agricole", "ticker": "ACA.PA", "country": "FR", "sector": "Finance"},
   ```
   - **ISIN** : code à 12 caractères trouvable sur https://live.euronext.com
   - **Ticker Yahoo** : format pour les actions françaises = `NOM.PA` (trouvable sur https://finance.yahoo.com)
5. Clique **"Commit changes..."** en haut à droite
6. La modification sera prise en compte dès le prochain run (le lendemain 19h)

### Forcer une mise à jour maintenant
Onglet Actions → **"Run workflow"** (comme à l'étape 5)

---

## 🆘 Problèmes fréquents

| Problème | Solution |
|----------|----------|
| Le dashboard affiche "Fichier introuvable" | Le workflow n'a pas encore tourné → fais l'étape 5 |
| Le dashboard affiche 0 recommandations | C'est peut-être une période calme (vacances, été). Les déclarations AMF arrivent par vagues. Regarde les 🟡 "Intéressant" aussi. |
| Le workflow échoue en rouge | Relance-le (parfois lestransactions.fr est down 5 min). Si ça persiste, regarde les logs. |
| L'URL donne un 404 | GitHub Pages prend parfois 5-10 min à s'activer la première fois. Attends. |
| J'ai modifié un fichier et rien ne change | Les modifications de `index.html` sont actives immédiatement. Les modifications de `run.py` ne prennent effet qu'au prochain run du workflow. |

---

## 🎯 Ce que tu as maintenant

- ✅ **Un vrai outil de suivi d'initiés** sur les actions PEA françaises
- ✅ **Des données réelles** (AMF + Yahoo Finance), pas simulées
- ✅ **Mise à jour quotidienne automatique** (du lundi au vendredi à 19h)
- ✅ **Accessible depuis n'importe où** via ton URL GitHub Pages
- ✅ **Zéro coût, zéro maintenance**
- ✅ **Ton code t'appartient** : tu peux le modifier, l'améliorer, l'étendre quand tu veux

**Comparaison avec InsiderScreener Plus à 14€/mois** : tu as gratuitement l'essentiel (suivi, screener, données AMF). Il te manque les alertes email temps réel — mais le scraping quotidien à 19h est largement suffisant pour un PEA (pas de day trading).

---

## 📧 Ajouter des alertes email plus tard ?

C'est possible et gratuit via GitHub Actions. Ouvre une issue ou demande-moi de l'aide quand tu voudras cette fonctionnalité.
