# Plan de rénovation et budget indicatif

Le plan est **un ordre de grandeur, pas un devis**. Il est déduit des constats de l'analyse (jamais saisi à la main) et affiché sur la page du dossier, dans le PDF et dans l'API (`renovation`).

## Comment il est construit
- Chaque poste correspond à un ou plusieurs constats (`rules`) et cite leurs sources (document, page).
- Les postes sont classés en trois phases : **1. avant la signature** (inventaire d'amiante, nouveau PEB, régularisation urbanistique, étude de sol), **2. sécurité et mise en conformité** (retrait d'amiante, électricité), **3. amélioration énergétique**.
- Les constats écartés par l'utilisateur ne sont pas budgétés.
- Les postes pour lesquels aucune fourchette honnête n'existe (régularisation urbanistique, assainissement du sol) sont listés **sans chiffre** et comptés à part, jamais inclus dans le total.

## Fourchettes par défaut (hors TVA, octobre 2026)
| Poste | Fourchette | Niveau de confiance |
|---|---|---|
| Inventaire d'amiante | 150 – 600 € | fourchette de marché |
| Retrait de l'amiante (toiture) | 3 000 – 15 000 € | **hypothèse** : retrait publié 25–65 €/m² évacuation comprise, surface de toiture inconnue |
| Mise en conformité électrique | 1 000 – 7 000 € (forfait) | fourchette de marché (une remise aux normes complète d'une grande maison peut dépasser) |
| Nouveau contrôle électrique | 150 – 300 € | fourchette de marché |
| Nouveau PEB | 150 – 500 € | fourchette de marché |
| Amélioration énergétique, label E | 50 – 130 €/m² (sinon 2 000 – 15 000 €) | **hypothèse de travail** |
| Amélioration énergétique, label F | 100 – 250 €/m² (sinon 8 000 – 25 000 €) | **hypothèse de travail** |

Les montants « fourchette de marché » viennent de prix publiés par des sites de professionnels belges (guides de prix) et ne sont pas des tarifs officiels. Les montants « hypothèse » sont construits à partir de fourchettes publiées (isolation de toiture 20–100 €/m², murs 15–250 €/m², vitrage, chauffage ; amélioration d'un score PEB 2 000 – 25 000 € selon l'ampleur) : **ils doivent être validés par un professionnel (audit énergétique, devis) avant toute communication commerciale.**

La surface utilisée pour les postes au m² est celle du certificat PEB, à défaut celle d'un autre document ; la base du calcul est affichée.

## Ajuster les prix sans toucher au code
Créer un fichier JSON et indiquer son chemin dans la variable `RENOVATION_COST_FILE` :
```json
{"electrical_compliance": {"low": 1500, "high": 8000}, "energy_upgrade_f": {"low": 120, "high": 280}}
```
Clés autorisées par poste : `low`, `high`, `flat_low`, `flat_high`. Un fichier illisible est ignoré (les valeurs par défaut restent en place).

## À ne pas oublier
- Les aides et obligations de rénovation varient selon la région et changent (Wallonie : nouveau système de prêts depuis octobre 2026 ; Flandre : délais pour les logements E et F ; Bruxelles : primes Renolution suspendues). Le plan ne les chiffre pas : à vérifier auprès de l'administration régionale.
- Une TVA réduite de 6 % peut s'appliquer aux logements de plus de 10 ans occupés par leur propriétaire (à vérifier).
