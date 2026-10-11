# Checklist de lancement (suite à la « Revue avant lancement » du 10 octobre 2026)

Statuts : **Corrigé** = changement de code testé ; **À faire (propriétaire)** = information, décision ou validation que seul le propriétaire / le conseil peut apporter ;
**À vérifier en production** = le code est prêt, il faut constater le résultat sur le service déployé.

| ID | Constat | Statut | Ce qui est fait | Ce qui reste |
|---|---|---|---|---|
| F01 | Accès commercial sans contact opérationnel | Corrigé + à vérifier en production | Formulaire « Demander un accès » sur `/contact` (enregistré en base, e-mail au propriétaire, anti-spam, limite par adresse), bouton sur l'accueil et lien sous le champ du code, page `/admin/requests` pour les administrateurs, état « bêta sur invitation » affiché | Renseigner `CONTACT_EMAIL`, `SMTP_*`, `ADMIN_EMAILS` ; envoyer une demande réelle, la recevoir, répondre avec un code (`docs/generer-secrets.html`) |
| F02 | Identité et mentions légales incomplètes | À faire (propriétaire) | Les pages se remplissent d'elles-mêmes à partir des variables ; chaque champ manquant est signalé « à compléter » | Renseigner `COMPANY_NAME`, `COMPANY_ADDRESS`, `COMPANY_ENTERPRISE_NUMBER`, `COMPANY_PHONE`, `HOSTING_PROVIDER`, `HOSTING_REGION` ; relecture par le conseil ; puis `LEGAL_REVIEWED=1` |
| F03 | Traitement des données et IA insuffisamment décrit | À faire (propriétaire) | La politique de confidentialité cite Stripe, l'e-mail et Anthropic **uniquement s'ils sont configurés** et décrit cookies, conservation, droits | Confirmer le flux réel et les engagements de chaque prestataire (lieu de traitement, conservation, réutilisation), compléter les clauses de transfert, signer les contrats de sous-traitance, faire relire |
| F04 | Validation métier des règles non établie | À faire (professionnel) | Registre `docs/REGLES.md` (une ligne par règle : base juridique, date d'effet, exceptions, validation), bandeau « règles en cours de validation » sur la page du dossier, le PDF et la démo, jusqu'à `RULES_VALIDATED=1` | Faire valider chaque règle par le professionnel compétent (périmètre Flandre), compléter le registre, puis `RULES_VALIDATED=1`. Bruxelles et Wallonie restent préliminaires |
| F05 | Conditions commerciales non finalisées | À faire (propriétaire + conseil) | Comportements testés : renouvellement, résiliation, quota mensuel, doubles webhooks, paiements ; les points ouverts apparaissent « à définir » | Décider remboursement, validité des crédits, rétractation, responsabilité ; distinguer particuliers et professionnels ; essai complet de Stripe en mode test avant l'activation |
| F06 | Inscription et essai incohérents | Corrigé | Choix « particulier / professionnel » (nom d'organisation facultatif pour un particulier, obligatoire pour un professionnel) ; la règle d'essai (`FREE_CREDITS`) est affichée partout avec le même texte et appliquée côté serveur | – |
| F07 | Pas de CSP | Corrigé | CSP stricte (`script-src 'self'`, aucun script ni gestionnaire en ligne, `frame-ancestors 'none'`, `object-src 'none'`) ; `CSP_MODE=report-only` pour observer avant d'imposer ; vérifié dans un navigateur réel sans violation | Les styles en ligne restent autorisés (`style-src 'unsafe-inline'`) ; à retirer dans une étape ultérieure. Surveiller la console du navigateur après déploiement |
| F08 | En-têtes incomplets sur les refus inter-sites | Corrigé | Mêmes protections sur toutes les réponses : pages, redirections, 4xx, 5xx, refus précoces, fichiers statiques | – |
| F09 | 404 en JSON brut | Corrigé | Page HTML lisible avec retour à l'accueil pour les visiteurs (et clients sans en-tête `Accept`) ; JSON conservé pour `/v1`, `/docs` et les clients API ; 500 générique sans détail technique | – |
| F10 | Couverture régionale à rendre visible | Corrigé | Mention « optimisé pour la Flandre, Bruxelles et Wallonie préliminaires » près du premier bouton et sur la page Tarifs ; région détectée par code postal, signalée dans chaque rapport | Faire valider les règles bruxelloises avec l'agent partenaire (`docs/PROTOCOLE-TEST-BRUXELLES.md`) |
| F11 | Preuve de valeur et gravité à mieux expliquer | Corrigé | Page `/demo` et PDF de démonstration produits par le vrai moteur sur des documents de démonstration ; chaque constat indique sa nature (fait, inférence, risque, action) avec une phrase d'explication, et la gravité est définie comme un impact potentiel | Un exemple réel anonymisé validé par l'agent partenaire remplacerait avantageusement la démonstration |

## Plan de validation authentifié (page 7 de la revue)
Tests automatisés ajoutés (`tests/test_security_authenticated.py`, `tests/test_http_hardening.py`), exécutés sur SQLite et PostgreSQL avec des données synthétiques :

| Domaine | Couvert par les tests | Reste à faire manuellement |
|---|---|---|
| Isolation des clients | Un second client ne lit, ne modifie, ne supprime rien du premier (pages, PDF, API publique, JSON, documents, constats, commentaires) | Rejouer sur le service déployé avec deux vrais comptes de test |
| Sessions et comptes | Déconnexion, cookie falsifié, jetons à usage unique, sessions invalidées après changement de mot de passe | Expiration réelle, rôles distincts (le produit n'en a pas encore) |
| CSRF et injections | Refus inter-sites sur chaque action ; HTML et PDF inertes avec du contenu hostile (titres, noms de fichiers, adresses, commentaires) | – |
| Fichiers et OCR | Types non pris en charge, PDF mal formés, vides ou piégés, extensions trompeuses, traversée de chemin, fichier trop gros | Fichiers volumineux ou très paginés en conditions réelles |
| Instructions dans les documents | Un texte « ignore les règles » ne modifie aucun constat ni gravité ; les prompts IA traitent le texte comme une donnée | Tester avec un vrai fournisseur IA branché |
| Fiabilité métier | Documents illisibles ou manquants, région inconnue ou préliminaire jamais présentés comme rassurants | Dossiers anonymisés réels (protocole bruxellois) |
| Coûts et quotas | Deux analyses simultanées sur un seul crédit, ré-analyses gratuites, webhooks rejoués | Mode test Stripe réel |
| Paiements | Signature, idempotence, résiliation (tests avec événements simulés) | Parcours complet avec le mode test de Stripe |
| Données et résilience | Suppression des fichiers et des lignes | Restauration d'une sauvegarde PostgreSQL, politique de conservation en production |

## Conditions minimales avant d'ouvrir à des dossiers réels
1. Tous les « À faire (propriétaire) » ci-dessus sont clos : identité, contacts, hébergeur, conditions, politique de confidentialité relues.
2. `RULES_VALIDATED=1` seulement après validation documentée des règles.
3. Une recette sur le service déployé : demande d'accès bout en bout, inscription avec code, dossier de démonstration, PDF, paiement en mode test, suppression.
4. Un plan de support, d'alertes (`/health`), de sauvegardes et de réponse à incident.

Une bêta limitée avec **données synthétiques ou anonymisées** peut commencer avant la clôture de tout ce qui précède.
