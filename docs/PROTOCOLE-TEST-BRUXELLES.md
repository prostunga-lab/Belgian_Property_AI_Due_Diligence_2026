# Protocole de test avec un agent immobilier bruxellois

Objectif : savoir si l'outil fait gagner du temps et si ses constats sont justes **à Bruxelles**, où les règles du moteur sont encore **préliminaires** (aucun professionnel ne les a validées).

## Avant de commencer (à faire par vous)
1. **Accès** : générez un code d'invitation dédié (`docs/generer-secrets.html`) ou donnez celui en vigueur, puis communiquez-le à l'agent par un canal privé. L'agent crée son compte sur le site.
2. **Honnêteté sur l'état de l'outil** : dites à l'agent que c'est une version de test, que les règles bruxelloises sont préliminaires et que les résultats sont une aide à la lecture, pas un avis.
3. **Données** : demandez des documents **anonymisés** (noms, adresses exactes, numéros de registre national et coordonnées bancaires masqués), ou des dossiers dont l'agent a le droit de partager le contenu. Les pages légales sont encore des projets non relus par un juriste : n'acceptez pas de dossiers de clients réels tant que la politique de confidentialité n'est pas validée.
4. **Consentement et confidentialité** : convenez par écrit que les documents ne seront utilisés que pour le test et que l'agent peut demander leur suppression (bouton de suppression du dossier).

## Jeu de test fictif (avant de toucher à de vrais dossiers)
Un dossier bruxellois **entièrement inventé** (Ixelles, 1050) est fourni en deux variantes : `coherent` (rien d'important à signaler) et `problematique` (PEB G, électricité non conforme, surface incohérente, infraction urbanistique, bien à l'inventaire du patrimoine, litige et arriérés de copropriété).
```
python scripts/make_brussels_pack.py pack-bruxelles
```
Déposez les 6 PDF d'une variante dans un dossier, lancez l'analyse et comparez avec `tests/test_brussels.py` (résultats attendus). Documents attendus à Bruxelles : PEB, contrôle électrique, attestation du sol, acte/compromis, **renseignements urbanistiques** (l'attestation amiante n'est pas exigée dans le moteur ; ces choix sont préliminaires et à valider par un professionnel).
Particularités appliquées à Bruxelles : pas de contrôle étiquette/score à la flamande, étiquettes E/F/G jugées faibles, vocabulaire PRAS/PPAS/CoBAT/urban.brussels et « inventaire du patrimoine » reconnus.

## Scénarios à faire tester (3 à 5 dossiers)
| # | Dossier | Ce qu'on vérifie |
|---|---|---|
| 1 | Un dossier bruxellois complet récent (PEB, acte ou compromis, contrôle électrique, attestation du sol, urbanisme) | Région détectée (code postal 1000–1299), documents attendus corrects, absence de faux « manquant » |
| 2 | Un dossier avec une copropriété (appartement) | Lecture des documents de copropriété, litiges, arriérés, fonds de réserve |
| 3 | Un dossier avec un scan de mauvaise qualité | OCR, avertissements de qualité, aucune valeur inventée |
| 4 | Un dossier avec des incohérences connues (surfaces, année de construction, adresse) | Les incohérences sont détectées avec la bonne source |
| 5 | Un dossier propre | Pas de faux positifs gênants |

Pour chaque dossier : déposer les documents, lancer l'analyse, lire le résumé, la chronologie, les constats, le plan de rénovation, puis télécharger le PDF.

## Questions à poser à l'agent
**Exactitude**
- Les informations extraites (adresse, surfaces, année, label PEB, conformité) sont-elles justes ? Lesquelles sont fausses ou manquantes ?
- Les documents attendus à Bruxelles correspondent-ils à votre pratique ? Lequel manque ou est en trop ?
- Un constat important a-t-il été **raté** ? Un constat est-il **faux ou trompeur** ?
- Le plan de rénovation et ses fourchettes vous paraissent-ils réalistes pour Bruxelles ? Quels postes sont trop hauts, trop bas ?

**Utilité**
- Combien de temps avez-vous gagné par dossier (estimation) ?
- Qu'utiliseriez-vous tel quel avec un client ? Qu'est-ce qui vous gênerait de montrer à un client ?
- Qu'est-ce qui manque pour que vous l'utilisiez chaque semaine ?

**Prix**
- À partir de quel prix par dossier ou par mois cela devient-il trop cher ? Quel prix vous semble normal ?

## Grille de notes (à remplir par dossier)
| Dossier | Champs justes / total | Constats justes | Constats faux | Constats ratés | Gain de temps | Remarques |
|---|---|---|---|---|---|---|

## Comment utiliser les retours
- Chaque erreur d'extraction → un exemple de texte à ajouter aux tests (en anonymisant).
- Chaque règle bruxelloise contestée → à confirmer avec le notaire de l'agent avant de la durcir.
- Les fourchettes de rénovation contestées → ajuster `RENOVATION_COST_FILE` (voir `docs/RENOVATION.md`).

## À ne pas promettre
- Aucune garantie d'exactitude.
- Aucune validation juridique : le texte du service précise que les conclusions doivent être validées par un professionnel.
