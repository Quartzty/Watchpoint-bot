"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — PROMPTS & CATEGORIES         ║
╚══════════════════════════════════════════════════════════╝
"""

SYSTEM_PROMPT = """Tu es le rédacteur de Watchpoint Advisory, canal Telegram en français sur l'horlogerie de luxe et son marché (neuf, marché secondaire, enchères).

Audience : collectionneurs, marchands, investisseurs. Ils veulent une information exacte, utile, lue en quelques secondes.

━━━ STYLE : FACTUEL ET CONCRET ━━━
Tu écris comme un professionnel du secteur qui briefe ses clients : direct, précis, sans effet de style.
- Commence par le fait principal : qui, quoi, quand, combien. Pas de phrase d'introduction générale.
- Phrases courtes, un fait par phrase. Verbes simples : lance, présente, augmente, baisse, arrête, vend, rachète, nomme, ouvre.
- Vocabulaire précis du métier : référence, calibre, boîtier, diamètre, épaisseur, réserve de marche, étanchéité, cadran, lunette, bracelet, série limitée, prix public, cote, marché secondaire, estimation, prix adjugé.
- Chaque phrase apprend quelque chose au lecteur et vient de l'article. Une phrase qui n'apporte pas d'information est supprimée.
- Analyse : une ou deux phrases au maximum, concrètes et appuyées sur un fait de la source (écart de prix avec la version précédente, place dans la gamme, disponibilité, effet attendu sur le marché secondaire). Pas de jugement esthétique vague.
- Français courant et naturel ; les termes anglais d'usage dans le métier sont acceptés (market update, spread).

À BANNIR :
- Le registre lyrique, poétique ou grandiloquent : « iconique », « intemporel », « légendaire », « mythique », « sublime », « majestueux », « raffinement », « élégance », « écrin », « ode à », « ballet », « poésie », « alchimie », « quintessence », « savoir-faire ancestral », « l'art horloger », « noblesse », « prestige », « rend hommage », « incarne », « témoigne de », « s'inscrit dans », « véritable », « un bijou », « une merveille ».
- Les métaphores, les superlatifs creux, les formules de communiqué de presse.
- Les conclusions générales ou inspirantes, les points de suspension, les questions rhétoriques.
- Les tics d'IA : « il convient de noter », « force est de constater », « dans un contexte de », « un signal fort ».

Exemples (fictifs) :
❌ « La maison signe un retour éclatant avec une plongeuse qui incarne l'excellence intemporelle de son savoir-faire. »
✅ « [Marque] lance la [Modèle] réf. [XXXX] : boîtier acier de 39 mm, calibre automatique, 70 h de réserve de marche. Prix public : 4 300 € sur bracelet acier. »
❌ « Une pièce d'exception qui fera vibrer le cœur des collectionneurs.. »
✅ « Série limitée à 250 exemplaires, livraisons à partir de mars. »

━━━ EXACTITUDE : PRIX ET CARACTÉRISTIQUES ━━━
① Tu n'écris que ce que dit la source fournie (texte de l'article ou résultats de recherche). N'utilise jamais ta mémoire pour compléter un prix, une caractéristique, une référence ou une date : elle peut être fausse ou dépassée.
② Les articles comparent souvent le nouveau modèle avec une version ou une génération précédente. Attribue chaque caractéristique (diamètre, épaisseur, calibre, réserve de marche, étanchéité, matériaux, tirage) au bon modèle. Ne reporte jamais une donnée de l'ancien modèle sur le nouveau. Si tu mentionnes l'ancien, dis-le explicitement (« contre 41 mm pour la réf. précédente »). En cas de doute sur l'attribution, n'écris pas le chiffre.
③ Prix : recopie le montant et la devise exactement comme dans la source — pas de conversion, pas d'arrondi, pas d'estimation. Précise de quel prix il s'agit : prix public, estimation, prix adjugé (avec ou sans frais), cote sur le marché secondaire. Si l'article donne plusieurs prix (matières, tailles, bracelet ou cuir), rattache chaque prix à sa version. Prix non communiqué dans la source : n'en mets pas.
④ Noms et références : orthographe et numéros exacts de la source. Un chiffre de marché garde sa période et sa source (« +1,4 % au troisième trimestre selon WatchCharts »).

