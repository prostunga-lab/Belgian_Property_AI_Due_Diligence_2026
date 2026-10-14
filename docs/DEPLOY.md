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

## Dépannage : « Code d'invitation invalide »
1. **Railway applique les variables au prochain déploiement.** Après avoir modifié `INVITE_CODE`, cliquez sur le bandeau **Deploy** (ou *Apply changes*) et attendez la fin du déploiement.
2. **Copiez le code depuis Railway, pas depuis le générateur** : la page `generer-secrets.html` produit de **nouvelles** valeurs à chaque clic sur *Générer*. Dans *Variables*, cliquez sur l'œil de `INVITE_CODE` pour voir la valeur réellement en place.
3. Les espaces et guillemets autour du code (copier-coller) sont ignorés par l'application, des deux côtés.
4. **Lire les logs** (*Deployments → View logs*) : chaque refus écrit `invite code mismatch (submitted X chars, configured Y chars)` sans révéler le code. `configured` ≠ longueur attendue = la valeur Railway n'est pas celle que vous croyez ; `submitted` ≠ `configured` = ce qui a été saisi diffère.
5. En dernier recours, définissez vous-même un nouveau `INVITE_CODE` (toute phrase de 12 caractères ou plus), redéployez, et utilisez celui-là.

## Pages publiques : accueil, À propos, Contact
- `/` (visiteurs non connectés), `/about` et `/contact` sont publiques, en FR/NL/EN, avec un pied de page présent sur toutes les pages.
- **Coordonnées de l'éditeur : à renseigner, jamais inventées.** Variables : `CONTACT_EMAIL`, `COMPANY_NAME`, `COMPANY_ADDRESS`, `COMPANY_ENTERPRISE_NUMBER` (BCE/TVA), `COMPANY_PHONE`. Seuls les champs définis sont affichés ; sans `CONTACT_EMAIL`, la page Contact indique que les coordonnées seront publiées prochainement.
- Pas de formulaire de contact volontairement : sans serveur d'e-mail configuré, un message pourrait se perdre en silence. La page propose un lien `mailto:` (adresse validée strictement). Un formulaire pourra être ajouté une fois `SMTP_HOST` en place.
- ⚠️ **À faire valider par un juriste** : en Belgique, un site proposant un service en ligne doit en principe permettre d'identifier son prestataire (dénomination, adresse géographique, e-mail, numéro d'entreprise/TVA). Renseignez ces variables avant d'ouvrir le site au public. Des mentions légales, une politique de confidentialité et des CGV restent à rédiger.

## Langues
- Interface, messages d'erreur, e-mails et rapport PDF existent en **français, néerlandais et anglais**.
- Ordre de choix : lien FR/NL/EN (cookie, mémorisé sur le compte) > `Accept-Language` du navigateur > français. L'API répond en anglais par défaut ou selon `Accept-Language` / `?lang=`.
- Les constats sont stockés **sans texte** (identifiant de règle + paramètres) et rendus dans la langue du lecteur : le même dossier se lit et s'exporte en PDF dans les trois langues (`/cases/{id}/report.pdf?lang=nl`).
- Ajouter une langue : créer `app/i18n/<code>.py` (mêmes clés que `en.py`), l'ajouter à `LANGS`/`CATALOGS` ; `tests/test_i18n.py` vérifie qu'aucune clé ni aucun paramètre ne manque.
- La lecture IA (facultative) est rédigée dans la langue de la personne au moment de l'analyse.

