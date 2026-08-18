# Holberton-school-Hackathon-Le_Bras

## Quickstart Docker

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
