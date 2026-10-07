# SaaS d'analyse immobilière (PEB, conformité électrique, cadastre, attestation du sol)

FastAPI + interface web intégrée : OCR des scans, classification, extraction JSON par l'IA, synthèse croisée,
comptes, clés API, crédits et paiement Stripe (packs de crédits, paiement unique).

## Lancer (dev)
    cp .env.example .env        # renseigner ANTHROPIC_API_KEY, SECRET_KEY, Stripe
    docker build -t saas-immo . && docker run --env-file .env -p 8000:8000 -v $PWD/data:/app/data saas-immo
Interface : http://localhost:8000 · API : http://localhost:8000/docs
(avec SQLite, mettez DATABASE_URL=sqlite:////app/data/saas.db pour persister; Postgres recommandé en production)

## Stripe
1. Créez un produit « Pack de crédits » (paiement unique) et copiez son `price_...` dans STRIPE_PRICE_ID.
2. Webhook vers `https://votre-domaine/billing/webhook`, événements `checkout.session.completed` et
   `checkout.session.async_payment_succeeded`; copiez le secret dans STRIPE_WEBHOOK_SECRET.
3. En local : `stripe listen --forward-to localhost:8000/billing/webhook`.

## API
    curl -H "X-API-Key: sk_live_..." -F "files=@peb.pdf" -F "files=@elec.pdf" localhost:8000/v1/dossier

## Fonctionnement des crédits
1 crédit = 1 document. Débit atomique avant analyse, remboursement automatique en cas d'échec ou de document non pris en charge.

## Avant la production
- Migrations de base (Alembic): la colonne `users.verified` est nouvelle, en dev supprimez saas.db
- Limiteur de tentatives en mémoire (1 processus): Redis si plusieurs instances; limitation globale des requêtes non incluse
- Expéditeur e-mail: SPF/DKIM/DMARC sur votre domaine, sinon les messages finissent en spam
- File de tâches pour l'OCR (aujourd'hui synchrone), HTTPS + COOKIE_SECURE=1, hébergement UE
- TVA et facture (Stripe Tax / Stripe Invoicing), CGV, politique de confidentialité, mention « aide à la lecture »
- Tests sur de vrais documents (NL, scans de mauvaise qualité) et tests automatisés des flux crédits/webhook

## E-mails
Inscription: lien de confirmation (48 h). Les analyses exigent une adresse confirmée. Mot de passe oublié: lien de 1 h, à usage unique.
Renseignez SMTP_* dans .env; sans cela, les liens s'affichent dans la console du serveur.

## Tests
    pip install -r requirements-dev.txt
    pytest -q                      # tests rapides, sans réseau ni clé API (OCR et IA simulés)
    RUN_LIVE=1 ANTHROPIC_API_KEY=sk-ant-... pytest -m live -v   # qualité réelle de l'IA (quelques appels payants)

- `test_security.py`, `test_ocr.py`, `test_ai_parsing.py`: jetons, mots de passe, logique OCR, extraction JSON, classification, prompts.
- `test_api_flow.py`: inscription, confirmation d'e-mail, crédits et remboursements, clés API, mot de passe oublié à usage unique, webhook Stripe idempotent, isolation entre utilisateurs, suppression de compte.
- `test_live_accuracy.py`: documents fictifs dans `tests/fixtures` (PEB, électrique, cadastre, sol, facture, document incomplet, tentative d'injection). Pour ajouter un cas: `<nom>.txt` + `<nom>.expected.json`.
  Ajoutez ensuite des documents réels anonymisés (jamais de données personnelles dans le dépôt).
