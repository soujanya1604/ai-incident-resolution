# AI Incident Resolution System

Multi-agent AI system that diagnoses **database connection failures** using RAG over PostgreSQL runbooks and past incident reports. Five specialized agents collaborate to extract the incident, retrieve relevant documentation, identify the root cause, recommend safe fixes, and sanitize the response — with a **human approval gate** before any remediation step is shown.

## Architecture

```
User Input → Intake → Retrieval (RAG) → RCA → Recommendation → Security → [Human Approval] → Fix Steps
                ↓ blocked
               END
```

| Agent | Role |
|-------|------|
| **Intake** | Security input gate + extract service, error_type, severity |
| **Retrieval** | ChromaDB semantic search over runbooks (top 3) |
| **RCA** | Root cause + confidence from docs + incident |
| **Recommendation** | Ordered advisory remediation steps |
| **Security** | Mask secrets, flag destructive steps, sanitize output |

## Quick start

Requires **Python 3.11+** (3.11 recommended).

```bash
cd ai-incident-resolution
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY
```

### Run app (API + UI together)

```bash
streamlit run streamlit_app.py
```

This starts the FastAPI backend on port **8001** in a background subprocess, then launches the Streamlit UI. The UI talks to `http://localhost:8001` by default.

### Run API or UI separately (optional)

```bash
# API only
uvicorn api.main:app --reload --host 0.0.0.0 --port 8001

# UI only (API must already be running)
export API_URL=http://localhost:8001
streamlit run ui/app.py --server.port 8502
```

- Health: `GET http://localhost:8001/health`
- Incident: `POST http://localhost:8001/incident` with `{"message": "..."}`
- Approve: `POST http://localhost:8001/approve` with `{"incident_id": "..."}`

### Run tests

```bash
# Offline security tests (no API key)
pytest tests/test_security_offline.py -v

# Full agent tests (requires OPENAI_API_KEY)
pytest tests/test_agents.py -v
```

## API response

`POST /incident` returns analysis with `recommended_steps: []` and `steps_locked: true` until `POST /approve` reveals steps.

## Knowledge base

Markdown runbooks in `knowledge_base/docs/` are chunked and indexed into `chroma_db/` (gitignored) on first search. First request may take longer while the embedding model loads.

## Deployment

### Streamlit Community Cloud (recommended — single app)

The bundled entrypoint `streamlit_app.py` runs **both** the FastAPI backend and the Streamlit UI in one deployment. No separate Railway/Heroku backend is required.

1. Push this repo to GitHub.
2. Open [share.streamlit.io](https://share.streamlit.io) → **Create app**.
3. Select your repository, branch **`main`**, main file **`streamlit_app.py`**.
4. **Advanced settings**
   - **Python version:** `3.11` (see `.python-version`)
   - **Dependencies file:** `requirements.txt` (default)
   - **Secrets:** paste from `.streamlit/secrets.toml.example` (at minimum `OPENAI_API_KEY`)

Example secrets (TOML):

```toml
OPENAI_API_KEY = "sk-..."
API_URL = "http://localhost:8001"
API_PORT = "8001"
```

5. Deploy and watch logs. The first cold start can take 1–3 minutes while embeddings and the knowledge base warm up.

| Secret | Required | Description |
|--------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for agent LLM calls |
| `API_URL` | No | Defaults to `http://localhost:8001` (bundled backend) |
| `API_PORT` | No | Defaults to `8001` |

### Local secrets

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml, or use .env (see .env.example)
```

### AWS EC2 (one-command deploy)

See **[deploy/aws/README.md](deploy/aws/README.md)** — CloudFormation stack + bootstrap script (Ubuntu 22.04, nginx, systemd).

```bash
cd deploy/aws && ./deploy.sh
```

Requires AWS CLI (`aws configure`) and an EC2 key pair.

### Optional: separate API hosting (Railway)

For production scale, you can still deploy the API alone using `railway.toml` and point the UI at it via `API_URL`. For assignments and demos, the bundled `streamlit_app.py` flow is simpler.

**Note:** Incidents are stored in memory and are lost when the backend process restarts.

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| “Cannot reach the API” | Use main file `streamlit_app.py`, not `ui/app.py`, on Streamlit Cloud |
| Import / module errors | Run from repo root; ensure `agents/`, `api/`, `graph/`, `knowledge_base/` are present |
| Slow first message | Normal — KB warmup and embedding model load on first `/incident` |
| `OPENAI_API_KEY not set` | Add key in Streamlit **Secrets** or `.env` |
| App exceeds memory | Streamlit Cloud ~1 GB limit; large models may OOM — use Python 3.11 and redeploy |

## Presentation one-liner

> I built a multi-agent AI system that diagnoses database connection failures using RAG over real PostgreSQL runbooks and past incident reports. Five specialized agents collaborate to extract the incident, retrieve relevant documentation, identify the root cause, recommend safe fixes, and sanitize the response — with a human approval gate before any remediation step is shown to the engineer.
