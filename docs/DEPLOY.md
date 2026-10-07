# Déploiement sur Railway (données persistantes)

## Architecture
- **Service web** : l'image Docker du dépôt (`Dockerfile`, `railway.toml`). Tesseract (OCR nl/fr/en) y est installé.
- **PostgreSQL** (plugin Railway) : comptes, dossiers, findings, commentaires, crédits, journal d'audit. Schéma géré par **Alembic** (`migrations/`), appliqué automatiquement au démarrage.
- **Volume Railway monté sur `/data`** : fichiers uploadés, **chiffrés au repos** (Fernet) avec `FILE_ENCRYPTION_KEY`.

## Mise en ligne, pas à pas
1. **Fusionner** la PR dans `main` (Railway déploie la branche qu'on lui indique).
2. Sur [railway.com](https://railway.com) : **New Project → Deploy from GitHub repo** → `Belgian_Property_AI_Due_Diligence_2026`.
3. **Ajouter la base** : dans le projet, **+ New → Database → Add PostgreSQL**.
4. **Ajouter le volume** : ouvrir le service web → **Settings → Volumes → New Volume**, *mount path* = `/data`.
   Sans volume, les fichiers uploadés sont perdus à chaque redéploiement.
5. **Variables** (service web → *Variables*). Les valeurs secrètes (`SECRET_KEY`, `FILE_ENCRYPTION_KEY`, `INVITE_CODE`) se génèrent **vous-même** : ouvrez [`docs/generer-secrets.html`](generer-secrets.html) dans votre navigateur (hors ligne, rien n'est envoyé) ou lancez `python -m app.gen_secrets`, puis collez le résultat dans *Variables → Raw Editor*.
   Récapitulatif :

   | Variable | Valeur |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (référence vers le plugin ; adapter « Postgres » au nom du service) |
   | `APP_ENV` | `production` |
   | `SECRET_KEY` | chaîne aléatoire longue (`openssl rand -hex 32`) |
   | `FILE_ENCRYPTION_KEY` | chaîne aléatoire longue — **à sauvegarder** (voir plus bas) |
   | `INVITE_CODE` | code à donner uniquement aux personnes autorisées à s'inscrire |
   | `COOKIE_SECURE` | `1` |
   | `DATA_DIR` | `/data` (déjà défini dans l'image) |

   En `APP_ENV=production`, l'application **refuse de démarrer** si `SECRET_KEY`, `FILE_ENCRYPTION_KEY`, `INVITE_CODE` ou `COOKIE_SECURE=1` manquent : c'est voulu (le déploiement échoue plutôt que de tourner sans protection).
6. **Domaine public** : service web → **Settings → Networking → Generate Domain**. Les liens envoyés par e-mail et les redirections Stripe utilisent automatiquement ce domaine (`RAILWAY_PUBLIC_DOMAIN`) ; pour un domaine personnalisé, définir `BASE_URL=https://votre-domaine`.
7. Ouvrir l'adresse, **choisir la langue (FR / NL / EN)** en haut à droite et s'inscrire avec l'`INVITE_CODE`.

Le contrôle de santé est `GET /health` (vérifie aussi la base). Un premier build prend plusieurs minutes (installation de Tesseract).

## Langues
- Interface, messages d'erreur, e-mails et rapport PDF existent en **français, néerlandais et anglais**.
- Ordre de choix : lien FR/NL/EN (cookie, mémorisé sur le compte) > `Accept-Language` du navigateur > français. L'API répond en anglais par défaut ou selon `Accept-Language` / `?lang=`.
- Les constats sont stockés **sans texte** (identifiant de règle + paramètres) et rendus dans la langue du lecteur : le même dossier se lit et s'exporte en PDF dans les trois langues (`/cases/{id}/report.pdf?lang=nl`).
- Ajouter une langue : créer `app/i18n/<code>.py` (mêmes clés que `en.py`), l'ajouter à `LANGS`/`CATALOGS` ; `tests/test_i18n.py` vérifie qu'aucune clé ni aucun paramètre ne manque.
- La lecture IA (facultative) est rédigée dans la langue de la personne au moment de l'analyse.

## E-mail, crédits, Stripe, API
- **E-mail** : `SMTP_HOST` (+ `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`). Sans `SMTP_HOST` les liens sont seulement écrits dans les logs, la confirmation d'e-mail n'est **pas** exigée et « mot de passe oublié » ne peut pas fonctionner. Prévoir SPF/DKIM/DMARC sur le domaine d'envoi.
- **Crédits** : 1 crédit = 1 document, débité au premier « Analyser » (ré-analyse gratuite). `FREE_CREDITS` (6) offerts à l'inscription, `PACK_CREDITS` (20) par achat. Débit atomique, annulé si l'analyse échoue.
- **Stripe** : produit « Pack de crédits » (paiement unique) → `STRIPE_PRICE_ID` + `STRIPE_SECRET_KEY` ; webhook `https://<votre-domaine>/billing/webhook` sur `checkout.session.completed` et `checkout.session.async_payment_succeeded` → `STRIPE_WEBHOOK_SECRET`. Le webhook est idempotent.
- **API** : *Compte → Clés API*, puis `curl -H "X-API-Key: sk_live_…" -F "files=@epc.pdf" -F "files=@akte.pdf" <url>/v1/dossier`. Documentation interactive : `/docs`.
- **IA (facultatif)** : `ANTHROPIC_API_KEY` active la lecture IA et le remplissage des champs manquants ; indicative, jamais intégrée au score.

## Variables d'environnement (récapitulatif)
`DATABASE_URL`, `DATA_DIR`, `SECRET_KEY`, `FILE_ENCRYPTION_KEY`, `INVITE_CODE`, `COOKIE_SECURE`, `APP_ENV`, `BASE_URL`, `FREE_CREDITS`, `PACK_CREDITS`, `STRIPE_*`, `SMTP_*`, `MAIL_FROM`, `ANTHROPIC_API_KEY`, `LLM_MODEL`, `RETENTION_DAYS`, `OCR_ENABLED`, `OCR_LANGS`, `OCR_DPI`, `MAX_UPLOAD_MB`, `MAX_FILES_PER_REQUEST`. Voir `.env.example`.

## Sauvegardes
- **Base** : activer les sauvegardes du plugin PostgreSQL de Railway et **tester une restauration**.
- **Fichiers** : activer les sauvegardes du volume ; en complément, copier régulièrement `/data` ailleurs.
- **Clé de chiffrement** : sauvegarder `FILE_ENCRYPTION_KEY` dans un gestionnaire de mots de passe, **séparément**. Base + fichiers sans la clé = fichiers illisibles.

## Rétention / RGPD
- « Supprimer le dossier » efface le dossier, ses documents et les fichiers ; « Supprimer mon compte » efface l'organisation entière (les paiements sont conservés pour la comptabilité).
- `python -m app.purge` (à planifier, ex. cron Railway) supprime les dossiers plus vieux que `RETENTION_DAYS`.
- Le texte extrait des documents est stocké en base (chiffrement au repos fourni par l'hébergeur, pas au niveau applicatif).

## Migrations
```
alembic upgrade head                                   # appliquer (automatique au démarrage)
alembic revision --autogenerate -m "description"       # après modification de app/models.py
```
(lancer avec `PYTHONPATH=.`). Vérifier qu'une migration autogénérée est valable sur **PostgreSQL** (ex. défauts booléens : `sa.false()`, pas `0`).

## Limites connues avant de traiter de vrais dossiers clients
- Pas de 2FA ni de rôles/multi-utilisateurs au sein d'une organisation.
- Limitation des tentatives en mémoire (une seule instance) ; pas de traitement asynchrone (l'analyse/OCR tourne dans la requête).
- Aucune validation juridique des règles : voir README.
- Contrat de traitement des données (DPA) avec l'hébergeur, CGV/TVA et avis du DPO/juriste à prévoir.
