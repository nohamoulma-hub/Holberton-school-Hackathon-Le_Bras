# Holberton-school-Hackathon-Le_Bras

## Back : quickstart (palier 2, socle back seulement)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis renseigner ANTHROPIC_API_KEY dans .env
uvicorn app.main:app --reload
```

- `GET /health` : vérifie que le back tourne.
- `POST /chat` (body `{"message": "..."}`) : appel LLM réel (Claude), retourne `{"response": "..."}`.
- Doc interactive : http://127.0.0.1:8000/docs

Le front (palier 2, côté Jo) n'est pas encore branché : ce squelette expose uniquement l'API back testable via `/docs` ou `curl`.