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

### Run API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

- Health: `GET http://localhost:8001/health`
- Incident: `POST http://localhost:8000/incident` with `{"message": "..."}`
- Approve: `POST http://localhost:8000/approve` with `{"incident_id": "..."}`

### Run UI

```bash
export API_URL=http://localhost:8001
streamlit run ui/app.py --server.port 8502
```

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

## Deploy

| Component | Platform |
|-----------|----------|
| API | [Railway](https://railway.app) — connect repo, set `OPENAI_API_KEY`, uses `railway.toml` |
| UI | [Streamlit Community Cloud](https://share.streamlit.io) — see below |

### Streamlit Community Cloud

1. Push this repo to GitHub (`main` branch).
2. [Deploy an app](https://share.streamlit.io/deploy) → pick `soujanya1604/ai-incident-resolution`.
3. **Main file path:** `ui/app.py`
4. **Python version:** 3.11 (`.python-version`)
5. **Dependencies file:** `requirements-ui.txt` (UI-only; API runs on Railway)
6. **Secrets** (Settings → Secrets): `API_URL` = your Railway API URL (e.g. `https://your-app.up.railway.app`)

**Note:** Incidents are stored in memory and are lost on API restart.

## Presentation one-liner

> I built a multi-agent AI system that diagnoses database connection failures using RAG over real PostgreSQL runbooks and past incident reports. Five specialized agents collaborate to extract the incident, retrieve relevant documentation, identify the root cause, recommend safe fixes, and sanitize the response — with a human approval gate before any remediation step is shown to the engineer.
