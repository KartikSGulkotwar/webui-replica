# PROJECT_SPEC.md — WebUI Replica (Open WebUI–inspired rebuild)

> Paste this file into the root of a new repo and tell Claude Code:
> "Read PROJECT_SPEC.md and build it phase by phase. Stop after each phase, run the checks, and commit."

## 0. What we're building
A self-hosted AI chat app that connects to **two model sources — Ollama and any OpenAI-compatible API** (OpenAI, Groq, OpenRouter, Together, LM Studio, vLLM). Users pick a model from a unified list, chat with streaming responses, and switch providers mid-conversation.

Inspired by Open WebUI, but an **original implementation**: do not copy code, assets, or branding from the open-webui repo. The project name is **WebUI Replica**; credit Open WebUI as inspiration in the README.

Key difference from the original: **frontend is React + TypeScript (Vite), not SvelteKit.**

## 1. Tech stack
**Frontend**
- React 18 + TypeScript + Vite
- Tailwind CSS
- TanStack Query (React Query) for server state
- React Router
- react-markdown + remark-gfm + rehype-highlight (markdown + code blocks)
- Streaming via `fetch` + ReadableStream (SSE format from backend)

**Backend**
- Python 3.11+, FastAPI, Uvicorn
- httpx (async) for provider calls
- SQLModel + SQLite locally, Postgres in production (via `DATABASE_URL`)
- Alembic for migrations
- cryptography (Fernet) to encrypt stored API keys
- pydantic-settings for config

**Infra**
- Docker (separate images for frontend and backend)
- docker-compose: frontend + backend + postgres + ollama
- GitHub Actions: lint + test on PR

## 2. Repo structure
```
webui-replica/
├── frontend/
│   ├── src/
│   │   ├── api/            # typed API client, streaming helper
│   │   ├── components/     # ChatWindow, MessageBubble, ModelSelector, Sidebar, ProviderForm
│   │   ├── pages/          # ChatPage, SettingsPage
│   │   ├── hooks/          # useChatStream, useModels, useConversations
│   │   ├── types/          # shared TS types
│   │   └── main.tsx
│   ├── Dockerfile
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py       # SQLModel tables
│   │   ├── schemas.py      # request/response models
│   │   ├── crypto.py       # Fernet encrypt/decrypt
│   │   ├── providers/
│   │   │   ├── base.py     # BaseProvider (abstract)
│   │   │   ├── ollama.py
│   │   │   ├── openai_compat.py
│   │   │   └── registry.py
│   │   └── routers/
│   │       ├── providers.py
│   │       ├── models.py
│   │       ├── chat.py
│   │       └── conversations.py
│   ├── tests/
│   ├── alembic/
│   └── Dockerfile
├── docker-compose.yml
├── .github/workflows/ci.yml
└── README.md
```

## 3. Backend design

### Provider abstraction (core of the project)
```python
class BaseProvider(ABC):
    id: str
    kind: Literal["ollama", "openai_compat"]

    async def list_models(self) -> list[ModelInfo]: ...
    async def stream_chat(self, model: str, messages: list[ChatMessage],
                          params: ChatParams) -> AsyncIterator[str]: ...
    async def health(self) -> ProviderHealth: ...
```
- **OllamaProvider**: `GET {base_url}/api/tags` for models, `POST {base_url}/api/chat` with `stream: true` (NDJSON lines).
- **OpenAICompatProvider**: `GET {base_url}/models`, `POST {base_url}/chat/completions` with `stream: true` (SSE `data:` lines, `[DONE]` terminator). Bearer API key.
- **Registry** loads enabled providers from DB, caches instances, exposes `get(provider_id)`.
- Model IDs exposed to the frontend are namespaced: `"{provider_id}:{model_name}"` so two providers can share a model name.

### Data model
- `Provider`: id, name, kind, base_url, api_key_encrypted (nullable), enabled, created_at
- `Conversation`: id, title, created_at, updated_at
- `Message`: id, conversation_id, role (system/user/assistant), content, model_id (which model produced it), created_at

