*Synthèse stratégique • Marché • Produit • Concurrence • MVP • Pricing •
Go-to-market • Finances*

# 1. Executive summary

L'opportunité est forte : créer un SaaS de « property due diligence »
capable d'ingérer un dossier immobilier belge (acte, PEB/EPC, amiante,
électricité, urbanisme, copropriété, plans, etc.), d'extraire les faits,
de détecter les incohérences entre documents, d'identifier les risques
et de produire un rapport traçable avec citations aux pages sources.

Le produit ne doit pas être positionné comme un simple lecteur de PDF ou
comme un « avocat IA ». Le moat recherché est une combinaison de modèle
de données immobilier, moteur réglementaire régional, analyse
cross-document, scoring des risques, traçabilité et intégrations
professionnelles.

Verdict : potentiel startup ≈ 8,5/10. La Belgique est un excellent
marché de lancement ; l'ambition doit être européenne à terme.

# 2. Pourquoi maintenant ?

-   Le marché reste volumique : au T2 2026, les transactions de
    logements existants ont reculé de 11 % sur un an, mais représentent
    toujours un flux considérable de dossiers. Source : Statbel.

-   Les prix médians S1 2026 restent élevés : €285k pour maisons 2/3
    façades, €402,4k pour maisons 4 façades et €257k pour appartements
    en Belgique. Une meilleure due diligence peut donc avoir une valeur
    économique importante.

-   La réglementation est régionalisée (Flandre, Bruxelles, Wallonie),
    ce qui augmente la complexité mais crée une barrière à l'entrée.

-   En Flandre, l'EPC des parties communes et l'obligation
    d'asbestattest pour les parties communes des copropriétés montrent
    que le périmètre documentaire continue d'évoluer en 2026.

# 3. Produit cible

Promesse : « Upload the property documents → get the risks before the
buyer does. »

-   Upload multi-documents : acte, compromis, PEB/EPC, certificat
    amiante, contrôle électrique, sol, urbanisme, plans, copropriété,
    factures et photos.

-   OCR + classification automatique des documents.

-   Extraction vers un modèle structuré de la propriété.

-   Analyse cross-document : contradictions de surfaces, dates,
    extensions, installations, travaux, propriétaires, références
    cadastrales, etc.

-   Moteur réglementaire régional et règles de contrôle.

-   Property Risk Score : Legal / Urbanistic / Energy / Technical /
    Environmental / Documentation.

-   Rapport avec chaque conclusion reliée au document et à la
    page/extrait source.

-   Liste des documents manquants et questions à poser au notaire,
    vendeur ou syndic.

-   À terme : plan de rénovation, estimation des coûts, potentiel
    énergétique et aide à l'investissement.

# 4. Exemple de valeur

Exemple : l'acte mentionne 185 m², le PEB une extension de 32 m² et un
plan 240 m². Le SaaS ne se contente pas de résumer : il signale une
incohérence, indique les sources et recommande une vérification
urbanistique. C'est cette couche de raisonnement multi-document qui
différencie le produit d'un chatbot générique.

# 5. Clients prioritaires

-   1\. Agences et agents immobiliers : meilleur premier segment ;
    besoin fréquent, ROI facile à mesurer, volume de dossiers.

-   2\. Notaires : forte valeur et forte crédibilité, mais cycle de
    vente et exigences plus élevés.

-   3\. Investisseurs/promoteurs : excellent potentiel de panier moyen ;
    analyse rapide de nombreux dossiers.

-   4\. Syndics, experts et bureaux d'étude : extensions naturelles.

-   5\. Particuliers : gros marché mais CAC et support plus difficiles ;
    à traiter ensuite ou via un produit self-service.

# 6. Taille et logique économique du marché

L'IPI indique plus de 11 000 agents immobiliers en Belgique en 2026.
Même une pénétration de 10 % auprès d'environ 8 550 professionnels
orientés vente/location, à €100/mois, représenterait environ €85 500 de
MRR, soit \~€1,0 M ARR. Ce scénario n'est qu'un point de départ :
notaires, investisseurs, syndics et expansion géographique peuvent
multiplier le marché.

La bonne approche est bottom-up : nombre de professionnels ×
dossiers/mois × valeur par dossier, plutôt qu'un TAM « AI » théorique.

# 7. Concurrence et positionnement

Le marché belge n'est pas vierge. Cléa/ViaKompas se positionne déjà sur
la due diligence IA côté acheteur, avec analyse multi-documents et
détection proactive des risques. ImmoSpect, PlaceGenie et ImmoHabits
ciblent surtout les rapports/états des lieux et l'inspection. Cela
valide la demande pour l'IA immobilière, mais signifie qu'un produit
générique d'analyse de documents serait insuffisant.

-   Positionnement recommandé : « Belgian Property Due Diligence OS ».

-   Différenciation : priorité B2B, contrôle multi-documents, moteur
    réglementaire régional, audit trail, workflows d'agence/notaire, API
    et scoring propriétaire.

-   Ne pas concurrencer uniquement sur le résumé ou l'OCR.

# 8. Moat technologique

-   Faible moat : OCR, résumé LLM, chat PDF.

-   Moat moyen : extraction spécialisée par type de document.

-   Moat fort : base réglementaire belge structurée + cross-document
    reasoning.

-   Moat très fort : Property Knowledge Graph + historique des
    validations humaines + intégrations professionnelles.

-   Architecture : ingestion → OCR/classification → modèle immobilier
    structuré → regulatory engine → cross-document engine → risk engine
    → rapport avec preuves.

