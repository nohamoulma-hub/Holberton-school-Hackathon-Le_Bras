# JOURNAL — travail avec l'IA

Ce journal retrace les principales décisions prises avec l'aide de l'IA pendant le développement de LE BRAS.

Il documente notamment les cas où une proposition de l'IA était incorrecte, incomplète ou inadaptée, ainsi que les corrections, refus et décisions prises par l'équipe.

## Entrées clés pour la livraison

| Entrée | Problème rencontré | Correction |
| --- | --- | --- |
| 7 | Clé Anthropic chargée trop tard | Chargement de `.env` corrigé |
| 10 | Trop de questions avant d'agir | Valeurs par défaut explicites |
| 12 | Contournement d'un Tool désactivé | Substitution interdite |
| 13 | Erreur JSON sur la boucle multi-Tools | Sérialisation corrigée |
| 18 | 5 actions proposées au lieu d'une | Distinction demande précise / vague |

## Entrée 1 — 2026-08-18, cadrage (palier 1)

Session avec l'agent pour produire `SPEC.md` : problème en 5 lignes, user stories, hors scope, schéma d'architecture, liste des outils avec signatures typées, happy path de démo, répartition du travail. L'agent a proposé une première version centrée sur un seul scénario (onboarding d'un stagiaire).

## Entrée 2 — 2026-08-18, généralisation du problème

Demandé à l'agent de généraliser la section "Le problème" : au lieu de ne traiter que le cas du stagiaire, l'agent devait couvrir plusieurs types de situations (onboarding, clôture de projet, préparation d'événement...). L'agent a répercuté ce changement sur l'ensemble du SPEC.md : user stories, outils (renommage `write_onboarding_record` → `write_record`, `generate_welcome_doc` → `generate_document`), schéma d'architecture, happy path. A aussi ajouté un item hors-scope précisant qu'il n'y a pas de catalogue métier codé en dur par scénario.

## Entrée 3 — 2026-08-18, socle back (palier 2)

Demandé à l'agent de construire le squelette back du palier 2 (objectif : un tuyau ouvert de bout en bout, avec un appel LLM réel visible à l'écran). Vu la répartition des tâches, l'agent a proposé de ne construire que le back (API + appel LLM), en laissant le front à Jo sur sa propre branche. Résultat : FastAPI (`app/main.py`) avec une route `/health` et une route d'appel LLM réel via l'API Anthropic (Claude Opus 5), `.env.example` + `.gitignore` pour ne jamais committer la clé API, README avec quickstart. Testé en local (serveur qui démarre, route qui répond) avant commit.

## Entrée 4 — 2026-08-18, alignement du contrat back/front

Jo a demandé un format d'entrée/sortie précis pour le chat (`POST /chat` avec `{"message": "..."}` en entrée, `{"response": "..."}` en sortie). Demandé à l'agent de renommer la route en conséquence (`/agent/ping` → `/chat`, champ `prompt` → `message`) et de retester l'appel LLM réel avec le nouveau format avant de committer. Fusion avec la branche `dev` de Jo (premier front HTML/CSS/JS) faite dans la foulée.

## Entrée 5 — 2026-08-18, accompagnement au lancement local

