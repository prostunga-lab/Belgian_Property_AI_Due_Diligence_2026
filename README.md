# Belgian Property Due Diligence (MVP)

SaaS construit à partir de `docs/strategy.md` (§9 « MVP recommandé »): **Flandre, 4 documents** – EPC, acte, asbestattest, contrôle électrique.

## Ce que fait le MVP
- Comptes / organisations (multi-tenant strict), quota de dossiers par mois.
- Upload de dossiers (PDF/TXT), classification automatique (NL/FR/EN), correction manuelle du type.
- Extraction de champs clés, chacun avec **page + extrait source**. Passe LLM optionnelle (`ANTHROPIC_API_KEY`) qui ne comble que les champs manquants et n'est acceptée que si l'extrait cité figure mot pour mot dans la page.
- 14 règles versionnées (`app/rules.py`, `VL-2026.1`): complétude, validité EPC, cohérence label/score, asbeste, électricité, adresses/surfaces/bouwjaar contradictoires entre documents, extension sans permis, infos urbanistiques, chronologie.
- Property Risk Score global + 6 domaines (Legal / Urbanistic / Energy / Technical / Environmental / Documentation).
- Chaque finding distingue **fait / inférence IA / risque / action**; validation humaine (confirmer/rejeter), commentaires, audit log.
- Rapport PDF exportable avec sources, règles utilisées, questions par partie (notaire/vendeur), disclaimer.
- Rétention configurable (`python -m app.purge`).

## Lancer
```
pip install -r requirements.txt
SECRET_KEY=... uvicorn app.main:app --reload     # http://localhost:8000
pytest
```
Variables: `DATA_DIR`, `DATABASE_URL`, `SECRET_KEY`, `ANTHROPIC_API_KEY`, `LLM_MODEL`, `RETENTION_DAYS`, `MAX_UPLOAD_MB`.

## Limites connues / prochaines étapes
- Pas d'OCR : les PDF scannés sont signalés « non lisibles » (ajouter Tesseract/Textract).
- Les règles réglementaires (durées de validité, seuils) sont des **points de départ à faire valider par un juriste/notaire** avant mise en production.
- À faire: Postgres + migrations (Alembic), stockage objet chiffré, paiement (Stripe), export Word, plans/urbanisme/copropriété, Bruxelles/Wallonie, API publique, file de tâches pour l'analyse asynchrone, protection CSRF dédiée, rate limiting.