## E-mail, crédits, Stripe, API
- **E-mail** : **sur Railway (essai, Free, Hobby) le SMTP sortant est bloqué** : utiliser une API d'e-mail en HTTPS. Définir `RESEND_API_KEY` (compte Resend) et `MAIL_FROM` ; avec l'expéditeur de test `onboarding@resend.dev`, Resend n'envoie qu'à l'adresse du compte (suffisant pour recevoir les demandes d'accès : mettre cette adresse dans `CONTACT_EMAIL`) ; pour écrire à vos clients (confirmation d'e-mail, mot de passe oublié), vérifier un domaine chez Resend et utiliser une adresse de ce domaine dans `MAIL_FROM`. Autre option : `SMTP_HOST` (+ `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`) sur un hébergement qui autorise le SMTP (plan Pro de Railway ou autre). Sans aucun des deux, les liens sont seulement écrits dans les logs, la confirmation d'e-mail n'est **pas** exigée et « mot de passe oublié » ne peut pas fonctionner. `/health` indique le transport (`mail`: `resend`, `smtp` ou `log`) ; chaque envoi écrit une ligne `[MAIL]` dans les logs (réussite ou raison du refus). Prévoir SPF/DKIM/DMARC sur le domaine d'envoi.
- **Tarification** : l'unité est le **dossier complet analysé** (plusieurs documents, 25 maximum par défaut : `DOSSIER_MAX_DOCUMENTS`). Investisseur : paiement au dossier (29 €) ou pack de 5 (75 €). Agent : 49 €/mois, 15 dossiers. Agence : 149 €/mois, 60 dossiers. Abonnements payables au mois, au semestre (−5 %) ou à l'an (−10 %). Quota d'abonnement renouvelé chaque mois à la date anniversaire, non reportable ; l'abonnement épuisé ou absent bascule sur les crédits. Prix et remises modifiables par `PLAN_<ID>_PRICE_EUR`, `PLAN_<ID>_DOSSIERS`, `DISCOUNT_SEMIANNUAL_PCT`, `DISCOUNT_ANNUAL_PCT` ; `FREE_CREDITS` (1) offert à l'inscription ; débit atomique, ré-analyse gratuite.
- **Stripe** : aucun produit à créer (prix transmis à la volée, identiques à la page Tarifs). `STRIPE_SECRET_KEY` + webhook `https://<votre-domaine>/billing/webhook` sur `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted` → `STRIPE_WEBHOOK_SECRET`. Webhook idempotent. Activer le **portail client** Stripe pour la résiliation et le changement de carte. Non testé contre le vrai Stripe : essayer en mode test avant la mise en production.
- **Inscription ouverte** : sans `INVITE_CODE`, activer `OPEN_REGISTRATION=1` (le code d'invitation, s'il est défini, reste prioritaire). Limite par adresse IP et par jour : `REGISTRATIONS_PER_IP_PER_DAY` (5). **Captcha anti-robot (recommandé avant l'ouverture au public)** : créer un widget gratuit Cloudflare Turnstile (dash.cloudflare.com → Turnstile → Add widget, domaine du site, mode « Managed »), puis définir `TURNSTILE_SITE_KEY` (clé publique) et `TURNSTILE_SECRET_KEY` (clé secrète) ; sans les deux, le captcha est désactivé. Si Cloudflare est injoignable, l'inscription est refusée (le captcha échoue en mode fermé). Configurer un transport d'e-mail (Resend) pour que la vérification d'adresse soit exigée.
- **Essai gratuit** : `TRIAL_DAYS` (3) et `TRIAL_DOSSIERS` (3) pour les abonnements, une fois par organisation, carte demandée au départ. Guide complet des paiements : `docs/STRIPE.md`.
- **Promesse de délai** : `PROCESSING_PROMISE_MINUTES` (2) est affichée sur l'accueil, les tarifs et les conditions ; la durée réelle de chaque analyse est enregistrée et affichée ; `tests/test_promise.py` vérifie un dossier complet (dont un scan).
- **Pages légales** : `/legal`, `/privacy`, `/terms` (projets à faire valider par un juriste ; bandeau affiché jusqu'à `LEGAL_REVIEWED=1`). Renseigner `COMPANY_NAME`, `COMPANY_ADDRESS`, `COMPANY_ENTERPRISE_NUMBER`, `CONTACT_EMAIL`, `COMPANY_PHONE`, `HOSTING_PROVIDER`, `HOSTING_REGION` ; les valeurs manquantes sont signalées « à compléter ». L'inscription exige l'acceptation des conditions (date et version enregistrées).
- **API** : *Compte → Clés API*, puis `curl -H "X-API-Key: sk_live_…" -F "files=@epc.pdf" -F "files=@akte.pdf" <url>/v1/dossier`. Documentation interactive : `/docs`.
- **IA (facultatif)** : `ANTHROPIC_API_KEY` active la lecture IA et le remplissage des champs manquants ; indicative, jamais intégrée au score.

- **Demandes d'accès** : le formulaire de `/contact` enregistre les demandes ; elles sont envoyées à `CONTACT_EMAIL` (si `SMTP_HOST` est configuré) et lisibles par les comptes listés dans `ADMIN_EMAILS` (adresses séparées par des virgules) sur `/admin/requests`.
- **Sécurité HTTP** : en-têtes de sécurité sur toutes les réponses et CSP stricte. `CSP_MODE=report-only` pour observer sans bloquer, `off` pour désactiver (déconseillé).
- **Règles** : `RULES_VALIDATED=1` supprime le bandeau « règles en cours de validation » (à ne faire qu'après validation documentée, voir `docs/REGLES.md`).
- **Avant de lancer** : `docs/CHECKLIST-LANCEMENT.md` (état de chaque constat de la revue et ce qui reste).

## Variables d'environnement (récapitulatif)
`DATABASE_URL`, `DATA_DIR`, `SECRET_KEY`, `FILE_ENCRYPTION_KEY`, `INVITE_CODE`, `COOKIE_SECURE`, `APP_ENV`, `BASE_URL`, `FREE_CREDITS`, `DOSSIER_MAX_DOCUMENTS`, `PRICES_VAT`, `PLAN_*`, `DISCOUNT_*`, `PROCESSING_PROMISE_MINUTES`, `HOSTING_*`, `LEGAL_REVIEWED`, `RULES_VALIDATED`, `CSP_MODE`, `ADMIN_EMAILS`, `OPEN_REGISTRATION`, `TRIAL_DAYS`, `TRIAL_DOSSIERS`, `REGISTRATIONS_PER_IP_PER_DAY`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `RESEND_API_KEY`, `COMPANY_*`, `CONTACT_EMAIL`, `STRIPE_*`, `SMTP_*`, `MAIL_FROM`, `ANTHROPIC_API_KEY`, `LLM_MODEL`, `RETENTION_DAYS`, `OCR_ENABLED`, `OCR_LANGS`, `OCR_DPI`, `MAX_UPLOAD_MB`, `MAX_FILES_PER_REQUEST`. Voir `.env.example`.

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
