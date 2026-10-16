"""Fictional Brussels-Capital documents (French). Entirely invented: no real person, address or certificate."""
ADDR = "Rue des Tilleuls 24, 1050 Ixelles"

DEED = f"""COMPROMIS DE VENTE
Signé le 10/02/2026 devant le notaire Maître Dupont.
Vendeur : Marie Lambert
Acquéreur : Paul Renard
Bien situé à {ADDR}.
Référence cadastrale : section B numéro 456/C.
Superficie habitable de 120 m².
Année de construction 1968.
"""
EPC = f"""Certificat PEB (performance énergétique des bâtiments)
Numéro de certificat 20250601-0004321
Adresse : {ADDR}
Classe énergétique : E
Consommation d'énergie primaire 310 kWh/m².an
Surface utile 120 m²
Valable jusqu'au 01/06/2035
Année de construction 1968
"""
ELEC = f"""Rapport de contrôle de l'installation électrique (RGIE)
Adresse : {ADDR}
Date du contrôle : 15/01/2026
Installation conforme.
"""
SOIL = f"""Attestation du sol - Bruxelles Environnement
{ADDR}
Date : 20/01/2026
La parcelle est inscrite à l'inventaire de l'état du sol : catégorie 0, aucune pollution connue.
"""
URBANISM = f"""Renseignements urbanistiques - Commune d'Ixelles
{ADDR}
Date : 05/02/2026
Selon le PRAS, le bien se situe en zone d'habitation. Aucun procès-verbal d'infraction n'est connu.
Le bien n'est pas repris à l'inventaire du patrimoine.
"""
COPRO = """Décompte de la copropriété Résidence des Tilleuls
Fonds de réserve : 18.500,00 EUR
Assemblée générale du 20/03/2025
Charges mensuelles : 210,00 EUR
Il n'y a pas de litige en cours.
"""

# Problematic variant: bad energy label, old non-conform electrics, infraction + heritage, dispute and arrears, surface mismatch.
EPC_BAD = EPC.replace("Classe énergétique : E", "Classe énergétique : G").replace("310 kWh", "520 kWh")
ELEC_BAD = ELEC.replace("15/01/2026", "05/05/2002").replace("Installation conforme.", "Installation non conforme.")
URBANISM_BAD = URBANISM.replace(
    "Aucun procès-verbal d'infraction n'est connu.", "Un procès-verbal d'infraction a été dressé en 2019."
).replace("n'est pas repris", "est repris")
DEED_BAD = DEED.replace("120 m²", "150 m²")
COPRO_BAD = COPRO.replace("Il n'y a pas de litige en cours.", "Un litige est en cours avec le syndic. Arriérés de charges du propriétaire : 1.200 EUR.")

COHERENT = {"01-compromis.pdf": DEED, "02-peb.pdf": EPC, "03-controle-electrique.pdf": ELEC, "04-attestation-sol.pdf": SOIL,
            "05-renseignements-urbanistiques.pdf": URBANISM, "06-copropriete.pdf": COPRO}
PROBLEM = {"01-compromis.pdf": DEED_BAD, "02-peb.pdf": EPC_BAD, "03-controle-electrique.pdf": ELEC_BAD, "04-attestation-sol.pdf": SOIL,
           "05-renseignements-urbanistiques.pdf": URBANISM_BAD, "06-copropriete.pdf": COPRO_BAD}
