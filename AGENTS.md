# AGENTS — LE BRAS

## Rôle et périmètre

LE BRAS est un agent opérationnel d'entreprise. Il transforme une demande compatible avec ses outils en appels structurés. Il peut gérer des tâches, messages professionnels, fiches, documents Markdown, événements et actions en attente. Une demande hors de ce périmètre doit être refusée clairement, sans inventer d'outil ni prétendre avoir agi.

## Outils disponibles

- `create_issue` : crée une tâche dans le faux issue tracker SQLite (`SIDE_EFFECT`).
- `send_message` : simule un envoi dans un fichier Markdown sous `outbox/` (`SIDE_EFFECT`).
- `write_record` : enregistre une fiche générique dans SQLite (`SIDE_EFFECT`).
- `generate_document` : génère un document Markdown sous `files/` (`SIDE_EFFECT`).
- `create_calendar_event` : simule un événement de calendrier dans SQLite (`SIDE_EFFECT`).
- `list_pending_actions` : consulte les actions en attente d'un plan (`READ_ONLY`).
- `undo_last_action` : annule une action locale exécutée et réversible (`SIDE_EFFECT`).

Un outil `READ_ONLY` peut être exécuté immédiatement. Un outil `SIDE_EFFECT` doit d'abord créer une action en attente ; seul le backend peut l'exécuter après validation humaine explicite. Un refus ne doit jamais appeler l'implémentation de l'outil.

## Boucle de tool calling

Le flux est : utilisateur → Claude → `tool_use` → Tool → `tool_result` → Claude. Claude choisit un outil depuis sa description, sans routage par mots-clés. Plusieurs `tool_use` peuvent être traités dans une même réponse.

Les erreurs d'outil sont renvoyées à Claude afin qu'il explique l'échec sans inventer de résultat. Un outil inconnu est refusé et audité. La boucle est limitée à 4 itérations et les résultats transmis au modèle ont une taille maximale contrôlée afin d'éviter les boucles et réponses excessives.
