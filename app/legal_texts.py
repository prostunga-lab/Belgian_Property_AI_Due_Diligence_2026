"""Texts of the three legal pages (DRAFTS: they must be reviewed by a lawyer before the service goes public).

Structure: TEXTS[lang][doc] = [(section title, [item, ...]), ...]
 - an item is a paragraph; "- text" is a bullet; a ("stripe" | "ai" | "smtp", text) tuple is shown only when that feature is configured
 - placeholders {company} {address} {enterprise} {email} {phone} {hosting} {hosting_region} are replaced by the configured value,
   or by a visible "to be completed" marker when it is not configured; nothing is ever invented.
 - {todo} marks a business decision that is still open (refund policy, validity of credits, ...).
"""
VERSION = "2026-10-07"
DOCS = ("legal", "privacy", "terms")

FR = {
    "legal": [
        ("Éditeur du service", [
            "Le service « Belgian Immo Due Diligence » est édité par :",
            "- Dénomination : {company}", "- Adresse : {address}", "- Numéro d'entreprise (BCE/TVA) : {enterprise}",
            "- E-mail : {email}", "- Téléphone : {phone}"]),
        ("Hébergement", ["Le service est hébergé par {hosting} (région : {hosting_region})."]),
        ("Nature du service", [
            "Le service aide à repérer des points d'attention dans un dossier d'achat immobilier (Flandre) à partir de documents que l'utilisateur télécharge. "
            "Il fournit une aide à la lecture automatisée. Il ne constitue ni un conseil juridique, ni une expertise, ni un avis d'un notaire, "
            "et ne remplace pas la vérification des documents originaux par un professionnel."]),
        ("Propriété intellectuelle", [
            "Le site, son code, ses textes et sa marque appartiennent à l'éditeur. Les documents téléchargés restent la propriété de l'utilisateur ou de ses ayants droit."]),
        ("Litiges", ["Le droit belge s'applique. Les tribunaux belges sont compétents, sous réserve des règles impératives protégeant les consommateurs."]),
    ],
    "privacy": [
        ("Qui est responsable ?", [
            "Le responsable du traitement des données de compte est {company}, {address}. Contact : {email}.",
            "Pour les documents de dossiers qu'un professionnel (agence, cabinet) télécharge au sujet de ses propres clients, ce professionnel reste responsable du traitement "
            "et l'éditeur agit comme sous-traitant : le professionnel doit disposer d'une base légale pour déposer ces documents."]),
        ("Données traitées", [
            "- Compte : nom de l'agence/cabinet/société, e-mail, mot de passe (conservé uniquement sous forme de hachage scrypt), langue choisie, date et version d'acceptation des conditions.",
            "- Dossiers : titres, documents téléchargés (stockés chiffrés), texte extrait, résultats de l'analyse, durée d'analyse.",
            "- Facturation : historique des achats et abonnements (montant, date, formule).",
            "- Journal d'audit : actions importantes liées au compte (connexion, création, suppression, paiement).",
            ("stripe", "- Paiement : les coordonnées de carte sont saisies chez Stripe et ne transitent jamais par nos serveurs ; nous recevons uniquement l'état du paiement et des identifiants."),
        ]),
        ("Finalités et bases légales", [
            "- Fournir le service demandé (exécution du contrat).", "- Sécuriser les comptes et prévenir les abus (intérêt légitime).",
            "- Conserver les pièces comptables (obligation légale) : environ 7 ans.", "- Répondre à vos demandes (intérêt légitime)."]),
        ("Sous-traitants et destinataires", [
            "Les données ne sont ni vendues ni utilisées à des fins publicitaires. Elles peuvent être traitées par :",
            "- {hosting} (hébergement, région : {hosting_region}).",
            ("stripe", "- Stripe (paiements)."),
            ("smtp", "- Le fournisseur d'e-mail configuré (e-mails de vérification et de réinitialisation du mot de passe)."),
            ("ai", "- Anthropic (lecture assistée par IA, uniquement si l'option est activée) : le texte des documents peut lui être transmis pour obtenir le résumé."),
            "Si des données sont transférées hors de l'Espace économique européen, des garanties appropriées (clauses contractuelles types) doivent être en place : {todo}."]),
        ("Cookies", [
            "Nous n'utilisons que deux cookies strictement nécessaires, sans suivi ni publicité :",
            "- « session » : vous garde connecté (12 heures).", "- « lang » : mémorise votre langue (12 mois).",
            "Aucun consentement n'est requis pour ces cookies fonctionnels."]),
        ("Durée de conservation", [
            "Les dossiers et documents sont conservés jusqu'à leur suppression par l'utilisateur ou la clôture du compte. "
            "Les données de facturation sont conservées environ 7 ans. Les fichiers sont stockés chiffrés."]),
        ("Vos droits", [
            "Vous pouvez demander l'accès, la rectification, l'effacement, la limitation, l'opposition et la portabilité de vos données en écrivant à {email}. "
            "Vous pouvez aussi introduire une réclamation auprès de l'Autorité de protection des données (www.autoriteprotectiondonnees.be)."]),
    ],
    "terms": [
        ("Objet", ["Les présentes conditions régissent l'utilisation du service « Belgian Immo Due Diligence » édité par {company}. En créant un compte, vous les acceptez."]),
        ("Le service", [
            "Le service analyse des documents de dossier immobilier et signale des points d'attention. Le résultat est une aide à la lecture : il peut être incomplet ou erroné et doit être vérifié. "
            "Il ne remplace ni un notaire, ni un expert, ni un conseil juridique. Vous restez responsable des décisions prises.",
            "Nous visons un premier rapport en moins de {minutes} minutes pour un dossier complet standard. Cet objectif n'est pas une garantie : "
            "le délai dépend de la taille et de la qualité des documents (documents scannés, lecture IA éventuelle) et de la charge du service."]),
        ("Compte et accès", [
            "L'accès est limité aux personnes autorisées (inscription sur invitation). Vous êtes responsable de la confidentialité de vos identifiants et des actions réalisées avec votre compte."]),
        ("Vos documents", [
            "Vous garantissez avoir le droit de télécharger les documents et, pour les données de tiers, disposer d'une base légale pour le faire. Nous les traitons uniquement pour fournir le service, voir la politique de confidentialité."]),
        ("Dossiers, crédits et abonnements", [
            "- Un dossier complet analysé correspond à un crédit ou à un dossier du quota d'abonnement.",
            "- Paiement à l'unité : les crédits achetés servent à analyser des dossiers ; validité et remboursement des crédits non utilisés : {todo}.",
            "- Abonnements (agent, agence) : un quota de dossiers par mois, renouvelé chaque mois à la date anniversaire, non reportable. La formule peut être payée par mois, par semestre ou par an, avec les remises affichées sur la page Tarifs.",
            "- L'abonnement se renouvelle automatiquement à la fin de chaque période. Vous pouvez le résilier à tout moment depuis le portail de facturation ; il reste actif jusqu'à la fin de la période payée.",
            ("trial", "- Essai gratuit : les abonnements (agent, agence) peuvent être essayés pendant {trial_days} jours, dans la limite de {trial_dossiers} dossiers, une fois par organisation. Une carte bancaire est demandée au départ ; à la fin de l'essai l'abonnement est facturé automatiquement, sauf résiliation avant cette date depuis le portail de facturation."),
            "- Les prix affichés sont ceux de la page Tarifs au moment de l'achat."]),
        ("Droit de rétractation", [
            "Les consommateurs disposent en principe de 14 jours pour se rétracter, sauf pour un contenu numérique ou un service pleinement exécuté avec leur accord préalable exprès et la reconnaissance de la perte du droit de rétractation. Modalités applicables : {todo}."]),
        ("Responsabilité", [
            "Nous répondons de nos fautes dans les limites permises par la loi. Nous ne garantissons pas l'exactitude des résultats ni l'absence d'interruption du service. {todo}"]),
        ("Modification et résiliation", [
            "Nous pouvons modifier ces conditions ; la version applicable est celle en vigueur à la date d'acceptation, et les changements importants vous seront notifiés. Vous pouvez supprimer votre compte à tout moment."]),
        ("Droit applicable", ["Droit belge. Tribunaux belges, sous réserve des règles impératives protégeant les consommateurs."]),
    ],
}

