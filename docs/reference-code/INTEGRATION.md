# Code de référence fourni (autre implémentation)

Ces fichiers (`main.py`, `security.py`, `db.py`, `ai.py`, `mail.py`, `index.html`, README, Dockerfile…) viennent d'une première
implémentation « Analyse immobilière BE ». Ils sont conservés ici **à titre de référence uniquement** (non exécutés).
Leurs fonctions ont été intégrées dans l'application principale :

| Référence | Application (`app/`) | Remarques |
|---|---|---|
| inscription, confirmation e-mail, mot de passe oublié | `main.py`, `auth.py`, `mail.py` | jetons `itsdangerous` (au lieu de JWT), session liée à l'empreinte du mot de passe |
| clés API (`sk_live_…`) | `auth.py`, `api_v1.py`, `/account` | hash SHA-256, clé affichée une seule fois |
| crédits (1/document) | `services.py` | au niveau **organisation** ; débit conditionnel atomique, annulé si l'analyse échoue |
| Stripe Checkout + webhook | `billing.py` | paiement + crédit dans **une** transaction ; webhook lu en JSON brut (voir ci-dessous) |
| prompts PEB / électrique / cadastre / sol / croisé | `prompts.py`, `llm.py` | lecture IA **indicative**, hors score |
| types cadastre et sol | `classify.py`, `extract.py`, `rules.py` | extraction et règles déterministes, sources page/extrait |
| effacement RGPD (`DELETE /me`) | `/account/delete` | supprime l'organisation, ses dossiers/fichiers/clés ; paiements conservés |

## Défauts relevés dans le code de référence (corrigés dans l'intégration)
1. **Webhook Stripe** : `s.get(...)` sur un `StripeObject` plante avec les versions récentes de la bibliothèque → les paiements ne créditaient jamais. Désormais : signature vérifiée par Stripe, puis lecture du JSON brut.
2. **Paiement non atomique** : `Payment` puis crédit dans deux transactions séparées ; un échec entre les deux faisait perdre le crédit. Désormais une seule transaction.
3. **Crédits perdus en cas de crash** entre le débit et le remboursement. Désormais le débit est dans la transaction de l'analyse (rollback = crédits restitués).
4. **Sessions non révocables** (JWT 7 jours) : changer/réinitialiser le mot de passe ne déconnectait personne. Désormais la session est liée à l'empreinte du mot de passe.
5. **Pas de limitation sur l'inscription** ni sur la création de clés ; pas de contrôle d'origine (CSRF) ; pas d'en-têtes de sécurité.
6. `SECRET_KEY` absente → `KeyError` au démarrage sans message clair ; migrations absentes (`create_all` seul).
7. Texte du document injecté tel quel dans le prompt : désormais encadré par `<document>` et déclaré comme donnée.
