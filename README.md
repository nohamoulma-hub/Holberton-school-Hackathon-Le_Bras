# LE BRAS

LE BRAS est un prototype d'agent conversationnel développé dans le cadre d'un hackathon. L'utilisateur saisit une demande dans une interface web simple, puis le backend transmet cette demande à Claude via l'API Anthropic et affiche la réponse obtenue.

## État actuel — Palier 4

Le Palier 3 est opérationnel :

- le frontend HTML/CSS/JavaScript est servi par FastAPI ;
- `GET /health` permet de vérifier que le backend fonctionne ;
- `POST /chat` transmet un message à Claude et renvoie sa réponse avec la trace des outils ;
- le frontend appelle `/chat` sans URL de backend codée en dur ;
- Claude choisit parmi sept outils via le Tool Calling natif Anthropic ;
- les effets de bord sont idempotents, audités et mis en attente d'une validation humaine ;
- le frontend permet d'approuver ou refuser chaque action en attente ;
- les outils locaux réversibles peuvent être annulés une fois ;
- les outils peuvent être activés ou désactivés depuis le menu Paramètre ;
- les réponses de l'agent prennent en charge un rendu Markdown limité et sécurisé ;
- un compte local permet d'afficher le profil et de conserver les historiques personnels ;
- les comptes, conversations, plans et actions sont enregistrés dans PostgreSQL ;
- un plan et les statuts de ses actions sont restaurés après un rechargement de page ;
- un calendrier interactif permet de sélectionner une date et de préparer une demande ;
- Docker Compose lance FastAPI et PostgreSQL, FastAPI restant exposé sur le port `8000`.

## Architecture actuelle

```text
Navigateur
    -> Frontend HTML/CSS/JS
    -> POST /chat
    -> FastAPI
    -> API Anthropic/Claude
    -> tool_use
    -> action en attente de validation
    -> Tool local après approbation
    -> tool_result et réponse affichés dans le frontend
    -> plan et historique PostgreSQL associés au compte connecté
```

FastAPI sert à la fois l'API et les fichiers statiques du frontend. PostgreSQL utilise un second
conteneur dédié ; aucun conteneur frontend séparé n'est utilisé.

## Structure du projet

```text
.
├── app/
│   ├── __init__.py
│   ├── accounts.py
│   ├── agent.py
│   ├── db.py
│   ├── history.py
│   ├── main.py
│   ├── plans.py
│   └── tools.py
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── style.css
├── tests/
│   ├── test_accounts_history.py
│   ├── test_palier3.py
│   ├── test_palier4_postgres.py
│   └── postgres_test_case.py
├── .dockerignore
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── README.md
└── requirements.txt
```

## Prérequis

- Git
- Docker
- Docker Compose
- une clé API Anthropic valide

## Quickstart Docker

Clonez le dépôt et placez-vous dans le projet :

```bash
git clone https://github.com/nohamoulma-hub/Holberton-school-Hackathon-Le_Bras.git
cd Holberton-school-Hackathon-Le_Bras
```

Créez votre fichier d'environnement local :

```bash
cp .env.example .env
```

Ajoutez ensuite votre clé Anthropic dans `.env` :

```dotenv
ANTHROPIC_API_KEY=votre_cle_anthropic
```

Les valeurs PostgreSQL locales sont déjà documentées dans `.env.example`. Modifiez-les dans
`.env` avant un déploiement partagé.

Lancez l'application :

```bash
docker compose up --build
```

- Application : http://localhost:8000
- Health : http://localhost:8000/health
- Docs FastAPI : http://localhost:8000/docs

Pour arrêter et supprimer le conteneur et le réseau créés par Compose :

```bash
docker compose down
```

## API actuelle

### `GET /health`

Vérifie que l'application FastAPI est disponible.

Réponse :

```json
{
  "status": "ok"
}
```

### `POST /chat`