NL = {
    "legal": [
        ("Uitgever van de dienst", [
            "De dienst « Belgian Immo Due Diligence » wordt uitgegeven door:",
            "- Naam: {company}", "- Adres: {address}", "- Ondernemingsnummer (KBO/btw): {enterprise}",
            "- E-mail: {email}", "- Telefoon: {phone}"]),
        ("Hosting", ["De dienst wordt gehost door {hosting} (regio: {hosting_region})."]),
        ("Aard van de dienst", [
            "De dienst helpt aandachtspunten te vinden in een dossier voor de aankoop van vastgoed (Vlaanderen), op basis van documenten die de gebruiker downloadt naar de dienst. "
            "Het is een geautomatiseerde leeshulp. Het is geen juridisch advies, geen expertise en geen advies van een notaris, "
            "en vervangt de controle van de originele documenten door een professional niet."]),
        ("Intellectuele eigendom", [
            "De site, de code, de teksten en het merk behoren toe aan de uitgever. De geüploade documenten blijven eigendom van de gebruiker of zijn rechthebbenden."]),
        ("Geschillen", ["Het Belgische recht is van toepassing. De Belgische rechtbanken zijn bevoegd, onder voorbehoud van dwingende regels ter bescherming van consumenten."]),
    ],
    "privacy": [
        ("Wie is verantwoordelijk?", [
            "Verwerkingsverantwoordelijke voor de accountgegevens is {company}, {address}. Contact: {email}.",
            "Voor dossierdocumenten die een professional (kantoor, makelaar) over zijn eigen klanten uploadt, blijft die professional verwerkingsverantwoordelijke "
            "en treedt de uitgever op als verwerker: de professional moet een rechtsgrond hebben om die documenten te uploaden."]),
        ("Verwerkte gegevens", [
            "- Account: naam van kantoor/bedrijf, e-mail, wachtwoord (enkel bewaard als scrypt-hash), gekozen taal, datum en versie van de aanvaarding van de voorwaarden.",
            "- Dossiers: titels, geüploade documenten (versleuteld opgeslagen), uitgelezen tekst, analyseresultaten, analyseduur.",
            "- Facturatie: geschiedenis van aankopen en abonnementen (bedrag, datum, formule).",
            "- Auditlog: belangrijke acties op het account (aanmelden, aanmaken, verwijderen, betaling).",
            ("stripe", "- Betaling: kaartgegevens worden ingevoerd bij Stripe en passeren nooit onze servers; wij ontvangen enkel de betaalstatus en identificatoren."),
        ]),
        ("Doeleinden en rechtsgronden", [
            "- De gevraagde dienst leveren (uitvoering van de overeenkomst).", "- Accounts beveiligen en misbruik voorkomen (gerechtvaardigd belang).",
            "- Boekhoudkundige stukken bewaren (wettelijke verplichting): ongeveer 7 jaar.", "- Op uw vragen antwoorden (gerechtvaardigd belang)."]),
        ("Verwerkers en ontvangers", [
            "Gegevens worden niet verkocht of voor reclame gebruikt. Ze kunnen worden verwerkt door:",
            "- {hosting} (hosting, regio: {hosting_region}).",
            ("stripe", "- Stripe (betalingen)."),
            ("smtp", "- De geconfigureerde e-mailprovider (verificatie- en wachtwoordresetmails)."),
            ("ai", "- Anthropic (AI-ondersteunde lezing, enkel indien de optie actief is): de tekst van documenten kan hiernaartoe worden gestuurd om de samenvatting te krijgen."),
            "Worden gegevens buiten de Europese Economische Ruimte doorgegeven, dan moeten passende waarborgen (standaardcontractbepalingen) bestaan: {todo}."]),
        ("Cookies", [
            "Wij gebruiken slechts twee strikt noodzakelijke cookies, zonder tracking of reclame:",
            "- « session »: houdt u aangemeld (12 uur).", "- « lang »: onthoudt uw taal (12 maanden).",
            "Voor deze functionele cookies is geen toestemming vereist."]),
        ("Bewaartermijn", [
            "Dossiers en documenten worden bewaard tot de gebruiker ze verwijdert of het account wordt gesloten. "
            "Facturatiegegevens worden ongeveer 7 jaar bewaard. Bestanden worden versleuteld opgeslagen."]),
        ("Uw rechten", [
            "U kunt inzage, verbetering, wissing, beperking, bezwaar en overdraagbaarheid van uw gegevens vragen via {email}. "
            "U kunt ook klacht indienen bij de Gegevensbeschermingsautoriteit (www.gegevensbeschermingsautoriteit.be)."]),
    ],
    "terms": [
        ("Doel", ["Deze voorwaarden regelen het gebruik van de dienst « Belgian Immo Due Diligence » van {company}. Door een account aan te maken aanvaardt u ze."]),
        ("De dienst", [
            "De dienst analyseert documenten van een vastgoeddossier en signaleert aandachtspunten. Het resultaat is een leeshulp: het kan onvolledig of onjuist zijn en moet worden gecontroleerd. "
            "Het vervangt geen notaris, expert of juridisch advies. U blijft verantwoordelijk voor uw beslissingen.",
            "Wij streven naar een eerste rapport binnen {minutes} minuten voor een standaard volledig dossier. Dit streefdoel is geen garantie: "
            "de duur hangt af van de omvang en kwaliteit van de documenten (gescande documenten, eventuele AI-lezing) en van de drukte op de dienst."]),
        ("Account en toegang", [
            "Toegang is beperkt tot bevoegde personen (registratie op uitnodiging). U bent verantwoordelijk voor de vertrouwelijkheid van uw inloggegevens en voor handelingen met uw account."]),
        ("Uw documenten", [
            "U garandeert het recht te hebben de documenten te uploaden en, voor gegevens van derden, een rechtsgrond te hebben. Wij verwerken ze enkel om de dienst te leveren, zie het privacybeleid."]),
        ("Dossiers, tegoed en abonnementen", [
            "- Een volledig geanalyseerd dossier komt overeen met één tegoed of één dossier van het abonnementsquotum.",
            "- Betaling per stuk: gekochte tegoeden dienen om dossiers te analyseren; geldigheid en terugbetaling van ongebruikte tegoeden: {todo}.",
            "- Abonnementen (makelaar, kantoor): een quotum dossiers per maand, elke maand vernieuwd op de verjaardatum, niet overdraagbaar. De formule kan per maand, per halfjaar of per jaar worden betaald, met de korting op de pagina Tarieven.",
            "- Het abonnement wordt automatisch verlengd aan het einde van elke periode. U kunt op elk moment opzeggen via het factureringsportaal; het blijft actief tot het einde van de betaalde periode.",
            ("trial", "- Gratis proefperiode: de abonnementen (makelaar, kantoor) kunnen {trial_days} dagen worden uitgeprobeerd, beperkt tot {trial_dossiers} dossiers, eenmaal per organisatie. Bij de start wordt een bankkaart gevraagd; na de proefperiode wordt het abonnement automatisch aangerekend, tenzij u vóór die datum opzegt via het factureringsportaal."),
            "- De getoonde prijzen zijn die van de pagina Tarieven op het moment van aankoop."]),
        ("Herroepingsrecht", [
            "Consumenten hebben in principe 14 dagen om te herroepen, behalve voor digitale inhoud of een volledig uitgevoerde dienst met hun voorafgaande uitdrukkelijke instemming en erkenning van het verlies van het herroepingsrecht. Toepasselijke regeling: {todo}."]),
        ("Aansprakelijkheid", [
            "Wij zijn aansprakelijk voor onze fouten binnen de wettelijke grenzen. Wij garanderen niet dat resultaten juist zijn of dat de dienst ononderbroken beschikbaar is. {todo}"]),
        ("Wijziging en beëindiging", [
            "Wij kunnen deze voorwaarden wijzigen; de toepasselijke versie is die op de datum van aanvaarding, en belangrijke wijzigingen worden aangekondigd. U kunt uw account op elk moment verwijderen."]),
        ("Toepasselijk recht", ["Belgisch recht. Belgische rechtbanken, onder voorbehoud van dwingende regels ter bescherming van consumenten."]),
    ],
}

