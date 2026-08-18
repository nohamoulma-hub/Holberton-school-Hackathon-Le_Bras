# JOURNAL — travail avec l'IA

Entrées rédigées par Noham (back / agent / idempotence / audit). Jo complète avec sa partie (front / adaptateurs Tool / doc).

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

**Reste à faire pour le checkpoint palier 3** : un panneau debug dans le front pour afficher la trace visuellement (actuellement disponible via `GET /trace` ou le champ `trace` de `/chat`, mais pas encore affiché dans l'UI) ; la carte bonus "coût affiché" (tokens/coût/latence par exécution) n'est pas encore implémentée.