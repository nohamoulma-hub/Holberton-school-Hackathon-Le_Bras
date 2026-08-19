# SPEC — Sujet 03 : Le Bras

## Le problème (5 lignes)

De nombreuses situations d'équipe demandent d'accomplir manuellement une série de tâches dispersées sur plusieurs outils (arrivée d'un stagiaire, clôture d'un projet, préparation d'un événement, incident à traiter...), sans processus unifié. Résultat : oublis, doublons, tâches faites en retard ou pas faites du tout, et une exécution bâclée du cas à traiter. On propose un agent capable de transformer toute intention formulée en langage naturel et compatible avec les outils disponibles en un plan d'actions concrètes touchant plusieurs systèmes, puis de soumettre ce plan à validation humaine **action par action** et de n'exécuter que ce qui a été approuvé. Chaque exécution est journalisée de façon idempotente et annulable, pour qu'aucune action à effet de bord ne parte sans accord humain explicite et traçable. L'onboarding d'un stagiaire sert d'exemple de référence pour la démo, mais l'agent et ses outils restent conçus pour s'adapter à d'autres types de demandes.

## User stories (3 max)

1. **En tant qu'utilisateur**, je veux exprimer une intention en langage naturel afin que l'agent me propose un plan d'actions adapté sans rien exécuter immédiatement.

2. **En tant qu'utilisateur**, je veux approuver ou refuser chaque action du plan individuellement afin de garder le contrôle sur les actions réellement exécutées.

3. **En tant qu'utilisateur**, je veux consulter un journal d'audit afin de connaître les actions exécutées, refusées ou ayant échoué et de garder une trace de ce qui s'est passé.

## Hors scope (10 items)

- Pas de vraie intégration API tierce en v1 : on utilise PostgreSQL comme faux issue tracker et un faux service de messagerie qui écrit des fichiers `.md` dans un dossier `/outbox`, remplaçable par une vraie API plus tard sans changer l'interface `Tool`.
- **Pas de gestion des conflits concurrents (deux validations simultanées sur le même plan) : on suppose un usage mono-utilisateur séquentiel, verrouillé par plan.** *(ligne candidate au bonus "non argumenté", voir plus bas)*
- Pas de catalogue métier prédéfini par type de demande : la généralisation à plusieurs cas de figure repose sur le raisonnement du LLM combiné à un petit ensemble d'outils génériques, pas sur des templates codés en dur pour chaque scénario (onboarding, incident, événement...).
- Pas de multi-organisation ni de gestion fine des rôles : les comptes locaux séparent leurs historiques, mais partagent la même instance.
- Pas de fine-tuning ni d'entraînement de modèle : uniquement du prompt engineering + tool calling sur un LLM existant via API.
- Pas de récurrence dans les actions programmées : le bonus "actions programmées dans le temps" couvre des actions ponctuelles différées, pas un cron avancé.
- Pas d'undo multi-niveaux en MVP : seule la dernière action est annulable (bonus), pas de pile d'annulations en cascade.
- Pas d'application mobile native : l'interface web responsive couvre les écrans mobiles pour la démo.
- Pas de génération de fichiers autres que texte/markdown : pas de PDF, pas d'images, pas de docx.
- Pas de vérification métier du contenu (ex. vérifier que le stagiaire existe réellement en RH, que la salle est libre) : l'agent fait confiance aux informations fournies dans l'intention initiale.

## Schéma d'architecture

```mermaid
flowchart LR
    U[Utilisateur] -->|intention en langage naturel| FRONT[Frontend HTML/CSS/JS responsive]
    FRONT -->|POST /chat| API[FastAPI]
    API -->|prompt + Tools actifs| AGENT[Claude Sonnet 5]
    AGENT -->|tool_use| API
    API -->|valide le schéma puis crée pending| DB[(PostgreSQL)]
    API -->|réponse + trace + actions| FRONT
    FRONT -->|POST approve / reject| API
    API -->|met à jour le statut| DB
    API -->|exécute uniquement après approve| EXEC[Executor]
    EXEC --> T1[Tool: create_issue]
    EXEC --> T2[Tool: send_message]
    EXEC --> T3[Tool: write_record]
    EXEC --> T4[Tool: generate_document]
    EXEC --> T5[Tool: create_calendar_event]
    T1 & T3 & T5 --> DB
    T2 --> OUTBOX[/dossier outbox : faux service de messagerie/]
    T4 --> FILES[/dossier files : fichiers générés/]
    EXEC -->|log horodaté + idempotency_key| DB
    DB -->|plan restauré après F5, calendrier, historiques| API
    API --> FRONT
```

- **Front** : interface web responsive qui affiche le plan, un bouton approuver/refuser par action, la trace, le calendrier, le profil et les historiques.
- **Back** : API qui orchestre agent, plan, validation et exécution, ne fait jamais confiance au front pour l'exécution réelle.
- **Agent** : appelle Claude Sonnet 5 avec la liste des Tools disponibles et traite ses `tool_use`. Le même agent et les mêmes Tools servent quel que soit le type d'intention reçue.
- **Outils** : chacun est un adaptateur générique avec effet de bord isolé, appelé uniquement par l'Executor après validation. Aucun tool n'est spécifique à un seul scénario métier.
- **Stockage** : PostgreSQL contient `users`, `sessions`, `plans`, `conversations`, `actions`, `action_owners`, `audit_log`, `issues`, `records` et `calendar_events`. Les plans utilisent `processing`, `pending`, `completed` ou `error` ; les actions utilisent `pending`, `executing`, `executed`, `rejected`, `error` ou `cancelled`.
- **Persistance fichier** : les volumes Docker `files_data` et `outbox_data` conservent documents et messages lors d'une recréation du conteneur `app`.

## Endpoints REST actuels

- Chat et supervision : `POST /chat`, `GET /health`, `GET /trace`.
- Validation : `POST /actions/{action_id}/approve`, `POST /actions/{action_id}/reject`.
- Plans : `GET /plans/{plan_id}`, `GET /plans/latest`.
- Outils : `GET /tools`, `POST /tools/{tool_name}/toggle`.
- Comptes : `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.
- Historique et calendrier : `GET /history/conversations`, `GET /history/accepted-actions`, `GET /calendar/events`.

## Outils de l'agent

| Nom | Signature | Effet de bord |
|---|---|---|
| `create_issue` | `create_issue(title: str, description: str, assignee: str, due_date: date) -> IssueId` | **Oui** : insertion dans la table `issues` (faux issue tracker) |
| `send_message` | `send_message(channel: str, recipient: str, content: str) -> MessageId` | **Oui** : écriture d'un fichier `.md` dans `/outbox/{channel}/` (faux service de messagerie) |
| `write_record` | `write_record(record_type: str, subject: str, payload: dict) -> RecordId` | **Oui** : insertion dans la table générique `records` (`record_type` distingue onboarding, incident, événement...) |
| `generate_document` | `generate_document(title: str, content: str, filename: str) -> FilePath` | **Oui** : génération et sauvegarde d'un fichier markdown sur disque, quel que soit son contenu |
| `create_calendar_event` | `create_calendar_event(title: str, start: datetime, duration_min: int, attendees: list[str]) -> EventId` | **Oui** : insertion dans la table `calendar_events` |
| `list_pending_actions` | `list_pending_actions(plan_id: str) -> list[Action]` | Non : lecture seule |
| `undo_last_action` | `undo_last_action(action_id: str) -> bool` | **Oui** : compense/annule l'action précédente, idempotent |

Toute action a un `idempotency_key = hash(plan_id, action_index, payload)`. L'Executor vérifie cette clé avant d'exécuter : rejouer une action déjà exécutée est un no-op qui renvoie le résultat déjà loggé.

## Happy path de la démo finale (6 étapes)

Le scénario stagiaire ci-dessous sert de fil rouge pour la démo, mais le même pipeline (plan, validation, exécution, audit) s'applique sans changement de code à d'autres intentions (clôture de projet, préparation d'un événement...), en s'appuyant sur les mêmes outils génériques.

1. L'utilisateur saisit : *« Prépare l'arrivée du stagiaire Paul, équipe Data, le 25 août, buddy Sophie. »*
2. L'agent construit un plan de 5 actions (issue onboarding via `create_issue`, message à l'équipe via `send_message`, fiche stagiaire en base via `write_record`, document de bienvenue via `generate_document`, event calendrier via `create_calendar_event`) et l'affiche avec, pour chaque action, le détail de son effet de bord.
3. L'utilisateur approuve 4 actions et refuse l'event calendrier (la salle n'est pas encore réservée).
4. Le système exécute uniquement les 4 actions approuvées, dans l'ordre, chacune journalisée avec son `idempotency_key`.
5. Le journal d'audit affiche les 4 actions exécutées, horodatées, avec statut et lien vers l'effet produit (fichier, ligne en base).
6. L’utilisateur consulte le journal d’audit et vérifie que les actions approuvées ont été exécutées et que l’action refusée ne l’a pas été.

## Répartition du travail


- **Noham** : back (API orchestrateur), agent/planner (appel LLM + tool calling, capable de raisonner sur des intentions variées), gestion des doublons, journal d'audit + annulation.
- **Jonathan** : front (UI d'approbation action par action), les 5 adaptateurs Tool génériques (issue/message/record/document/calendrier), rédaction README/AGENTS.md.
- **En commun** : SPEC.md, schéma d'architecture et script de démo de 3 minutes.

---
**Carte bonus "Non argumenté" : ligne choisie**
> *Pas de gestion des conflits concurrents (deux validations simultanées sur le même plan) : on suppose un usage mono-utilisateur séquentiel, verrouillé par plan.*

Justification : c'est le genre de trou qu'on ne voit qu'en prod, jamais en demo, et un plan à moitié validé par deux clics simultanés casserait justement le cœur technique du sujet (human-in-the-loop fiable). L'assumer explicitement montre qu'on a pensé au risque sans sur-ingénierer une solution qu'on n'a pas le temps de livrer en 3 jours.