EN = {
    "legal": [
        ("Publisher", [
            "The « Belgian Immo Due Diligence » service is published by:",
            "- Name: {company}", "- Address: {address}", "- Enterprise number (BCE/VAT): {enterprise}",
            "- E-mail: {email}", "- Phone: {phone}"]),
        ("Hosting", ["The service is hosted by {hosting} (region: {hosting_region})."]),
        ("Nature of the service", [
            "The service helps spot points of attention in a property purchase file (Flanders) from documents the user uploads. "
            "It is an automated reading aid. It is not legal advice, a survey or a notary's opinion, "
            "and does not replace the checking of original documents by a professional."]),
        ("Intellectual property", [
            "The site, its code, texts and brand belong to the publisher. Uploaded documents remain the property of the user or their rightsholders."]),
        ("Disputes", ["Belgian law applies. Belgian courts have jurisdiction, subject to mandatory consumer protection rules."]),
    ],
    "privacy": [
        ("Who is responsible?", [
            "The controller of account data is {company}, {address}. Contact: {email}.",
            "For case documents that a professional (agency, firm) uploads about their own clients, that professional remains the controller "
            "and the publisher acts as processor: the professional must have a legal basis to upload those documents."]),
        ("Data we process", [
            "- Account: agency/firm/company name, e-mail, password (stored only as a scrypt hash), chosen language, date and version of the terms acceptance.",
            "- Cases: titles, uploaded documents (stored encrypted), extracted text, analysis results, analysis time.",
            "- Billing: history of purchases and subscriptions (amount, date, plan).",
            "- Audit log: important account actions (sign-in, creation, deletion, payment).",
            ("stripe", "- Payment: card details are entered at Stripe and never pass through our servers; we only receive the payment status and identifiers."),
        ]),
        ("Purposes and legal bases", [
            "- Providing the requested service (performance of the contract).", "- Securing accounts and preventing abuse (legitimate interest).",
            "- Keeping accounting records (legal obligation): about 7 years.", "- Answering your requests (legitimate interest)."]),
        ("Processors and recipients", [
            "Data is not sold or used for advertising. It may be processed by:",
            "- {hosting} (hosting, region: {hosting_region}).",
            ("stripe", "- Stripe (payments)."),
            ("smtp", "- The configured e-mail provider (verification and password-reset e-mails)."),
            ("ai", "- Anthropic (AI-assisted reading, only if the option is enabled): document text may be sent to it to obtain the summary."),
            "If data is transferred outside the European Economic Area, appropriate safeguards (standard contractual clauses) must be in place: {todo}."]),
        ("Cookies", [
            "We use only two strictly necessary cookies, with no tracking or advertising:",
            "- « session »: keeps you signed in (12 hours).", "- « lang »: remembers your language (12 months).",
            "No consent is required for these functional cookies."]),
        ("Retention", [
            "Cases and documents are kept until the user deletes them or the account is closed. "
            "Billing records are kept for about 7 years. Files are stored encrypted."]),
        ("Your rights", [
            "You may ask for access, rectification, erasure, restriction, objection and portability of your data by writing to {email}. "
            "You may also lodge a complaint with the Belgian Data Protection Authority (www.dataprotectionauthority.be)."]),
    ],
    "terms": [
        ("Purpose", ["These terms govern the use of the « Belgian Immo Due Diligence » service published by {company}. By creating an account you accept them."]),
        ("The service", [
            "The service analyses property-file documents and flags points of attention. The result is a reading aid: it may be incomplete or wrong and must be checked. "
            "It does not replace a notary, a surveyor or legal advice. You remain responsible for your decisions.",
            "We aim to deliver a first report in under {minutes} minutes for a standard complete case. This target is not a guarantee: "
            "the time depends on the size and quality of the documents (scanned documents, optional AI reading) and on the load on the service."]),
        ("Account and access", [
            "Access is limited to authorised people (invitation-only registration). You are responsible for keeping your credentials confidential and for actions taken with your account."]),
        ("Your documents", [
            "You warrant that you have the right to upload the documents and, for third-party data, a legal basis to do so. We process them only to provide the service, see the privacy policy."]),
        ("Cases, credits and subscriptions", [
            "- One complete analysed case uses one credit or one case of the subscription quota.",
            "- Pay as you go: purchased credits are used to analyse cases; validity and refund of unused credits: {todo}.",
            "- Subscriptions (agent, agency): a monthly case quota, renewed every month on the anniversary date, not carried over. The plan can be paid monthly, every six months or yearly, with the discounts shown on the Pricing page.",
            "- The subscription renews automatically at the end of each period. You can cancel at any time from the billing portal; it stays active until the end of the paid period.",
            ("trial", "- Free trial: the subscriptions (agent, agency) can be tried for {trial_days} days, limited to {trial_dossiers} cases, once per organisation. A card is requested at the start; when the trial ends the subscription is charged automatically unless you cancel before that date from the billing portal."),
            "- Displayed prices are those of the Pricing page at the time of purchase."]),
        ("Right of withdrawal", [
            "Consumers have in principle 14 days to withdraw, except for digital content or a fully performed service with their prior express consent and acknowledgement that the right of withdrawal is lost. Applicable arrangements: {todo}."]),
        ("Liability", [
            "We are liable for our faults within the limits permitted by law. We do not guarantee the accuracy of results or uninterrupted availability. {todo}"]),
        ("Changes and termination", [
            "We may change these terms; the applicable version is the one in force on the date of acceptance, and material changes will be notified. You may delete your account at any time."]),
        ("Governing law", ["Belgian law. Belgian courts, subject to mandatory consumer protection rules."]),
    ],
}

TEXTS = {"fr": FR, "nl": NL, "en": EN}

TITLES = {
    "fr": {"legal": "Mentions légales", "privacy": "Politique de confidentialité", "terms": "Conditions générales"},
    "nl": {"legal": "Juridische vermeldingen", "privacy": "Privacybeleid", "terms": "Algemene voorwaarden"},
    "en": {"legal": "Legal notice", "privacy": "Privacy policy", "terms": "Terms and conditions"},
}