### API
| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | backend health |
| GET | /api/providers | list providers (never return API keys; return `has_key: bool`) |
| POST | /api/providers | add provider |
| PATCH | /api/providers/{id} | update / enable / disable |
| DELETE | /api/providers/{id} | remove |
| GET | /api/providers/{id}/health | test connection |
| GET | /api/models | unified model list across all enabled providers (fan out with `asyncio.gather`, tolerate individual provider failures) |
| GET | /api/conversations | list |
| POST | /api/conversations | create |
| GET | /api/conversations/{id} | with messages |
| PATCH | /api/conversations/{id} | rename |
| DELETE | /api/conversations/{id} | delete |
| POST | /api/chat/stream | body: conversation_id, model_id, message → SSE stream of tokens; persist user msg before, assistant msg after stream completes |

### Rules
- API keys encrypted at rest with Fernet (`ENCRYPTION_KEY` env var). Never sent to the frontend.
- CORS restricted to `FRONTEND_ORIGIN`.
- Normalize both providers' streams into one SSE format: `data: {"delta": "..."}` … `data: {"done": true, "usage": {...}}`; errors as `data: {"error": "..."}`.
- Auto-title a conversation from the first user message (first ~6 words; no extra LLM call needed).
- Seed providers on startup from env vars (`OLLAMA_BASE_URL`, `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`) if the table is empty.
- Simple per-IP rate limit on `/api/chat/stream` for the public demo (e.g. slowapi, 20 req/min).

## 4. Frontend design
- **Layout**: left sidebar (new chat button, conversation list), main chat area, top bar with **ModelSelector** (grouped by provider, shows provider health dot).
- **Chat**: streaming assistant bubble that appends tokens; Stop button (AbortController); markdown + syntax-highlighted code with copy button; each assistant message shows a small model badge (proves provider switching works).
- **Model switching**: changing the selector mid-conversation applies to the next message; history is preserved.
- **Settings page**: list providers, add/edit form (kind, name, base URL, API key), "Test connection" button, enable/disable toggle.
- Dark mode by default with a light toggle; responsive down to mobile width.
- Empty, loading, and error states everywhere (provider down, no models, stream error).

## 5. Phases (build and commit one at a time)
1. **Scaffold**: monorepo, Vite React TS app, FastAPI app, health endpoint, docker-compose boots both.
2. **Provider layer**: base class, Ollama + OpenAI-compat providers, registry, `/api/models`. Unit tests with mocked httpx (respx).
3. **Streaming chat**: `/api/chat/stream`, normalized SSE, persistence. Test the stream parser for both formats.
4. **Frontend chat**: ModelSelector, ChatWindow, streaming hook, markdown rendering, stop button.
5. **Conversations**: sidebar, history, rename, delete.
6. **Settings**: provider CRUD UI, connection test, encrypted keys.
7. **Polish**: error states, rate limiting, responsive layout, CI workflow.
8. **Deploy** (section 6) + README.

## 6. Deployment (public demo)
Ollama can't be reached from a cloud deployment unless you host it, so:
- **Public demo**: backend uses an OpenAI-compatible provider with a free/cheap key (Groq or OpenRouter free models). Ollama provider appears as configurable but disconnected — that's fine and honest.
- **Local / self-hosted**: `docker compose up` runs everything including Ollama, so both providers work. Document this as the primary "full experience".

Targets:
- Frontend → **Vercel** (root `frontend/`, env `VITE_API_URL`)
- Backend → **Render** or **Railway** (Docker, root `backend/`)
- Database → **Neon** Postgres (free tier)
- Env vars: `DATABASE_URL`, `ENCRYPTION_KEY`, `FRONTEND_ORIGIN`, `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `OLLAMA_BASE_URL`

Provide a `.env.example` for both apps.

## 7. README must include
- One-line pitch + **live demo link** + screenshot/GIF of switching providers mid-chat
- Mermaid architecture diagram (React → FastAPI → provider registry → Ollama / OpenAI-compatible)
- Features list, tech stack, local setup (`docker compose up`), deployment notes
- "Design decisions" section: provider abstraction, namespaced model IDs, normalized SSE stream, encrypted keys
- Credit: "Inspired by Open WebUI; independent implementation in React + FastAPI."

## 8. Definition of done
- [ ] `docker compose up` works from a clean clone
- [ ] Can chat with an Ollama model and an OpenAI-compatible model in the same conversation
- [ ] Streaming works and can be stopped
- [ ] Conversations persist across refresh
- [ ] Backend tests pass in CI
- [ ] Live URL works on desktop and mobile
- [ ] README complete with demo link and screenshots
