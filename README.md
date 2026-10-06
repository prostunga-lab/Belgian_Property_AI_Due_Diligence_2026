# Belgian Property Due Diligence (MVP)

SaaS construit à partir de `docs/strategy.md` (§9 « MVP recommandé »): **Flandre, 4 documents** – EPC, acte, asbestattest, contrôle électrique.

## Ce que fait le MVP
- Comptes / organisations (multi-tenant strict), quota de dossiers par mois.
- Upload de dossiers (PDF, TXT, images PNG/JPG/TIFF), classification automatique (NL/FR/EN), correction manuelle du type.
- **OCR** (Tesseract, NL+FR+EN): les pages sans texte et les images sont lues par OCR, avec score de confiance par page; un scan de mauvaise qualité (< 75 %) ou sans OCR disponible génère un finding « documentation ». Correction automatique de « m² » lu « m? ».
- Extraction de champs clés, chacun avec **page + extrait source**. Passe LLM optionnelle (`ANTHROPIC_API_KEY`) qui ne comble que les champs manquants et n'est acceptée que si l'extrait cité figure mot pour mot dans la page.
- 14 règles versionnées (`app/rules.py`, `VL-2026.1`): complétude, validité EPC, cohérence label/score, asbeste, électricité, adresses/surfaces/bouwjaar contradictoires entre documents, extension sans permis, infos urbanistiques, chronologie.
- Property Risk Score global + 6 domaines (Legal / Urbanistic / Energy / Technical / Environmental / Documentation).
- Chaque finding distingue **fait / inférence IA / risque / action**; validation humaine (confirmer/rejeter), commentaires, audit log.
- Rapport PDF exportable avec sources, règles utilisées, questions par partie (notaire/vendeur), disclaimer.
- Rétention configurable (`python -m app.purge`).

## Déploiement avec données persistantes
Voir [`docs/DEPLOY.md`](docs/DEPLOY.md) : PostgreSQL + disque persistant chiffré, migrations Alembic, inscription sur invitation, protection cross-site, limitation des connexions, suppression RGPD, `render.yaml`.

## Lancer
```
pip install -r requirements.txt
SECRET_KEY=... uvicorn app.main:app --reload     # http://localhost:8000
pytest
```
OCR: nécessite `tesseract-ocr` (langues nld, fra, eng) et `poppler-utils` (`pdftoppm`); le Dockerfile les installe. Sans eux l'app fonctionne, mais les scans sont signalés « non lisibles ».
Variables OCR: `OCR_ENABLED`, `OCR_LANGS`, `OCR_DPI`, `OCR_MIN_CHARS`, `OCR_TIMEOUT_S`.

Variables: `DATA_DIR`, `DATABASE_URL`, `SECRET_KEY`, `ANTHROPIC_API_KEY`, `LLM_MODEL`, `RETENTION_DAYS`, `MAX_UPLOAD_MB`.

## Limites connues / prochaines étapes
- OCR Tesseract testé sur scans synthétiques seulement : à valider sur de vrais scans (photos, manuscrits, tampons). Le schéma SQLite a changé (`ocr_pages`, `warnings`) : pas de migration encore, recréer la base de dev.
- Les règles réglementaires (durées de validité, seuils) sont des **points de départ à faire valider par un juriste/notaire** avant mise en production.
- À faire: paiement (Stripe), export Word, plans/urbanisme/copropriété, Bruxelles/Wallonie, API publique, file de tâches pour l'analyse asynchrone, réinitialisation de mot de passe/2FA, rôles par organisation, traitement asynchrone.
