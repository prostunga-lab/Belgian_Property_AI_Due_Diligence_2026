# Brancher les paiements Stripe

Le code est déjà intégré : achats au dossier (29 €, pack de 5), abonnements agent et agence au mois / semestre / an, essai gratuit de 3 jours sur les abonnements, portail client, webhooks signés et idempotents. Il reste à **configurer votre compte Stripe et les variables Railway**. La carte bancaire est saisie chez Stripe (page Stripe Checkout) : elle ne passe jamais par vos serveurs.

> Les intitulés des écrans Stripe changent de temps en temps : si un libellé diffère, cherchez le mot-clé (« API keys », « Webhooks », « Customer portal »). Toutes les étapes se font d'abord en **mode test** (bandeau « Test mode » du tableau de bord Stripe).

## 1. Créer et activer le compte
1. Créez un compte sur [stripe.com](https://stripe.com) avec l'e-mail de la société.
2. Pour accepter de vrais paiements, Stripe demandera d'**activer** le compte : informations sur l'entité (société ou indépendant, numéro d'entreprise), représentant légal, pièce d'identité, IBAN pour les virements, description de l'activité et adresse du site. Les informations doivent correspondre aux mentions légales du site.
3. Le mode test fonctionne sans activation : commencez par là.

## 2. Récupérer la clé secrète (mode test)
Tableau de bord → **Developers → API keys** → « Secret key » (`sk_test_…`). Ne la partagez jamais (ni dans un message, ni dans le dépôt).

## 3. Créer le webhook
1. **Developers → Webhooks → Add endpoint**.
2. URL : `https://<votre-domaine>/billing/webhook` (par exemple `https://belgianpropertyaiduediligence2026-production.up.railway.app/billing/webhook`).
3. Événements à cocher :
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Après la création, ouvrez le webhook et copiez la **clé de signature** « Signing secret » (`whsec_…`).

## 4. Activer le portail client
**Settings → Billing → Customer portal** : activer, puis autoriser la mise à jour du moyen de paiement, la consultation des factures et **l'annulation de l'abonnement** (de préférence « à la fin de la période »). C'est ce que le bouton « Gérer mon abonnement » ouvre. Sans portail activé, ce bouton échoue.

## 5. Variables à ajouter dans Railway
| Variable | Valeur |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_test_…` (puis `sk_live_…` au lancement) |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` du webhook correspondant |
| `BASE_URL` | l'adresse publique du site, sans `/` final (déduite de Railway si absente ; à fixer si vous avez un domaine à vous) |
| `TRIAL_DAYS` / `TRIAL_DAYS_INDIVIDUAL` / `TRIAL_DOSSIERS` | facultatif : durée de l'essai des professionnels (3 par défaut) et des particuliers (1 par défaut), `0` pour le supprimer) et dossiers autorisés pendant l'essai (3 par défaut) |
| `PLAN_*_PRICE_EUR`, `DISCOUNT_*_PCT` | facultatif : prix et remises (voir `docs/DEPLOY.md`) |

Puis **Deploy** (ou `railway up`). Quand `STRIPE_SECRET_KEY` est présent, les boutons d'achat et d'abonnement apparaissent sur la page Tarifs et dans le compte ; sans elle, ils sont masqués.

Aucun produit ni prix n'est à créer dans Stripe : le site envoie le prix exact (celui affiché, remise comprise) à chaque paiement.

## 6. Tester en mode test
Cartes de test (n'importe quelle date future et n'importe quel CVC) :
- `4242 4242 4242 4242` : paiement réussi ;
- `4000 0025 0000 3155` : demande l'authentification 3D Secure ;
- `4000 0000 0000 0341` : la carte s'enregistre mais le prélèvement suivant échoue (teste « paiement échoué »).

Scénarios à dérouler avec un compte de test :
1. **Achat au dossier** (29 €) : après le paiement, le solde du compte augmente de 1 dossier. Rejouez l'événement depuis Stripe (« Resend ») : le solde ne doit pas augmenter une deuxième fois.
2. **Abonnement avec essai** : « Essayer 3 jours gratuitement » → paiement de 0 € → l'état devient « période d'essai », avec 3 dossiers au maximum.
3. **Fin d'essai** : dans Stripe, **Billing → Test clocks**, créez une horloge et avancez-la de 3 jours : le premier paiement est prélevé, l'état passe à « actif » et le quota complet devient disponible.
4. **Résiliation pendant l'essai** (bouton « Gérer mon abonnement ») : aucun prélèvement, le quota tombe à zéro à la fin.
5. **Paiement échoué** (carte `…0341`) : l'état passe à « past_due » et le quota est suspendu.

Où regarder : dans Stripe, la page du webhook liste chaque envoi (code 200 attendu) ; dans les logs Railway, chaque événement écrit une ligne `stripe <type> <id> -> <résultat>`.

## 7. Passer en production
1. Terminer l'activation du compte (étape 1).
2. Basculer le tableau de bord en mode **live** et **refaire** : la clé `sk_live_…`, un **nouveau webhook** (avec sa propre clé `whsec_…`, les clés de test et de production sont distinctes) et l'activation du portail client.
3. Remplacer les deux variables dans Railway, redéployer.
4. Faire un vrai achat de 29 € avec votre carte, vérifier le solde et la facture, puis le rembourser depuis Stripe.

## 8. Dépannage
| Symptôme | Cause probable |
|---|---|
| Pas de bouton d'achat | `STRIPE_SECRET_KEY` absente ou le service n'a pas été redéployé |
| Message « Paiement non configuré » | `STRIPE_WEBHOOK_SECRET` absente |
| Webhook en erreur 400 (signature) | mauvaise clé `whsec_…`, ou clé du mode test avec un webhook du mode live (ou l'inverse) |
| Le paiement réussit mais le compte ne change pas | webhook non reçu : vérifier l'URL, les événements cochés et les logs |
| « Vous avez déjà un abonnement » | un compte ne peut avoir qu'un abonnement actif ; pour changer de formule ou de période, utiliser « Changer de formule » (page Compte ou Tarifs) |
| Retour vers une mauvaise adresse après paiement | fixer `BASE_URL` |

## 9. Ce que Stripe ne fait pas à votre place
- **TVA et factures** : les prix affichés incluent la TVA (`PRICES_VAT=incl`). Vérifier avec votre comptable la TVA applicable, les mentions des factures et, éventuellement, activer Stripe Tax. Pour les achats uniques, activer la création de factures dans Stripe si vous en avez besoin.
- **Remboursements** : à faire dans Stripe ; ils ne retirent pas automatiquement les dossiers déjà crédités.
- **Conditions** : l'essai gratuit et le renouvellement automatique doivent être décrits dans les conditions générales (déjà le cas dans le texte-projet) et validés par votre conseil, notamment pour les consommateurs (information avant achat, droit de rétractation).
- **Changement de formule en cours d'abonnement** : géré (`POST /billing/change`). Même abonnement Stripe, nouveau prix ; Stripe crédite le temps non utilisé et facture le nouveau prix tout de suite (`always_invoice`), y compris pour une formule inférieure (le crédit est déduit des prochaines factures). Pendant l'essai gratuit, aucun prorata et l'essai continue. Une carte refusée laisse l'abonnement inchangé. Le quota suit la nouvelle formule immédiatement ; les dossiers déjà utilisés ce mois-ci restent comptés. À tester en mode test : passer de Agent mensuel à Agence annuelle et vérifier la facture au prorata dans Stripe.