Envoie un message à Claude via l'API Anthropic.

Corps de la requête :

```json
{
  "message": "..."
}
```

Réponse :

```json
{
  "response": "...",
  "trace": [],
  "plan_id": "...",
  "metrics": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "latency_ms": 0,
    "estimated_cost": null,
    "cost_status": "non_configured"
  }
}
```

Les actions à effet de bord apparaissent d'abord avec le statut `pending`. Elles peuvent ensuite être validées ou refusées depuis le frontend, qui appelle les endpoints suivants :

```text
POST /actions/{action_id}/approve
POST /actions/{action_id}/reject
```

Le journal récent des appels d'outils est disponible avec `GET /trace`.

### Plans persistants

```text
GET /plans/{plan_id}
GET /plans/latest
```

`GET /plans/{plan_id}` reconstruit la demande, la réponse et toutes les actions dans leur ordre
d'origine, avec leurs arguments, statuts, résultats et erreurs. Le frontend conserve uniquement le
`plan_id` courant dans `localStorage` puis relit PostgreSQL après un rechargement.

`GET /plans/latest` retourne le dernier plan du compte connecté.

### Compte et profil

```text
POST /auth/register
POST /auth/login
POST /auth/logout
GET  /auth/me
```

L'inscription et la connexion utilisent une adresse e-mail et un mot de passe d'au moins huit caractères. La session est conservée dans un cookie `HttpOnly` pendant sept jours.

### Historiques personnels

Ces routes nécessitent une connexion :

```text
GET /history/conversations
GET /history/accepted-actions
```

Les conversations sont enregistrées après une réponse de l'agent. Les actions apparaissent dans l'historique des tâches acceptées après leur approbation et leur exécution.

### Configuration des Tools

```text
GET  /tools
POST /tools/{tool_name}/toggle
```

L'état d'un Tool est appliqué dès la demande suivante, sans redémarrer le serveur.

La clé d'idempotence d'une action dépend de son `plan_id`, de son `action_index`, du Tool et de ses arguments. Rejouer exactement la même action ne répète donc pas son effet, sans confondre deux plans ou deux positions différentes.

Les intégrations sont locales pour ce hackathon : les comptes, historiques, plans, issues, records,
événements et audits utilisent PostgreSQL ; la messagerie écrit des fichiers Markdown sous
`outbox/` et les documents sont générés sous `files/`. PostgreSQL utilise le volume Docker
`postgres_data`.

L'ancien fichier `data.db` n'est ni importé ni supprimé automatiquement. Une base PostgreSQL vide
est initialisée au démarrage avec toutes les tables nécessaires.

## Variables d'environnement et sécurité

La vraie clé Anthropic doit être enregistrée uniquement dans le fichier local `.env`. Ce fichier ne doit jamais être commité ni envoyé sur un dépôt distant. Le fichier `.env.example` documente uniquement les variables attendues et ne doit contenir aucune vraie clé. Les mots de passe sont dérivés avec PBKDF2 et les jetons de session ne sont stockés qu'après hachage.

## Stack technique

- Python 3.12
- FastAPI
- Uvicorn
- Anthropic SDK
- PostgreSQL 16
- psycopg 3
- HTML, CSS et JavaScript
- Docker
- Docker Compose

## Pourquoi deux conteneurs au Palier 4 ?

Le conteneur `app` sert toujours le frontend et l'API. Le conteneur `db` isole PostgreSQL et son
volume persistant. Le healthcheck empêche FastAPI de démarrer avant que la base soit prête, tout en
conservant une seule commande de lancement.

## Limites actuelles

Le projet ne propose pas encore :

- de véritables intégrations tierces pour les issues, messages ou calendriers ;
- de migration automatique des anciennes données SQLite vers PostgreSQL ;
- de récupération de mot de passe ou de vérification d'adresse e-mail ;
- de gestion des validations concurrentes ;
- d'annulation multi-niveaux.