Difficulté à lancer et tester le serveur en local (confusion entre l'URL racine `/` et la doc interactive `/docs`, activation du venv, où placer la clé API). L'agent a détaillé les commandes pas à pas (`python3 -m venv .venv`, activation, `pip install -r requirements.txt`, `uvicorn app.main:app --reload`) et expliqué comment tester la route `/chat` via Swagger UI (`/docs`) et via `curl`, pour vérifier que l'appel LLM réel remonte bien à l'écran (exigence du checkpoint palier 2).

## Entrée 6 — 2026-08-18, fusion avec le front de Jo

Merge de la branche `dev` (Jo) apportant le premier front (HTML/CSS/JS) et le Dockerfile/docker-compose. Le front appelle `POST /chat` avec `{"message": "..."}` — contrat déjà aligné avec le back. `app/main.py` sert désormais le dossier `frontend/` en fichiers statiques sur `/`, en plus des routes API.

## Entrée 7 — 2026-08-18, premier outil réel (palier 3)

Demandé à l'agent de construire la boucle de tool calling pour le palier 3 : au moins deux outils réels branchés, choisis par le modèle lui-même (pas de routage `if "cherche" in message`), trace visible, gestion des erreurs d'outil. Résultat :
- `app/tools.py` : deux outils avec signature typée et description écrite pour le modèle — `create_issue` (insertion SQLite) et `send_message` (écriture d'un `.md` dans `/outbox/`). Exécution idempotente (clé = hash outil + input) et journalisée dans `audit_log`.
- `app/agent.py` : boucle avec le tool calling natif de l'API Claude (`tools=...`, pas de règle codée en dur). Chaque appel est chronométré et loggé.
- `app/main.py` : `/chat` renvoie `{"response": ..., "trace": [...]}` ; ajout de `GET /trace` pour montrer la séquence des appels sans ajouter de `print`.

Tests manuels validés : l'agent choisit le bon outil selon la demande, répond directement sans outil quand ce n'est pas pertinent, gère une entrée invalide sans planter (`ok: False` + message clair), et reste fonctionnel quand un outil est retiré de la liste (dit clairement qu'il n'y a plus accès au lieu d'halluciner un résultat).

Bug trouvé et corrigé en cours de route : `app/agent.py` créait le client Anthropic au chargement du module, mais `main.py` l'importait avant d'appeler `load_dotenv()` — la clé API n'était donc jamais chargée à temps, d'où des 500 systématiques sur `/chat`. Corrigé en rendant `agent.py` autonome sur le chargement de son `.env`.

**État à la fin de cette étape** : le panneau de trace et les métriques n'étaient pas encore dans le frontend ; ils ont été ajoutés lors de la finalisation décrite dans l'entrée suivante.

## Entrée 8 — 2026-08-18, finalisation du Palier 3

Demandé à l'agent de compléter les cinq outils manquants (`write_record`, `generate_document`, `create_calendar_event`, `list_pending_actions`, `undo_last_action`) sans réécrire la boucle Anthropic existante. Les nouvelles données sont stockées dans des tables SQLite créées sans supprimer l'existant ; les messages et documents restent dans `outbox/` et `files/`. Les sept outils sont désormais décrits et enregistrés, les résultats envoyés au LLM sont limités en taille tout en restant du JSON valide, et les tokens ainsi que la latence globale sont exposés sans inventer de tarif. L'idempotence distingue chaque action avec `plan_id`, `action_index`, Tool et arguments.

Pour éviter l'exécution silencieuse d'effets de bord, le choix retenu est une protection minimale : Claude crée une action `pending`, puis le backend ne l'exécute qu'après approbation explicite ; un refus ne déclenche aucun outil. La lecture des actions en attente reste immédiate. L'undo ne cible que les actions locales exécutées et réversibles et ne peut pas être appliqué deux fois. Le frontend affiche une trace repliable avec outil, arguments, statut, résultat ou erreur et latence, ainsi que les boutons d'approbation et de refus.

Tests effectués : 17 tests automatisés isolés couvrant les sept outils, la migration SQLite, les variantes de clé d'idempotence, approbation/refus, audit, erreur, undo, plusieurs `tool_use` et réponse sans outil ; construction Docker réussie ; vérification HTTP de `/health`, `/chat`, `/trace`, `/docs` et de l'interface. Des appels Claude réels ont aussi validé le hors périmètre (« Fais-moi un sandwich. »), une demande météo non anticipée, la question sur les capacités et une demande multi-outils restant en attente de validation.

## Entrée 9 — 2026-08-19, cadrage du prompt système et effort du modèle

Demandé à l'agent de reformuler le prompt système avec un cadre plus explicite (rôle, ce qu'il fait / ne fait jamais, ton) et de rendre l'effort du modèle réglable sans toucher au code. Résultat : `SYSTEM_PROMPT` restructuré en sections dans `app/agent.py` ; ajout de `AGENT_EFFORT` (low/medium/high/xhigh/max, défaut medium) lu depuis `.env` et passé en `output_config.effort` sur chaque appel.

Deux problèmes trouvés et corrigés pendant les tests :
- Le SDK Anthropic installé (0.68.0) ne supportait pas encore `output_config` : mis à jour vers 0.122.0.
- Le fichier `.env` ne se terminait pas par un retour à la ligne, donc un ajout précédent (`AGENT_EFFORT=medium` via `>>`) s'était collé à la fin de la ligne de la clé API, la rendant invalide (401 côté Anthropic). Corrigé en séparant proprement les deux lignes.

`AGENTS.md` mis à jour en conséquence (rôle/périmètre reformulés, nouvelle section Configuration).

## Entrée 10 — 2026-08-19, comportement face à une demande vague

Test manuel avec « Prépare l'arrivée de Jo » : l'agent posait 4 questions de clarification avant de proposer quoi que ce soit, ce qui ne correspond pas au happy path du SPEC (un plan d'actions affiché directement, à valider ou refuser). Décision prise avec l'utilisateur : l'agent doit toujours proposer un plan avec des valeurs par défaut explicites pour les champs manquants, plutôt que de bloquer sur des questions.

Ajout dans `SYSTEM_PROMPT` : proposer directement le plan le plus raisonnable avec des valeurs par défaut signalées comme telles, et toujours remplir les champs requis (y compris le contenu rédigé d'un document ou d'un message) avec un brouillon plutôt que de les laisser vides. Retest : la même demande produit désormais un plan de 6 actions en attente, avec les valeurs par défaut clairement listées dans la réponse.

Effet de bord observé (comportement stochastique du modèle, pas un bug de code) : sur certains runs, l'agent appelle un outil deux fois pour se corriger lui-même (un premier appel incomplet puis un second complet), et le signale explicitement à l'utilisateur en indiquant quelle action `pending` refuser. Accepté tel quel pour l'instant.

## Entrée 11 — 2026-08-19, rendu Markdown de la réponse dans le frontend

La réponse de l'agent contient du Markdown (gras, listes numérotées, tableaux) mais `app.js` l'affichait en texte brut (`textContent`), donc les `**...**` apparaissaient littéralement et les listes restaient sur une seule ligne. Demandé à l'agent de corriger l'affichage.

Ajout d'un petit convertisseur Markdown maison dans `app.js` (gras, code, listes, tableaux), sans dépendance externe pour rester fiable même sans connexion internet pendant une démo. Le texte est échappé avant mise en forme pour éviter toute injection HTML. Le conteneur `<p id="agent-response">` dans `index.html` a dû devenir un `<div>`, un `<p>` ne pouvant pas légalement contenir des listes ou tableaux. Styles ajoutés dans `style.css` pour la lisibilité.

## Entrée 12 — 2026-08-19, débrancher un outil en direct (palier 3)

Reformulé l'exigence du palier 3 « je débranche un outil et je relance la même requête » avec l'utilisateur : d'abord une variable `DISABLED_TOOLS` dans `.env` rechargée à chaque appel, puis remplacée par un état en mémoire piloté depuis un vrai panneau du front (cases à cocher par outil, `GET /tools`, `POST /tools/{nom}/toggle`), pour ne rien avoir à éditer en live devant le jury. Testé : désactivation de `create_issue` sans redémarrer le serveur, l'agent ne plante pas, réactivation confirmée.

Ajustement de comportement demandé ensuite : l'agent contournait un outil indisponible en utilisant un autre outil pour arriver à un résultat proche (ex. `write_record` à la place de `create_issue`). Ce n'est pas ce qui était voulu : ajout d'une règle explicite dans `SYSTEM_PROMPT` pour qu'il dise clairement que l'action précise n'est pas disponible, sans chercher de solution de repli. Retesté avec `create_issue` désactivé : trace vide, refus explicite, sans contournement.

Sur demande de l'utilisateur, suppression du tiret cadratin (« — ») du langage de l'agent (ajout dans `SYSTEM_PROMPT`) et des quelques occurrences codées en dur côté frontend.

## Entrée 13 — 2026-08-19, palier 4 : boucle fermée de bout en bout

Jo a fait évoluer le projet en parallèle avec de gros changements d'architecture : migration SQLite vers PostgreSQL, comptes utilisateurs avec sessions par cookie, historique des conversations et des actions acceptées, vue calendrier, persistance des plans (`app/plans.py`, `app/accounts.py`, `app/history.py`, `app/calendar_events.py`). Demandé à l'agent de lire ces changements, de faire tourner l'ensemble en local (PostgreSQL installé et configuré faute de démon Docker disponible), et de valider le palier 4 (happy path des 6 étapes du palier 1, persistance après rechargement, l'agent qui enchaîne plusieurs tours d'outils, garde-fou contre la boucle infinie).

Deux bugs critiques trouvés et corrigés :
- Même famille de bug que lors du palier 2 (déjà rencontré) : `app/db.py` lisait `DATABASE_URL` au chargement du module, avant que `.env` soit chargé, à cause de l'ordre des imports dans `agent.py`. Corrigé en lisant la variable à chaque appel plutôt qu'une fois pour toutes, et en déplaçant `load_dotenv()` avant les imports internes.
- Bug plus grave : dès que l'agent enchaînait deux outils dans le même appel (ex. `create_issue` puis `list_pending_actions`), le serveur renvoyait une 500 (`datetime is not JSON serializable`) au moment de journaliser l'appel dans `audit_log`. Cassait exactement le scénario « l'agent itère » exigé par ce palier. Corrigé (conversion `isoformat()` de la date dans `list_pending_actions`, et `default=str` sur les sérialisations JSON restantes dans `tools.py`).

Test complet des 6 étapes du happy path via l'API (simulant le navigateur, avec compte utilisateur) : intention → plan de 6 actions (dont un doublon incomplet que l'agent a lui-même détecté et signalé à refuser) → approbation de 5 / refus de 1 → exécution réelle → journal consultable (`GET /history/accepted-actions`) → annulation d'une action exécutée avec suppression réelle du fichier associé. Persistance vérifiée via `GET /plans/latest` (le frontend garde le `plan_id` courant en `localStorage` et le restaure au chargement). L'agent itère bien sur plusieurs tours dans un même appel, démontré deux fois (`create_issue` → `list_pending_actions`, puis `list_pending_actions` → `undo_last_action`). Garde-fou localisé : `MAX_TOOL_ITERATIONS = 4` (`app/agent.py`), utilisé dans la boucle `for _ in range(MAX_TOOL_ITERATIONS):`.

Limite identifiée et acceptée telle quelle : demander d'annuler « la dernière action » sans préciser son identifiant ne fonctionne pas, chaque appel `/chat` étant indépendant (nouveau `plan_id`, pas de mémoire des tours précédents). L'agent répond alors honnêtement qu'il n'a rien à annuler plutôt que d'halluciner. Fonctionne en revanche en citant l'`action_id` affiché dans le panneau de trace du front (ex. « annule l'action 13 »).

## Entrée 14 — 2026-08-19, consolidation finale du Palier 4

Après synchronisation de `dev` dans `dev_john`, nouvelle campagne sur Docker avec PostgreSQL. Les corrections de Noham sur l'ordre de chargement de `.env`, la sérialisation de `list_pending_actions`, le passage à `claude-sonnet-5` et le calcul du coût estimé ont été conservées. La suite existante a d'abord nécessité une adaptation de son schéma PostgreSQL temporaire afin de suivre la lecture dynamique de `DATABASE_SCHEMA` sans réintroduire une constante figée dans le backend.

Le défaut bloquant restant était la création d'actions `pending` à partir d'arguments incomplets. Une validation générique fondée sur les `input_schema` de `TOOL_DEFINITIONS` contrôle désormais les champs requis, les types, les formats, les bornes et `additionalProperties` avant toute insertion dans `actions`, sans appeler l'implémentation du Tool. L'erreur est auditée puis renvoyée à Claude comme `tool_result` en erreur, ce qui lui permet de se corriger au tour suivant. Le prompt a aussi été précisé de façon générique pour examiner tous les Tools pertinents, et la capacité de sortie a été relevée afin de ne pas tronquer un plan multi-actions.

Le frontend se resynchronise maintenant avec `GET /plans/{plan_id}` après un échec d'approbation et affiche immédiatement le statut PostgreSQL réel. La trace montre explicitement `action_id` et `action_index` ; après F5, elle indique que la latence n'est pas disponible au lieu d'inventer `0 ms`. Les descriptions actuelles des Tools parlent toutes de PostgreSQL. Enfin, `files/` et `outbox/` disposent de volumes Docker dédiés, ce qui conserve les documents et messages après recréation du conteneur et permet encore leur annulation après redémarrage.

Quinze tests de non-régression ont été ajoutés. Avec les tests existants sur les comptes, historiques, calendrier, outils, plans et F5, la suite compte 43 tests PostgreSQL isolés et passe intégralement. `SPEC.md` et `README.md` ont été alignés sur l'architecture REST actuelle, les comptes, les statuts réels, le calendrier, la persistance des plans, les volumes et Claude Sonnet 5, sans modifier les entrées historiques qui décrivent légitimement l'ancienne étape SQLite.

## Entrée 15 — 2026-08-19, suppression des événements du calendrier

Ajout d'un bouton Supprimer sur chaque événement affiché, avec confirmation explicite avant l'appel `DELETE /calendar/events/{event_id}`. Le backend supprime la ligne PostgreSQL, marque l'action `create_calendar_event` correspondante comme `cancelled`, actualise son audit et recalcule le statut du plan. Deux tests couvrent la suppression complète et le cas d'un identifiant inconnu ; la suite compte désormais 45 tests.

## Entrée 16 — 2026-08-19, isolation des comptes et traces anonymes

Correction d'une fuite fonctionnelle du calendrier : un compte connecté ne voit et ne peut désormais supprimer que les événements rattachés à ses propres actions via `action_owners`. Un visiteur non connecté ne reçoit que les événements des plans dont les identifiants aléatoires sont mémorisés dans le `localStorage` de son navigateur. Les mêmes plans locaux alimentent maintenant les historiques de conversations et de tâches acceptées sans forcer une connexion.

Ajout de `DELETE /history/accepted-actions/{action_id}` et d'un bouton « Supprimer de l'historique ». Ce retrait masque uniquement la ligne pour son propriétaire grâce à `action_owners.hidden_at`, sans annuler l'effet métier ni retirer l'autorisation sur un événement associé. Trois tests supplémentaires couvrent le masquage, l'interdiction d'agir sur l'historique d'un autre compte et l'isolation du calendrier ; la suite compte 48 tests.

## Entrée 17 — 2026-08-19, changement de modèle et coût affiché (bonus palier 3)

Demandé à l'agent de basculer de `claude-opus-5` vers `claude-sonnet-5` (moins cher, jugé suffisant pour ce projet), et de compléter le bonus « coût affiché » resté à `estimated_cost: null` depuis le palier 3. Ajout de `INPUT_PRICE_PER_MILLION_USD`/`OUTPUT_PRICE_PER_MILLION_USD` (tarif Sonnet 5 : $3/$15 par million de tokens) dans `app/agent.py`, calcul du coût réel à partir des tokens consommés à chaque appel, et affichage dans le panneau de métriques du front au lieu de « coût non configuré ». Testé en réel : coût cohérent avec les tokens facturés.

## Entrée 18 — 2026-08-20, palier 5 : éval manuelle et bug de sur-déclenchement

Demandé à l'agent d'expliquer le principe d'un eval avant de le construire (jamais fait auparavant), puis de rédiger `eval/cases.md` avec plus de 5 cas, dont plusieurs sur l'injection de prompt comme demandé explicitement. Neuf cas définis et rejoués un par un contre l'agent réel via `/chat` : sélection d'outil correcte, demande vague avec valeurs par défaut, refus hors périmètre, outil désactivé sans contournement, itération multi-outils, erreur d'outil gérée proprement, deux tentatives d'injection (contournement de la validation humaine, exfiltration du prompt système), absence de régression sur le tiret cadratin.

Un vrai bug trouvé en cours de route, pas anticipé : sur une demande d'une seule action entièrement précisée, l'agent proposait quand même 5 actions (message, fiche, document, événement inventés en plus de la tâche demandée). Cause identifiée : deux lignes du `SYSTEM_PROMPT` ("examiner tous les outils disponibles...", "pour une préparation ou une coordination complexe, vérifier séparément...") poussaient le modèle à toujours considérer les 5 types d'action dès qu'un mot comme « préparer » apparaissait, même sur une demande déjà précise. Corrigé en distinguant explicitement « demande précise » (ne faire que ce qui est demandé) et « demande vague » (compléter avec des valeurs par défaut, cas déjà couvert). Retest du cas corrigé et du cas de demande vague (non-régression) : les deux passent. Score final : 9/9.

## Entrée 19 — 2026-08-20, éval automatisée (bonus palier 5)

Construit `eval/run_eval.py` et un `Makefile` (`make eval`) pour rejouer automatiquement les 9 cas de `eval/cases.md` : appel direct à `run_agent` (pas besoin du serveur HTTP), vérification structurelle par cas (outils appelés, statuts, mots-clés), score chiffré affiché à la fin, code de sortie 0/1. Testé : `make eval` → 9/9 en une commande.

Question posée séparément : est-ce que l'exigence « au moins un test automatisé qui a une vraie valeur, sur la boucle ou sur un outil » était déjà remplie ? Vérification faite : oui, doublement. `tests/test_palier4_regressions.py::test_agent_guard_stops_after_four_tool_iterations` (Jo) mock l'API Claude pour forcer une boucle et vérifie l'arrêt exact après `MAX_TOOL_ITERATIONS`, en 1,4s, sans appel réel ; et les cas 5/6 de l'éval testent la boucle et un outil en conditions réelles (non mockées). Rien à ajouter sur ce point.
