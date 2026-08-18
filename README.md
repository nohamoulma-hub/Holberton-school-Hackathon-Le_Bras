# LE BRAS

LE BRAS est un prototype d'agent conversationnel développé dans le cadre d'un hackathon. L'utilisateur saisit une demande dans une interface web simple, puis le backend transmet cette demande à Claude via l'API Anthropic et affiche la réponse obtenue.

## État actuel — Palier 2

Le socle du Palier 2 est opérationnel :

- le frontend HTML/CSS/JavaScript est servi par FastAPI ;
- `GET /health` permet de vérifier que le backend fonctionne ;
- `POST /chat` transmet un message à Claude et renvoie sa réponse ;
- le frontend appelle `/chat` sans URL de backend codée en dur ;
- l'ensemble de l'application fonctionne dans un seul conteneur Docker exposé sur le port `8000`.

## Architecture actuelle

```text
Navigateur
    -> Frontend HTML/CSS/JS
    -> POST /chat
    -> FastAPI
    -> API Anthropic/Claude
    -> réponse affichée dans le frontend
```

FastAPI sert à la fois l'API et les fichiers statiques du frontend. Aucun conteneur frontend séparé n'est utilisé.

## Structure du projet

```text
.
├── app/
│   ├── __init__.py
│   └── main.py
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── style.css
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
  "response": "..."
}
```

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

## Pourquoi un seul conteneur au Palier 2 ?

Le Palier 2 correspond au socle minimal de l'application. FastAPI peut servir directement le frontend statique et l'API, sans base de données, cache ou autre service indépendant. Un seul conteneur limite donc la configuration et permet de lancer toute l'application avec une seule commande.

## Limites actuelles

Le projet ne propose pas encore :

- de plan structuré ;
- de validation ou de refus action par action ;
- de Tools pour exécuter des actions ;
- de mécanisme d'idempotence ;
- d'audit des actions ;
- de fonction d'annulation (`undo`).
