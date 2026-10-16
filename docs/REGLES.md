# Registre des règles

Jeu de règles **VL-2026.1** (périmètre : Flandre ; Bruxelles et Wallonie : préliminaires). Ce fichier est généré par `python -m app.rules_doc`.

Chaque règle doit être validée par le professionnel compétent avant l'ouverture commerciale : compléter les colonnes **Base juridique**, **Date d'effet**, **Exceptions**, puis **Validée par / le**. Tant qu'une ligne n'est pas validée, la règle reste « en cours de validation » (variable `RULES_VALIDATED`).

| Règle | Domaine | Gravité par défaut | Nature | Description (FR) | Cas de test | Base juridique | Date d'effet | Exceptions | Validée par / le |
|---|---|---|---|---|---|---|---|---|---|
| `DOC-EPC` | documentation | selon le document | action | Document manquant : PEB (certificat de performance énergétique) | 2 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-ASBESTOS` | documentation | selon le document | action | Document manquant : attestation d'amiante (asbestattest) | 4 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-ELECTRICAL` | documentation | selon le document | action | Document manquant : rapport de contrôle de l'installation électrique | 3 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-SOIL` | documentation | selon le document | action | Document manquant : attestation du sol (bodemattest) | 3 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-DEED` | documentation | selon le document | action | Document manquant : acte / compromis de vente | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-URBANISM` | documentation | selon le document | action | Document manquant : renseignements urbanistiques | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-OCR` | documentation | medium | risk | Document illisible : … | 4 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-OCR-LOWQ` | documentation | medium | risk | Mauvaise qualité de scan : … | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-OCR-USED` | documentation | info | fact | Document scanné (OCR) : … | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-WARN` | documentation | low | action | Avertissement de lecture : … | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-UNK` | documentation | low | action | Type de document non reconnu : … | 2 fichier(s) | à compléter | à compléter | à compléter | |
| `EPC-EXPIRED` | energy | high | risk | PEB expiré | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `EPC-OLD` | energy | high | risk | PEB de plus de 10 ans | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `EPC-LABEL-MISMATCH` | energy | medium | inference | Étiquette et score incohérents | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `EPC-POOR` | energy | sev | risk | Mauvaise performance énergétique (étiquette …) | 3 fichier(s) | à compléter | à compléter | à compléter | |
| `ASB-PRESENT` | environmental | high | risk | Amiante constaté ou suspecté | 6 fichier(s) | à compléter | à compléter | à compléter | |
| `ASB-CLEAR` | environmental | info | fact | Aucun amiante mentionné dans l'attestation | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `ASB-UNCLEAR` | environmental | medium | risk | Résultat amiante peu clair | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `ASB-OLD-NEG` | environmental | low | inference | Attestation sans amiante pour un logement d'avant 2001 | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `ELEC-NONCONFORM` | technical | high | risk | Installation électrique non conforme | 4 fichier(s) | à compléter | à compléter | à compléter | |
| `ELEC-OLD` | technical | medium | risk | Rapport de contrôle de plus de 25 ans | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `SOIL-POLLUTION` | environmental | high | risk | Pollution du sol ou risque mentionné | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `SOIL-CLEAR` | environmental | info | fact | Aucune pollution du sol mentionnée dans l'attestation | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `SOIL-UNCLEAR` | environmental | medium | risk | Statut du sol non identifié clairement | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `CAD-UNBUILT` | urbanistic | high | inference | Le cadastre décrit une parcelle non bâtie | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `X-CADASTRE` | legal | high | inference | Référence cadastrale différente entre l'acte et l'extrait | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `X-ADDRESS` | legal | high | inference | Adresses différentes selon les documents | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `X-SURFACE` | ? | ? | ? | Superficies différentes selon les documents | 10 fichier(s) | à compléter | à compléter | à compléter | |
| `URB-EXT-NOPERMIT` | urbanistic | high | risk | Extension sans permis démontrable | 3 fichier(s) | à compléter | à compléter | à compléter | |
| `URB-NO-INFO` | urbanistic | medium | risk | Aucun renseignement urbanistique dans l'acte | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `X-BUILDYEAR` | legal | medium | inference | Année de construction différente selon les documents | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `LEG-CADASTRE` | legal | low | action | Référence cadastrale introuvable | 0 fichier(s) | à compléter | à compléter | à compléter | |
| `X-DATES` | documentation | medium | inference | Attestation d'amiante postérieure à l'acte | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `WORK-EPC-STALE` | energy | low | inference | Travaux énergétiques postérieurs au PEB | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `WORK-ELEC-STALE` | technical | medium | inference | Travaux électriques postérieurs au contrôle | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `X-WORKS-BEFORE-BUILD` | documentation | low | inference | Facture antérieure à la construction | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `URB-INFRACTION` | urbanistic | high | risk | Infraction urbanistique mentionnée | 2 fichier(s) | à compléter | à compléter | à compléter | |
| `URB-FLOOD` | environmental | medium | risk | Risque d'inondation mentionné | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `URB-HERITAGE` | urbanistic | medium | risk | Bien protégé ou inscrit à l'inventaire du patrimoine | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `COPRO-DISPUTE` | legal | medium | risk | Litige en copropriété mentionné | 2 fichier(s) | à compléter | à compléter | à compléter | |
| `COPRO-ARREARS` | legal | medium | risk | Arriérés de charges mentionnés | 2 fichier(s) | à compléter | à compléter | à compléter | |
| `COPRO-OLD-AG` | documentation | low | action | Dernière assemblée générale ancienne | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `DOC-PHOTO` | documentation | info | fact | Photos jointes au dossier | 1 fichier(s) | à compléter | à compléter | à compléter | |
| `REG-UNKNOWN` | documentation | info | fact | Région non déterminée | 2 fichier(s) | à compléter | à compléter | à compléter | |
| `REG-CONFLICT` | documentation | medium | inference | Régions différentes selon les documents | 2 fichier(s) | à compléter | à compléter | à compléter | |
| `REG-PRELIM` | documentation | medium | action | Règles régionales préliminaires | 3 fichier(s) | à compléter | à compléter | à compléter | |

La gravité réelle peut varier selon la situation (voir `app/rules.py`). La nature (fait, inférence, risque, action) est affichée dans chaque rapport.