# 9. MVP recommandé

Ne pas démarrer avec toute la Belgique. MVP : Flandre, 4 documents :
EPC/PEB, acte, asbestattest, contrôle électrique.

-   Upload d'un dossier.

-   Détection et classement des 4 documents.

-   Extraction des champs clés.

-   10--20 contrôles de cohérence et risques.

-   Score global + scores par domaine.

-   Chaque finding doit pointer vers une page/extrait source.

-   Rapport PDF/Word exportable.

-   Historique, commentaires et validation humaine.

Objectif MVP : démontrer que le logiciel réduit fortement le temps de
revue et détecte des problèmes qu'un humain pressé peut manquer.

# 10. Pricing indicatif

-   Agent individuel : €79--149/mois avec quota de dossiers.

-   Agence : €299--599/mois, multi-utilisateurs, branding, rapports et
    intégrations.

-   Entreprise/notaire : €500--2 000+/mois selon volume, sécurité et
    workflow.

-   Usage/API : environ €2--10/document ou €20--50/dossier selon
    profondeur.

-   Particulier : achat ponctuel plutôt qu'abonnement, par exemple
    €29--99.

Tester le pricing avec des clients avant de figer les offres. La valeur
doit être ancrée sur le coût du temps économisé et surtout sur la
prévention d'un problème immobilier coûteux.

# 11. Go-to-market

-   Phase 1 : 10--20 agences pilotes en Flandre.

-   Mesurer : temps de revue avant/après, findings utiles, faux
    positifs, dossiers/mois et willingness-to-pay.

-   Créer des rapports anonymisés de démonstration et des cas réels de «
    contradiction détectée ».

-   Distribution : partenariats agences, réseaux immobiliers, experts,
    logiciels métier et notaires.

-   Phase 2 : Bruxelles + Wallonie et support NL/FR/EN.

-   Phase 3 : Luxembourg, France puis autres marchés européens, en
    adaptant le regulatory engine.

# 12. Risques et garde-fous

-   Ne pas présenter le produit comme un notaire, avocat, architecte ou
    expert agréé.

-   Human-in-the-loop pour les conclusions sensibles.

-   Traçabilité : source, page, extrait, règle utilisée, version de la
    réglementation.

-   RGPD, chiffrement, rétention configurable, séparation stricte des
    données clients.

-   Gestion de versions des règles par région et par date.

-   Le rapport doit distinguer fait extrait, inférence IA, risque
    potentiel et action recommandée.

Le contexte concurrentiel montre déjà ce positionnement prudent : des
solutions belges d'AI due diligence précisent qu'elles fournissent un
outil d'aide et non un conseil notarial/juridique. Il faut conserver
cette discipline.

# 13. Roadmap 12--18 mois

-   M0--2 : interviews + constitution d'un corpus anonymisé + 30
    contrôles prioritaires.

-   M2--4 : MVP Flandre + 5--10 clients pilotes.

-   M4--6 : scoring, rapports, dashboard, pricing payant.

-   M6--9 : copropriété, urbanisme, documents supplémentaires ;
    Bruxelles.

-   M9--12 : Wallonie, API, intégrations CRM/notaire.

-   M12--18 : rénovation/estimation coûts, investisseurs, expansion
    internationale.

# 14. Scénarios ARR

  -----------------------------------------------------------------------
  Scénario          Clients payants   ARPA moyen        ARR indicatif
  ----------------- ----------------- ----------------- -----------------
  Conservateur      300               €150/mois         €540k

  Traction          1 000             €220/mois         €2,64 M

  Scale Belgique    2 500             €300/mois         €9,0 M

  Europe            10 000            €350/mois         €42 M
  -----------------------------------------------------------------------

Ces scénarios sont des objectifs illustratifs, pas des prévisions. La
validation du taux de conversion, du churn, du coût d'acquisition et du
volume réel de dossiers est indispensable.

# 15. KPI à suivre

-   Time-to-first-report \< 2 minutes.

-   Temps humain économisé par dossier.

-   Findings pertinents / findings totaux.

-   Taux de faux positifs par type de règle.

-   Documents analysés par client/mois.

-   Conversion pilote → payant.

-   Net Revenue Retention et churn.

-   Coût LLM/OCR par dossier.

-   Part des rapports revus/validés par un professionnel.

-   Nombre de contradictions cross-document détectées.

# 16. Conclusion

Le potentiel est réel, mais la réussite dépend du niveau de
spécialisation. Le produit gagnant n'est pas « ChatGPT pour les actes
immobiliers » : c'est une infrastructure de due diligence immobilière
belge qui transforme des documents hétérogènes en faits structurés,
risques vérifiables et actions.

La meilleure stratégie est de lancer petit --- Flandre + 4 documents ---
puis d'élargir vers urbanisme, copropriété, rénovation et
investissement. La Belgique peut servir de laboratoire à forte
complexité réglementaire avant une expansion européenne.

# Sources clés

-   Statbel --- Real estate sales, Q2 2026.

-   Statbel --- Prix de l'immobilier, S1 2026.

-   Vlaanderen.be --- EPC des parties communes et asbestattest 2026.

-   IPI --- statistiques de la profession immobilière 2026.

-   Cléa / ViaKompas --- analyse concurrentielle du marché belge de due
    diligence IA.

-   ImmoSpect / PlaceGenie / ImmoHabits --- concurrence adjacente AI
    dans l'inspection immobilière.
