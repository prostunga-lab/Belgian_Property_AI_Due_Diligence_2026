# Déploiement avec données persistantes

## Architecture
- **PostgreSQL** (géré) : comptes, dossiers, findings, commentaires, journal d'audit. Schéma géré par **Alembic** (`migrations/`), appliqué automatiquement au démarrage (`AUTO_MIGRATE=1`).
- **Disque persistant** monté sur `/data` : fichiers uploadés, **chiffrés au repos** (Fernet) avec `FILE_ENCRYPTION_KEY`.
- **Région UE** (Francfort) pour la résidence des données.

## Mise en ligne sur Render
1. Fusionner la PR dans `main`.
2. Render → **New → Blueprint** → choisir le dépôt → *Apply* (lit `render.yaml`).
3. Dans le tableau de bord du service, ouvrir **Environment** et **copier `FILE_ENCRYPTION_KEY` et `INVITE_CODE`** dans un gestionnaire de mots de passe.
   Sans `FILE_ENCRYPTION_KEY`, les fichiers déjà uploadés sont **irrécupérables**.
4. Ouvrir l'URL, s'inscrire avec `INVITE_CODE`.

`APP_ENV=production` fait refuser le démarrage si `SECRET_KEY`, `FILE_ENCRYPTION_KEY`, `INVITE_CODE` ou `COOKIE_SECURE=1` manquent.

## Variables d'environnement
| Variable | Rôle |
|---|---|
| `DATABASE_URL` | PostgreSQL (`postgres://` accepté) ; SQLite par défaut en dev |
| `DATA_DIR` | dossier des fichiers uploadés (disque persistant) |
| `SECRET_KEY` | signature des cookies de session |
| `FILE_ENCRYPTION_KEY` | chiffrement des fichiers (n'importe quelle phrase secrète longue) |
| `INVITE_CODE` | code requis pour créer un compte (inscription fermée) |
| `COOKIE_SECURE=1` | cookies HTTPS uniquement |
| `RETENTION_DAYS` | durée de conservation avant `python -m app.purge` |
| `ANTHROPIC_API_KEY` | optionnel, extraction LLM |

## E-mail, crédits, Stripe, API
- **E-mail** : renseigner `SMTP_HOST` (+ `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`). Sans `SMTP_HOST` les liens sont seulement écrits dans les logs, la confirmation d'e-mail n'est **pas** exigée et « mot de passe oublié » ne peut pas fonctionner. Prévoir SPF/DKIM/DMARC sur le domaine d'envoi.
- **Crédits** : 1 crédit = 1 document, débité au premier « Analyser » (re-analyse gratuite). `FREE_CREDITS` offerts à l'inscription, `PACK_CREDITS` par achat. Le débit est atomique et annulé si l'analyse échoue.
- **Stripe** : créer un produit « Pack de crédits » (paiement unique) → `STRIPE_PRICE_ID` ; webhook `https://<votre-url>/billing/webhook` sur `checkout.session.completed` et `checkout.session.async_payment_succeeded` → `STRIPE_WEBHOOK_SECRET`. Test local : `stripe listen --forward-to localhost:8000/billing/webhook`. Le webhook est idempotent.
- **API** : page *Compte → Clés API*, puis `curl -H "X-API-Key: sk_live_…" -F "files=@epc.pdf" -F "files=@akte.pdf" <url>/v1/dossier` (JSON), `GET /v1/cases/{id}`, `GET /v1/cases/{id}/report.pdf`. Documentation interactive : `/docs`.
- **IA (facultatif)** : avec `ANTHROPIC_API_KEY`, chaque document reçoit une « lecture IA » et le dossier une synthèse croisée. Indicatif, jamais intégré au score ; l'app fonctionne entièrement sans.

## Sauvegardes
- **Base** : activer/vérifier les sauvegardes automatiques du Postgres géré (plans payants) et tester une restauration.
- **Fichiers** : vérifier les snapshots du disque ; en complément, copier régulièrement `/data` ailleurs.
- **Clés** : sauvegarder `FILE_ENCRYPTION_KEY` séparément. Base + fichiers sans la clé = fichiers illisibles.

## Rétention / RGPD
- Bouton « Dossier wissen » : supprime le dossier, ses documents et les fichiers du disque.
- `python -m app.purge` (à planifier, ex. cron Render) supprime les dossiers plus vieux que `RETENTION_DAYS`.
- Le texte extrait des documents est stocké en base (chiffrement au repos fourni par l'hébergeur, pas au niveau applicatif).

## Migrations
```
alembic upgrade head                                   # appliquer (automatique au démarrage)
alembic revision --autogenerate -m "description"       # après modification de app/models.py
```
(lancer avec `PYTHONPATH=.`)

## Limites connues avant de traiter de vrais dossiers clients
- Pas de 2FA ni de rôles/multi-utilisateurs au sein d'une organisation.
- Limitation des tentatives de connexion en mémoire (une seule instance).
- Pas de traitement asynchrone : l'analyse/OCR tourne dans la requête (documents volumineux = lent).
- Aucune validation juridique des règles : voir README.
- Contrat de traitement des données (DPA) avec l'hébergeur et avis du DPO/juriste à prévoir.
