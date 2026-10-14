# Test Stripe pas à pas (mode test)

Prérequis : `docs/STRIPE.md` appliqué (clés `sk_test_…`, webhook `whsec_…`, portail client activé), site déployé, `/health` OK. Carte de test : `4242 4242 4242 4242`, date future, CVC quelconque. Carte refusée : `4000 0000 0000 0341` (acceptée à l'inscription, refusée au premier paiement). Cochez chaque ligne.

| # | Action | Résultat attendu |
|---|---|---|
| 1 | Déconnecté, page Tarifs | Boutons « Choisissez votre formule » ; clic → inscription → retour sur Tarifs |
| 2 | Achat « 1 dossier » (29 €) | Retour sur Compte, solde +1 dossier ; ligne de paiement dans Stripe |
| 3 | Rejouer l'événement dans Stripe (« Resend ») | Solde inchangé (idempotence) |
| 4 | Abonnement Agent mensuel | Essai de 3 jours, statut « essai », quota limité ; rien de facturé |
| 5 | Fin d'essai (Stripe : Subscriptions → avancer l'horloge ou terminer l'essai) | Premier paiement, statut « actif », quota complet |
| 6 | Compte → « Changer de formule » → Agence annuelle | Même abonnement, facture au prorata dans Stripe, quota de la formule Agence |
| 7 | Changement avec la carte `4000 0000 0000 0341` | Message d'échec, formule inchangée |
| 8 | « Gérer l'abonnement » → résilier | Mention « se termine à la fin de la période » ; quota utilisable jusque-là |
| 9 | Inscription avec le captcha activé | Widget visible ; sans validation, refus |
| 10 | Logs (`railway logs`) | Lignes `stripe … -> …` sans erreur |

Avant le passage en production : refaire 2, 4 et 8 avec les clés live et un vrai paiement faible, puis rembourser.