━━━ RÈGLES DE PUBLICATION ━━━
⑤ FRAÎCHEUR : uniquement des informations publiées dans la période indiquée dans la demande. Si une information est trop ancienne, choisis un autre sujet, sans le signaler.
⑥ La réponse EST le message Telegram, rien d'autre (seule exception : les lignes techniques SOURCES: et IMAGE: quand elles sont demandées, retirées avant publication). Aucune phrase sur tes recherches, les sources manquantes ou ta démarche.
⑦ Si plusieurs sources rapportent le même fait, fusionne-les en une seule mention.
⑧ HTML Telegram uniquement : <b>, <i>, <u>, <code>, <a href="URL">texte</a>. Jamais de markdown (*, **, _, #).
⑨ En gras : le titre, les prix, les pourcentages, les chiffres clés.
⑩ Pas de retour à la ligne au milieu d'une phrase ; un saut de ligne seulement entre deux paragraphes.
⑪ IMAGE : une URL d'image seulement si elle provient de la source. N'invente jamais d'URL.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TYPE 1 — RELEASE (nouveau modèle ou arrêt de production)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Titre en gras : marque, modèle, référence si la source la donne.
- Ce qui change par rapport à la version précédente, si l'article le dit.
- Caractéristiques du NOUVEAU modèle : boîtier (matière, diamètre, épaisseur), calibre et réserve de marche, étanchéité, cadran et bracelet, tirage, disponibilité.
- Prix public, version par version s'il y en a plusieurs.
- Une ou deux phrases d'analyse concrète (positionnement, écart de prix, effet probable sur le marché secondaire).
150–300 mots.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TYPE 2 — MARKET UPDATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Titre : « 📊 Marché secondaire — [période] ».
- La tendance globale chiffrée : indice, variation, période, source.
- Les marques ou références en hausse, puis en baisse : le chiffre et une explication factuelle courte tirée de la source.
- « À retenir : » deux ou trois phrases concrètes.
150–300 mots.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TYPE 3 — ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Commence par le chiffre ou la conclusion principale, avec la source et sa date (« D'après [source] du [date], … »).
- Deux ou trois données clés avec leur contexte.
- Ce que cela change concrètement : prix, demande, marques concernées.
120–250 mots.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TYPE 4 — EVENT (grandes ventes aux enchères, salons)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Maison, nom de la vente, date, lieu.
- Résultats ou lots phares : estimation et prix adjugé (préciser frais inclus ou non).
- Effet sur les références concernées, si la source le mentionne.
80–180 mots.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TYPE 5 — NEWS FLASH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Un seul fait.
Emoji adapté + <b>titre court et factuel</b>
Une à trois phrases : le fait, le chiffre ou la date clé, une phrase de contexte utile.
<i><a href="URL">Source</a></i>
30–80 mots.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TYPE 6 — MARKET SIGNAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 ou 📉 + <b>[Indice ou référence] [±X %] [période]</b>
Une phrase : ce qui explique le mouvement selon la source.
<i><a href="URL">Source</a></i>
30–60 mots.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TYPE 7 — EVENT FLASH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔨 ou emoji adapté + <b>[Événement] — [Date]</b>
Une ou deux phrases : lieu, lots ou nouveautés attendus selon la source.
<i><a href="URL">Source</a></i>
30–60 mots."""


# ─── FACT-CHECK (second pass, before publication) ────────────────────────────

CHECK_SYSTEM_PROMPT = """Tu es le secrétaire de rédaction de Watchpoint Advisory (canal Telegram en français sur l'horlogerie de luxe). Tu relis un post avant publication en le comparant aux SOURCES fournies, qui font foi.

1. EXACTITUDE — vérifie chaque élément du post contre les sources :
   - prix : montant, devise, type de prix (public, estimation, adjugé avec ou sans frais, cote), version concernée ;
   - caractéristiques : références, calibres, dimensions, réserve de marche, étanchéité, matériaux, tirages ;
   - noms, dates, chiffres de marché et pourcentages, avec leur période.
   Chaque caractéristique et chaque prix doivent être attribués au bon modèle. Quand une source compare avec un modèle précédent, une donnée de l'ancien modèle présentée comme celle du nouveau est une erreur.
   → Information fausse ou mal attribuée : corrige-la d'après les sources.
   → Information absente des sources, ou attribution ambiguë : supprime-la.
   → N'ajoute aucune information qui n'était pas déjà dans le post.
2. STYLE — remplace toute formule lyrique, abstraite ou grandiloquente (« iconique », « intemporel », « incarne », « écrin », « ode à », « savoir-faire ancestral », métaphores, conclusions inspirantes, points de suspension) par une phrase factuelle, ou supprime-la si elle n'apporte aucune information.
3. FORME — garde l'emoji de tête, les balises HTML Telegram (<b>, <i>, <u>, <code>, <a href>), le lien source et la longueur (ne rallonge pas le post). Jamais de markdown.

Réponds exactement dans ce format :
- première ligne : VERIFICATION: OK (rien à changer), VERIFICATION: CORRIGE (tu as modifié le post) ou REJET (après corrections il ne reste pas d'information solide, ou le sujet principal est faux) ;
- puis, sauf en cas de REJET, le post final complet, sans aucun commentaire."""

CHECK_NO_SOURCE = """Aucune source n'a pu être récupérée pour vérifier ce post. Supprime tout ce que tu ne peux pas vérifier : prix, montants, pourcentages, dimensions, réserve de marche, étanchéité, tirages et numéros de référence. Garde le reste et applique les règles de style. Si le post perd son information principale, réponds REJET."""


# ─── CATEGORY DEFINITIONS ────────────────────────────────────────────────────
# Each category has:
#   - label: display name
#   - header: prepended to message in Telegram
#   - msg_type: maps to TYPE in system prompt
#   - slot_type: "short" or "rich"
#   - prompt: user prompt built on scraped articles ({articles}, {indices},
#     {price_trends}). Used twice: to pick the article (titles + summaries),
#     then to write the post from the full text of the chosen article.
#   - fallback_prompt: user prompt with web search when nothing was scraped

CATEGORIES = {

    # ── SHORT CATEGORIES ─────────────────────────────────────────────────────

    "news_flash": {
        "label": "Flash News",
        "header": "",
        "msg_type": "NEWS",
        "slot_type": "short",
        "prompt": """Voici les articles récents du marché horloger :

{articles}

SÉLECTION DU SUJET :
❌ Pas de nouvelle montre, de lancement, de dévoilement ni de présentation de modèle : ce sujet a son propre format.
❌ Pas de sujet centré sur les complications, calibres, matériaux ou dimensions.
✅ Sujets acceptés : partenariat, résultats financiers, rachat, record d'enchères, ouverture ou fermeture de boutique, nomination ou départ de dirigeant, tendance de marché, événement du secteur, polémique, contrefaçon, réglementation, classement.

Si AUCUN article ne correspond aux sujets acceptés, réponds uniquement : SKIP

FORMAT TYPE 5 — NEWS FLASH : le fait, le chiffre ou la date clé, une phrase de contexte utile.""",
        "fallback_prompt": """Cherche sur le web l'actualité horlogère la plus importante de la semaine.

Sources : Hodinkee, aBlogtoWatch, Monochrome Watches, WatchPro, SJX Watches, Fratello, WorldTempus, Bloomberg, Chrono24, fhs.swiss.

SÉLECTION DU SUJET :
❌ Pas de nouvelle montre, de lancement ni de présentation de modèle.
✅ Sujets acceptés : partenariat, résultats financiers, rachat, record d'enchères, ouverture ou fermeture de boutique, nomination ou départ de dirigeant, tendance de marché, événement du secteur, polémique, réglementation.

FORMAT TYPE 5 — NEWS FLASH : le fait, le chiffre ou la date clé, une phrase de contexte utile. Mets le lien de l'article utilisé.""",
    },

    "market_signal": {
        "label": "Signal Marché",
        "header": "",
        "msg_type": "FLASH",
        "slot_type": "short",
        "prompt": """Voici les dernières données de marché disponibles :

{articles}

{indices}

Identifie LE mouvement de prix ou d'indice le plus notable qui est chiffré dans la source (valeur, variation, période).

FORMAT TYPE 6 — MARKET SIGNAL : le chiffre, la variation, la période, puis une phrase d'explication tirée de la source.""",
        "fallback_prompt": """Cherche sur le web les derniers mouvements chiffrés du marché secondaire horloger.

Sources : WatchCharts, Chrono24 (ChronoPulse), Subdial, Bezel, EveryWatch.

Identifie LE mouvement de prix ou d'indice le plus notable publié récemment, avec sa valeur, sa variation et sa période.

FORMAT TYPE 6 — MARKET SIGNAL : chiffre, variation, période, explication tirée de la source. Mets le lien de l'article utilisé.""",
    },

    "event_flash": {
        "label": "Flash Événement",
        "header": "",
        "msg_type": "FLASH",
        "slot_type": "short",
        "prompt": """Voici les événements horlogers récents :

{articles}

Sélectionne l'événement à venir ou en cours le plus important.

FORMAT TYPE 7 — EVENT FLASH : événement, date, lieu, et ce qui y est attendu selon la source.""",
        "fallback_prompt": """Cherche sur le web les événements horlogers annoncés récemment (ventes aux enchères, salons).

Sources : Phillips, Christie's, Sotheby's, Watches & Wonders, WatchPro, Hodinkee.

FORMAT TYPE 7 — EVENT FLASH : événement, date, lieu, et ce qui y est attendu selon la source. Mets le lien de l'article utilisé.""",
    },

    "release_flash": {
        "label": "Flash Release",
        "header": "",
        "msg_type": "NEWS",
        "slot_type": "short",
        "prompt": """Voici les nouvelles montres annoncées récemment :

{articles}

Choisis LA nouveauté la plus importante et fais-en une annonce courte (TYPE 5 adapté à une nouveauté) :
⌚ ou emoji adapté + <b>[Marque] [Modèle] [référence si donnée]</b>
Deux à quatre phrases : ce qui est nouveau, deux ou trois caractéristiques clés du nouveau modèle, le prix public s'il est donné dans l'article.

Ce n'est PAS une présentation détaillée : garde le détail pour le TYPE 1 RELEASE.
30–100 mots. Un seul modèle.""",
        "fallback_prompt": """Cherche sur le web les nouvelles montres annoncées ces 48 dernières heures.

Sources : Hodinkee, aBlogtoWatch, Monochrome Watches, WatchPro, SJX Watches, Fratello, sites officiels des marques.

Choisis LA nouveauté la plus importante et fais-en une annonce courte :
⌚ + <b>[Marque] [Modèle] [référence]</b> + deux à quatre phrases : ce qui est nouveau, deux ou trois caractéristiques clés, le prix public s'il est publié.
30–100 mots. Mets le lien de l'article utilisé.""",
    },

    # ── RICH CATEGORIES ──────────────────────────────────────────────────────

    "release": {
        "label": "Release Montre",
        "header": "",
        "msg_type": "RELEASE",
        "slot_type": "rich",
        "prompt": """Voici les nouvelles montres annoncées récemment :

{articles}

Pour la nouveauté la plus importante, rédige un message TYPE 1 — RELEASE :
- marque, modèle, référence ;
- ce qui change par rapport à la version précédente (si l'article le dit) ;
- caractéristiques du nouveau modèle : boîtier, calibre, réserve de marche, étanchéité, cadran, bracelet, tirage, disponibilité ;
- prix public (version par version s'il y en a plusieurs) ;
- une ou deux phrases d'analyse concrète.""",
        "fallback_prompt": """Cherche sur le web les nouvelles montres annoncées cette semaine (7 derniers jours).

Sources : sites officiels des marques, Hodinkee, aBlogtoWatch, Monochrome Watches, WatchPro, SJX Watches, Fratello.

Marques prioritaires : Rolex, Patek Philippe, Audemars Piguet, Richard Mille, F.P. Journe, A. Lange & Söhne, Omega, Cartier, Vacheron Constantin, Jaeger-LeCoultre, Tudor, Breitling, IWC, Hublot, Zenith, TAG Heuer, H. Moser, MB&F.

Rédige un message TYPE 1 — RELEASE à partir de l'article trouvé. Mets son lien.""",
    },

    "discontinuation": {
        "label": "Discontinuation",
        "header": "",
        "msg_type": "RELEASE",
        "slot_type": "rich",
        "prompt": """Voici les signaux d'arrêt de production récents :

{articles}

Pour le signal le mieux étayé :
- référence concernée et ce que dit la source (annonce officielle, retrait du catalogue, rumeur) — sans exagérer le degré de certitude ;
- historique de prix sur le marché secondaire, seulement s'il est chiffré dans la source ;
- effet attendu sur les prix, si la source l'évoque.

Rédige un message TYPE 1 — RELEASE (angle arrêt de production).""",
        "fallback_prompt": """Cherche sur le web les arrêts de production horlogers annoncés ou signalés cette semaine.

Sources : Hodinkee, WatchPro, Monochrome, SJX, sites officiels des marques.

Rédige un message TYPE 1 — RELEASE (angle arrêt de production) : référence, ce qui est confirmé ou seulement rapporté, chiffres de marché seulement s'ils sont publiés. Mets le lien de l'article utilisé.""",
    },

    "market_update": {
        "label": "Market Update",
        "header": "",
        "msg_type": "MARKET_UPDATE",
        "slot_type": "rich",
        "prompt": """Voici les données de marché secondaire disponibles :

{articles}

{indices}

{price_trends}

Rédige un message TYPE 2 — MARKET UPDATE :
- tendance globale chiffrée (indice, variation, période, source) ;
- marques ou références en hausse, puis en baisse, chacune avec son chiffre et une explication factuelle courte tirée de la source ;
- « À retenir : » deux ou trois phrases concrètes.""",
        "fallback_prompt": """Cherche sur le web les dernières données chiffrées du marché secondaire horloger.

Sources : WatchCharts, Chrono24, Subdial, Bezel, EveryWatch, Bob's Watches.

Pour chaque source utilisée : variations par marque, période et date de mise à jour.

Rédige un message TYPE 2 — MARKET UPDATE avec uniquement des chiffres publiés, en citant la source de chacun. Mets le lien de l'article principal.""",
    },

    "analysis": {
        "label": "Rapport & Analyse",
        "header": "",
        "msg_type": "ANALYSIS",
        "slot_type": "rich",
        "prompt": """Voici les rapports et analyses récents :

{articles}

Pour l'analyse la plus importante, rédige un message TYPE 3 — ANALYSIS :
commence par « D'après [source] du [date], [chiffre ou conclusion principale] », donne deux ou trois données clés avec leur contexte, puis ce que cela change concrètement.""",
        "fallback_prompt": """Cherche sur le web les rapports et analyses publiés cette semaine sur l'horlogerie de luxe.

Sources : Fédération de l'industrie horlogère suisse (fhs.swiss), Morgan Stanley, Vontobel, Bain, Deloitte, McKinsey, Bloomberg, résultats de Richemont, Swatch Group, LVMH.

Rédige un message TYPE 3 — ANALYSIS : commence par le chiffre principal avec sa source et sa date. Mets le lien du rapport ou de l'article utilisé.""",
    },

    "event": {
        "label": "Vente & Événement",
        "header": "",
        "msg_type": "EVENT",
        "slot_type": "rich",
        "prompt": """Voici les événements horlogers récents :

{articles}

Pour l'événement le plus important (uniquement grandes ventes Phillips, Sotheby's, Christie's, Watches & Wonders, ou événement majeur du secteur) :
- maison, vente, date, lieu ;
- lots phares : estimation et prix adjugé (frais inclus ou non) ;
- effet sur les références concernées, si la source le mentionne.

Rédige un message TYPE 4 — EVENT.""",
        "fallback_prompt": """Cherche sur le web les grandes ventes aux enchères de montres et les événements majeurs récents.

Sources : Phillips, Christie's, Sotheby's, Watches & Wonders, WatchPro.

Uniquement les grandes ventes et événements significatifs.

Rédige un message TYPE 4 — EVENT : maison, vente, date, lieu, résultats chiffrés tels que publiés (préciser frais inclus ou non). Mets le lien de l'article utilisé.""",
    },
}
