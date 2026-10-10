# WebUI Replica

A self-hosted AI chat app for **Ollama** and any **OpenAI-compatible API** (OpenAI, Groq, OpenRouter, Together, LM Studio, vLLM), with streaming responses and switching between providers mid-conversation.

> Work in progress. The build follows the phases in [PROJECT_SPEC.md](PROJECT_SPEC.md).

## Quick start (Docker)

```bash
cp .env.example .env   # optional: add an OpenAI-compatible key
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000/api/health

## Local development

```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload        # http://localhost:8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev                                     # http://localhost:5173, proxies /api to :8000
```

Tests and lint:

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check .
cd frontend && npm run lint && npm run build
```

---

Inspired by [Open WebUI](https://github.com/open-webui/open-webui); independent implementation in React + FastAPI.
