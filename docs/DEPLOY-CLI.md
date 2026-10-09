# Déployer avec le Railway CLI (sans GitHub)

Ce guide permet de mettre le site à jour depuis votre ordinateur, tant que le dépôt GitHub n'est pas accessible.
Le CLI envoie le contenu d'un dossier local à Railway, qui construit l'image avec le `Dockerfile` et `railway.toml`, puis déploie.
Les variables, la base PostgreSQL et le volume `/data` du service ne changent pas.

> Les commandes ci-dessous sont celles du CLI Railway à la date de ce guide. En cas de doute : `railway --help` ou `railway <commande> --help`.

## 0. Ce qu'il vous faut
- Un Mac (ou Linux/Windows) avec un terminal.
- Votre compte Railway (celui du projet **upbeat-mindfulness**).
- Le code : le dernier `saas-source.zip` ou `saas.bundle` envoyé dans la conversation.

## 1. Installer le CLI (une fois)
- Mac avec Homebrew : `brew install railway`
- Ou avec Node.js : `npm i -g @railway/cli`
- Vérification : `railway --version`

## 2. Se connecter (une fois)
```
railway login
```
Le navigateur s'ouvre ; validez. Vérification : `railway whoami`.

## 3. Récupérer le code dans un dossier de travail
Choisissez **une** des deux méthodes.

**A. Depuis le zip**
```
mkdir ~/belgian-property && cd ~/belgian-property
unzip ~/Downloads/saas-source.zip
```

**B. Depuis le bundle git (garde l'historique)**
```
cd ~
git clone ~/Downloads/saas.bundle belgian-property
cd belgian-property
git checkout claude/saas-continuous-instructions-eyeb2q
```

Vérifiez que le dossier contient bien `Dockerfile`, `railway.toml`, `app/`, `migrations/`.
**Ne mettez jamais de fichier `.env` ni de clé dans ce dossier** : les secrets restent dans les variables Railway.

## 4. Relier le dossier au bon service (une fois par dossier)
```
railway link
```
Choisissez, dans l'ordre :
1. le projet **upbeat-mindfulness**
2. l'environnement **production**
3. le service **Belgian_Property_AI_Due_Diligence_2026**

Vérification : `railway status` doit afficher ce projet, cet environnement et ce service.
Le domaine de ce service est `belgianpropertyaiduediligence2026-production.up.railway.app`.
(L'autre déploiement, `belgian-property-dd-production`, est un autre service : ne le reliez pas.)

## 5. Déployer
```
railway up
```
- Le CLI envoie le dossier, Railway construit l'image (quelques minutes la première fois) et démarre le service.
- `railway up --detach` rend la main tout de suite ; suivez ensuite avec `railway logs`.
- Si vous avez plusieurs services : `railway up --service Belgian_Property_AI_Due_Diligence_2026`.

## 6. Vérifier que ça tourne
1. `railway logs` : vous devez lire
   `startup: build=… invite_code=configured (16 chars after normalisation)`, puis `Application startup complete`.
2. Dans le navigateur : `https://belgianpropertyaiduediligence2026-production.up.railway.app/health`
   doit répondre `{"status":"ok", …}`.
   Le champ `build` peut afficher `unknown` : il est rempli par GitHub, pas par le CLI. Ce n'est pas une erreur.
3. Dans Railway, le service doit être **Active**, pas « Crashed ».

## 7. Variables d'environnement
Elles se gèrent dans Railway (onglet **Variables**) ou en ligne de commande :
```
railway variables              # liste (valeurs visibles : ne les partagez pas)
railway variables --set "NOM=valeur"
```
Variables importantes : `APP_ENV=production`, `SECRET_KEY`, `FILE_ENCRYPTION_KEY`, `INVITE_CODE`, `DATABASE_URL` (fournie par le plugin PostgreSQL), `COOKIE_SECURE`.
- **En production, l'application refuse de démarrer** si `SECRET_KEY`, `FILE_ENCRYPTION_KEY` ou `INVITE_CODE` manque. Ne supprimez pas `INVITE_CODE` : remplacez-la.
- **Ne changez jamais `FILE_ENCRYPTION_KEY`** après le premier envoi de fichiers : les fichiers déjà stockés deviendraient illisibles.
- Après une modification de variable, Railway demande de redéployer (bouton **Deploy**) ou `railway redeploy`.

## 8. Cas courants
| Symptôme | Cause probable | Solution |
|---|---|---|
| `railway link` ne montre pas le projet | Mauvais compte Railway | `railway logout` puis `railway login` avec le bon compte |
| Build en échec | Fichier manquant dans le dossier | Vérifier `Dockerfile`, `app/`, `migrations/`, `requirements.txt` |
| Service « Crashed » | Variable obligatoire absente | `railway logs`, lire la dernière ligne `RuntimeError` |
| `/health` répond 502 | Le service n'a pas fini de démarrer | Attendre 1 à 2 minutes, relire `railway logs` |
| Le site montre l'ancienne version | Mauvais service ou domaine | Vérifier `railway status` et le domaine dans Settings → Networking |

## 9. Quand GitHub sera de nouveau accessible
Le service reste connecté au dépôt GitHub. Un `git push` sur la branche surveillée redéploiera depuis GitHub et **écrasera** ce que le CLI a envoyé.
Avant de reprendre le flux GitHub :
1. Vérifiez que le dépôt contient bien tous les changements déployés par le CLI.
2. Seulement ensuite, laissez Railway redéployer depuis GitHub.

## 10. Sauvegardes
Le code : gardez le zip/bundle reçu à chaque version.
Les données : activez les sauvegardes du plugin PostgreSQL dans Railway et testez une restauration (voir `docs/DEPLOY.md`).
