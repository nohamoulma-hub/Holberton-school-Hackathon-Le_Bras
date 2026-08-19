# LE BRAS

LE BRAS est un prototype d'agent conversationnel développé dans le cadre d'un hackathon. L'utilisateur saisit une demande dans une interface web simple, puis le backend transmet cette demande à Claude via l'API Anthropic et affiche la réponse obtenue.

## État actuel — Palier 3

Le Palier 3 est opérationnel :

- le frontend HTML/CSS/JavaScript est servi par FastAPI ;
- `GET /health` permet de vérifier que le backend fonctionne ;
- `POST /chat` transmet un message à Claude et renvoie sa réponse avec la trace des outils ;
- le frontend appelle `/chat` sans URL de backend codée en dur ;
- Claude choisit parmi sept outils via le Tool Calling natif Anthropic ;
- les effets de bord sont idempotents, audités et mis en attente d'une validation humaine ;
- le frontend permet d'approuver ou refuser chaque action en attente ;
- les outils locaux réversibles peuvent être annulés une fois ;
- l'ensemble de l'application fonctionne dans un seul conteneur Docker exposé sur le port `8000`.

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
```

FastAPI sert à la fois l'API et les fichiers statiques du frontend. Aucun conteneur frontend séparé n'est utilisé.

## Structure du projet

```text
.
├── app/
│   ├── __init__.py
│   ├── agent.py
│   ├── db.py
│   ├── main.py
│   └── tools.py
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── style.css
├── tests/
│   └── test_palier3.py
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

La clé d'idempotence d'une action dépend de son `plan_id`, de son `action_index`, du Tool et de ses arguments. Rejouer exactement la même action ne répète donc pas son effet, sans confondre deux plans ou deux positions différentes.

Les intégrations sont locales pour ce hackathon : l'issue tracker, les records, les événements et l'audit utilisent SQLite ; la messagerie écrit des fichiers Markdown sous `outbox/` ; les documents sont générés sous `files/`.

## Variables d'environnement et sécurité

La vraie clé Anthropic doit être enregistrée uniquement dans le fichier local `.env`. Ce fichier ne doit jamais être commité ni envoyé sur un dépôt distant. Le fichier `.env.example` documente uniquement le nom de la variable attendue et ne doit contenir aucune vraie clé.

## Stack technique

- Python 3.12
- FastAPI
- Uvicorn
- Anthropic SDK
- HTML, CSS et JavaScript
- Docker
- Docker Compose

## Pourquoi un seul conteneur au Palier 3 ?

FastAPI sert directement le frontend statique et l'API, tandis que SQLite et les dossiers de simulation restent locaux au projet. Aucun service indépendant n'est nécessaire à ce stade. Un seul conteneur limite donc la configuration et permet de lancer toute l'application avec une seule commande.

## Limites actuelles

Le projet ne propose pas encore :

- de plan structuré ;
- de véritables intégrations tierces pour les issues, messages ou calendriers ;
- d'authentification ou de gestion multi-utilisateurs ;
- de gestion des validations concurrentes ;
- d'annulation multi-niveaux.
