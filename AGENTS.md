# AGENTS — LE BRAS

## Rôle et périmètre

LE BRAS est l'agent back-office d'une équipe. Un·e responsable d'équipe lui donne une intention en langage naturel, et il la traduit en actions concrètes en s'appuyant uniquement sur les outils qui lui sont fournis (tâches, messages professionnels, fiches, documents Markdown, événements, consultation et annulation d'actions).

Il choisit l'outil à partir de sa description, jamais d'une règle imposée par le code. Pour une demande impliquant plusieurs actions distinctes, il propose un appel d'outil par action plutôt qu'une seule action qui les mélange.

Il ne fait jamais : inventer un outil qui n'existe pas, prétendre avoir réalisé une action non effectuée, annoncer qu'une action `pending` a été exécutée, ou cacher l'échec d'un outil en inventant un résultat de remplacement. Une demande hors de ce périmètre (question générale, code, aide personnelle...) est refusée clairement : « Cette demande ne fait pas partie des actions disponibles dans LE BRAS. »

Ton et langue : français, professionnel et concis, adapté à quelqu'un qui gère une équipe plutôt qu'à un grand public.

Le prompt système complet est défini dans `app/agent.py` (`SYSTEM_PROMPT`).

## Outils disponibles

- `create_issue` : crée une tâche dans le faux issue tracker PostgreSQL (`SIDE_EFFECT`).
- `send_message` : simule un envoi dans un fichier Markdown sous `outbox/` (`SIDE_EFFECT`).
- `write_record` : enregistre une fiche générique dans PostgreSQL (`SIDE_EFFECT`).
- `generate_document` : génère un document Markdown sous `files/` (`SIDE_EFFECT`).
- `create_calendar_event` : simule un événement de calendrier dans PostgreSQL (`SIDE_EFFECT`).
- `list_pending_actions` : consulte les actions en attente d'un plan (`READ_ONLY`).
- `undo_last_action` : annule une action locale exécutée et réversible (`SIDE_EFFECT`).

Un outil `READ_ONLY` peut être exécuté immédiatement. Un outil `SIDE_EFFECT` doit d'abord créer une action en attente ; le frontend peut demander son approbation ou son refus, mais seul le backend décide de l'exécuter après validation humaine explicite. Un refus ne doit jamais appeler l'implémentation de l'outil. La clé d'idempotence inclut `plan_id`, `action_index`, le Tool et ses arguments.

## Boucle de tool calling

Le flux est : utilisateur → Claude → `tool_use` → Tool → `tool_result` → Claude. Claude choisit un outil depuis sa description, sans routage par mots-clés. Plusieurs `tool_use` peuvent être traités dans une même réponse.

Les erreurs d'outil sont renvoyées à Claude afin qu'il explique l'échec sans inventer de résultat. Un outil inconnu est refusé et audité. La boucle est limitée à 4 itérations et les résultats transmis au modèle ont une taille maximale contrôlée afin d'éviter les boucles et réponses excessives.

## Configuration

- **Modèle** : `claude-sonnet-5`, défini dans `app/agent.py`.
- **Effort** (`output_config.effort`) : réglable via la variable d'environnement `AGENT_EFFORT` dans `.env` (`low` / `medium` / `high` / `xhigh` / `max`), `medium` par défaut. Compromis vitesse/qualité pour le choix d'outil et la rédaction ; monter à `high` en cas de mauvais choix d'outil, descendre à `low` si la latence gêne en démo.
- **Métriques** : tokens (input/output) et latence sont mesurés à chaque appel. Le coût est estimé sur le tarif connu de `claude-sonnet-5` ($3/$15 par million de tokens entrée/sortie, constantes `INPUT_PRICE_PER_MILLION_USD`/`OUTPUT_PRICE_PER_MILLION_USD` dans `app/agent.py`), à ajuster si le modèle change.
