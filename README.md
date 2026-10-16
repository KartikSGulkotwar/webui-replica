# WebUI Replica

A self-hosted AI chat app that talks to **Ollama**, **Anthropic's Claude** (native API), and **any OpenAI-compatible API** (Groq, OpenRouter, OpenAI, Together, LM Studio, vLLM) from one interface. Replies stream in as they're written, and you can switch providers in the middle of a conversation.

**Live demo: [webui-replica.vercel.app](https://webui-replica.vercel.app)** · runs on Groq's free tier, so Ollama shows as configured but offline (it needs a machine you control). For the full experience, run it locally with `docker compose up`.

![Switching from Ollama to an OpenAI-compatible provider in the same conversation](docs/images/provider-switch.gif)

## Features

- **Three provider types, one model menu.** Models from every enabled provider are grouped by provider, each with a live health dot.
- **Switch models mid-conversation.** The next message goes to the newly selected model with the full history, and each reply is labelled with the model and provider that wrote it.
- **Streaming with Stop.** Tokens appear as they're generated. Stopping keeps the partial answer.
- **Markdown, code, and math.** GitHub-flavoured Markdown, syntax highlighting with a copy button, and LaTeX formulas (KaTeX loads only for messages that contain math).
- **Work with replies.** Copy, regenerate (optionally with a different model), edit and resend an earlier message, and rate replies 👍/👎 with an optional comment.
- **Per-chat system prompt.** Give a chat standing instructions, even before the first message.
- **Organise and find chats.** Full-text search across titles and messages (with matching snippets), pin, archive and restore.
- **Share and export.** Share a read-only public snapshot by link (later messages stay private until you update it), export a chat as Markdown or JSON, or export every chat at once.
- **Conversation history.** Chats are saved and grouped by date, with auto-titles, inline rename, and delete.
- **Provider settings in the browser.** Add, edit, enable/disable, and delete providers, and test a connection before saving. Presets cover common services.
- **Encrypted API keys.** Keys are encrypted at rest and never sent back to the browser.
- **Chat with your documents (RAG).** Upload PDF, Word, Markdown, text, CSV, JSON or HTML into reusable knowledge bases, or attach files to a single chat. Answers cite numbered sources with file name and page, and you can expand each citation to read the exact passage.
- **Hybrid search.** Keyword ranking (BM25) always runs. Add an embedding model (Ollama or any `/embeddings` API) and semantic vector search joins in, merged with Reciprocal Rank Fusion. Vectors live in Postgres via **pgvector**.
- **Native Claude support.** Uses the official Anthropic SDK, so the system prompt, per-model output limits, and prompt caching work as Claude intends. If a model declines a request, server-side fallback can answer with another Claude model, and the reply is labelled with the model that actually answered.
- **Tools (function calling).** Switch on built-in tools from the 🔧 menu: an exact calculator, the current time in any timezone, and a web-page reader. The model decides when to call them. Each step shows in the reply with its input and output, and is saved with it. This works natively on Ollama, OpenAI-compatible APIs, and Claude.
- **Web search with citations.** Turn on 🌐 Web search next to the message box. The server searches, reads the top pages, picks the passages that best match the question, and the reply cites them as [1], [2] with links. Follow-up questions are rewritten into standalone search queries. Models can also search on their own with the 🔎 Web search tool. Engines: DuckDuckGo (no key), SearXNG, Brave, or Tavily.
- **Install it like an app.** It's a Progressive Web App: add it to an iPhone's home screen (Safari → Share → Add to Home Screen), the Mac Dock (Safari → File → Add to Dock), or install it from Chrome/Edge. It opens full screen with its own icon, respects the iPhone notch and home bar, and shows a friendly page when offline.
- **Your language.** The interface is in English, हिन्दी, Español or Français. It follows the browser's language, and you can switch on the Account page or the sign-in page.
- **Notes.** Private markdown notes with search, pinning and autosave. ✨ AI can improve, summarize or continue the whole note or just a selection (you choose to replace, insert or copy the result). You can also dictate into a note, download it as `.md`, or start a chat about it with "Ask in chat".
- **Channels.** Shared chat rooms (#general…) where everyone signed in can post, reply, react, edit and delete. Type **@** to bring a model in: it reads the recent conversation and replies in the channel, streaming to whoever asked. Admins create and manage channels.
- **Voice.** Dictate with 🎤, have any reply read aloud with 🔊, or open voice mode and just talk: it listens until you pause, answers out loud, and listens again. It works with no setup using the browser's own speech, or with server engines (any OpenAI-compatible audio API, such as Groq Whisper for transcription and OpenAI or Groq Orpheus for voices). You can pick the browser voice and speed on the Account page.
- **Image generation.** Switch on 🎨 Image next to the message box and your message becomes a picture; follow-ups like "now make it blue" are rewritten into a complete prompt. Models can also draw on their own with the 🎨 Image tool. Images show in the reply, open full size, download, and appear in shared links. Engines: Pollinations (free, no key), any OpenAI-compatible images API (gpt-image-1, DALL·E), or Automatic1111.
- **Compare models side by side.** Click **+** next to the model menu to ask up to three models the same question. Their answers stream in columns, each model continues its own thread, and any column can be regenerated on its own.
- **Arena and leaderboard.** Pick ⚔️ Arena and two models chosen at random answer blind as "Model A" and "Model B". Vote for the better one to reveal them. Votes and 👍/👎 on side-by-side answers feed an Elo leaderboard under Admin panel → Evaluations.
- **Usage analytics.** Admin panel → Analytics shows messages, active people and tokens over 7, 30 or 90 days, a per-day chart (with a table view), and usage and ratings per model.
- **Memory.** The assistant remembers facts about you across chats ("Prefers Python", "Has a dog called Biscuit"). Add, edit, and delete them on the Memory page, or switch on the 🧠 Memory tool and say "remember that…" so the model saves them itself. Memories are private to each user and can be turned off.
- **Custom models.** Save assistants that combine a base model, instructions, knowledge bases, and tools (e.g. an "HR Helper" that always answers from the handbook and cites it). They're private by default; admins can share them with everyone.
- **Model management.** Admins choose which provider models appear in the menu and can give them friendlier names. A hidden model can still power a curated public assistant.
- **Accounts and roles.** Email/password sign-up (Argon2-hashed), optional "Sign in with GitHub/Google", and admin / user / pending roles. The first account becomes admin. Each user's chats are private.
- **Admin panel.** Approve or remove users, change roles, turn sign-up on or off, and manage providers.
- **Built for a public demo.** Includes an optional guest mode and per-IP rate limits on chat and sign-in.
- **Polish.** Dark mode by default with a light toggle, works at phone widths, and handles empty, loading, and error states.

| Settings | Mobile |
|---|---|
| ![Provider settings](docs/images/settings.png) | <img src="docs/images/mobile.png" alt="Chat on a phone" width="260"> |

## Architecture

```mermaid
flowchart LR
    UI["React + TypeScript<br/>(Vite, TanStack Query)"]
    subgraph API["FastAPI backend"]
        R["Routers<br/>chat · models · conversations · providers"]
        REG["Provider registry"]
        OL["OllamaProvider<br/>NDJSON"]
        OA["OpenAICompatProvider<br/>SSE"]
        R --> REG
        REG --> OL
        REG --> OA
    end
    RAG["RAG: extract → chunk → embed<br/>BM25 + pgvector, RRF"]
    R --> RAG
    RAG --> DB
    DB[("Postgres + pgvector / SQLite<br/>conversations · messages · documents<br/>providers (encrypted keys)")]
    UI -- "REST + SSE (/api)" --> R
    R --> DB
    REG --> AN["AnthropicProvider<br/>official SDK"]
    OL --> O["Ollama"]
    AN --> C["Anthropic API (Claude)"]
    OA --> G["Groq · OpenRouter · OpenAI<br/>LM Studio · vLLM · …"]
```

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, React Router, react-markdown + remark-gfm + rehype-highlight |
| Backend | Python 3.11+, FastAPI, httpx (async), SQLModel, Alembic, cryptography (Fernet), pydantic-settings |
| Data | SQLite for local dev, Postgres in Docker and production |
| Infra | Docker, docker compose (frontend · backend · Postgres · Ollama), GitHub Actions, Vercel + Neon for the demo |
| Tests | pytest + respx (mocked provider HTTP), Vitest, Playwright for manual end-to-end checks |

## Run it locally (full experience)

Requires Docker.

```bash
git clone <this repo> && cd webui-replica
cp .env.example .env
# Put an encryption key in .env (needed to store API keys):
sed -i.bak "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')|" .env && rm .env.bak

docker compose up --build
docker compose exec ollama ollama pull qwen2.5:0.5b   # a small model (~400 MB) to start with
```

Open **http://localhost:3000**, then:

- create your account (the first one becomes the admin and keeps any existing chats), then
- add Groq, OpenAI, or another service under **Admin panel → Connections → Add provider**.

If a port is taken, set `FRONTEND_PORT`, `BACKEND_PORT`, or `OLLAMA_PORT` in `.env`. Ollama installed directly on your machine is reachable from the backend container at `http://host.docker.internal:11434`.

## Development without Docker

```bash
# backend: http://localhost:8000 (API docs at /docs)
cd backend
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env               # set ENCRYPTION_KEY; OLLAMA_BASE_URL if you run Ollama
.venv/bin/uvicorn app.main:app --reload

# frontend: http://localhost:5173 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Checks (the same ones CI runs):

```bash
cd backend  && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
cd frontend && npm run lint && npm run format:check && npm test && npm run build
```

## Configuration

Backend environment variables (see [`backend/.env.example`](backend/.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./webui.db` | SQLite or Postgres. `postgres://` URLs from hosts like Neon work as-is |
| `ENCRYPTION_KEY` | — | Fernet key for stored API keys. Required to save a provider with a key |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed CORS origin(s), comma-separated |
| `OLLAMA_BASE_URL`, `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `ANTHROPIC_API_KEY` | — | Providers created on first start, only while the providers table is empty |
| `SECRET_KEY` | derived from `ENCRYPTION_KEY` | Signs session cookies |
| `ENABLE_SIGNUP` | `true` | Initial value; admins can change it in the admin panel |
| `DEFAULT_USER_ROLE` | `pending` | Role for new sign-ups: `pending` (admin approves) or `user`. Admins can change it |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` | — | Creates this admin on startup/deploy, so a public site isn't claimed by whoever signs up first |
| `GUEST_ACCESS` | `false` | Shows "Continue as guest" (a throwaway account per visitor) |
| `GITHUB_CLIENT_ID`/`_SECRET`, `GOOGLE_CLIENT_ID`/`_SECRET`, `PUBLIC_URL` | — | Sign in with GitHub/Google. Register `<PUBLIC_URL>/api/auth/oauth/<provider>/callback` |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | Sign-up/login/guest attempts per minute per IP |
| `MAX_UPLOAD_MB` | `10` | Largest document upload (use `4` on Vercel, which caps request bodies at 4.5 MB) |
| `RAG_EMBEDDING_ENGINE`, `RAG_EMBEDDING_BASE_URL`, `RAG_EMBEDDING_MODEL`, `RAG_EMBEDDING_API_KEY` | — | Initial semantic-search settings: engine `ollama` or `openai` (any `/embeddings` API); blank means keyword search only. Admins can change them under Admin panel → Documents |
| `ENABLED_TOOLS` | `calculator,current_time,fetch_url,web_search,add_memory,generate_image` | Initial list of tools people may turn on; admins can change it under Admin panel → General |
| `WEB_SEARCH_ENGINE`, `WEB_SEARCH_BASE_URL`, `WEB_SEARCH_API_KEY`, `WEB_SEARCH_RESULT_COUNT` | —, —, —, `3` | Initial web search settings: `duckduckgo` (no key), `searxng` (base URL), `brave` or `tavily` (API key); blank means off. Admins can change them under Admin panel → Web search |
| `STT_ENGINE`, `STT_BASE_URL`, `STT_API_KEY`, `STT_MODEL` | — | Initial speech-to-text engine: `openai` (any OpenAI-compatible `/audio/transcriptions`, e.g. Groq `whisper-large-v3-turbo`); blank means the browser's own recognition. Admins can change it under Admin panel → Audio |
| `TTS_ENGINE`, `TTS_BASE_URL`, `TTS_API_KEY`, `TTS_MODEL`, `TTS_VOICE` | — | Initial text-to-speech engine: `openai` (`/audio/speech`); blank means browser voices |
| `IMAGE_ENGINE`, `IMAGE_BASE_URL`, `IMAGE_API_KEY`, `IMAGE_MODEL`, `IMAGE_SIZE` | —, —, —, —, `1024x1024` | Initial image settings: `pollinations` (no key), `openai` (base URL, model and key) or `automatic1111` (base URL); blank means off. Admins can change them under Admin panel → Images |
| `ARENA_MODELS` | — | Initial arena line-up (comma-separated model IDs, two or more); admins can change it under Admin panel → Evaluations |
| `DEFAULT_MODEL` | — | Model new visitors start with, e.g. `groq:openai/gpt-oss-120b` |
| `CHAT_RATE_LIMIT_PER_MINUTE` | `20` | Messages per minute per client IP. `0` disables the limit |
| `TRUSTED_PROXY_HOPS` | `0` | Number of proxies whose `X-Forwarded-For` entries are trusted (1 behind nginx or Vercel) |
| `LOG_FORMAT`, `LOG_LEVEL` | `auto`, `INFO` | `json` for one JSON object per line (with request IDs), `text` for humans; `auto` picks JSON unless writing to a terminal |
| `METRICS_TOKEN` | — | Turns on Prometheus metrics at `/api/metrics` (bearer token required) |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME` | —, `webui-replica` | Sends OpenTelemetry traces (HTTP, SQL, provider calls) to an OTLP/HTTP collector |
| `DATABASE_WAIT_SECONDS` | `60` | How long startup retries an unreachable database before failing |
| `AUTO_MIGRATE` | `true` | Run migrations on startup. Vercel runs them during the build instead |

## Deployment

The public demo runs as **one Vercel project** (React frontend and FastAPI backend on the same domain), with **Neon** Postgres and **Groq** as the model provider. The step-by-step guide is in [docs/deploy-vercel.md](docs/deploy-vercel.md).

It also runs on **Kubernetes**: [`deploy/kubernetes/`](deploy/kubernetes) has Kustomize manifests (Postgres with pgvector, autoscaled backend replicas, frontend, Ingress, network policy, optional Ollama and Prometheus ServiceMonitor). See [docs/kubernetes.md](docs/kubernetes.md).

The Docker images also run on any container host (Render, Railway, Fly.io). Set `VITE_API_URL` when building the frontend if the API is on a different domain.

## Design decisions

- **Provider abstraction.** Ollama, OpenAI-compatible APIs, and Anthropic implement the same small interface: `list_models`, `stream_chat`, and `health`. Each provider turns its wire format (Ollama's NDJSON, OpenAI's SSE with a `[DONE]` terminator, Anthropic's typed stream events via the official SDK) into the same text deltas plus one final chunk with token usage. Supporting another kind of API means adding one class.
- **Namespaced model IDs.** The frontend sees models as `provider_id:model`, so two providers can offer a model with the same name. The ID is split on the *first* colon because Ollama tags contain colons: `ollama:llama3.2:1b` → provider `ollama`, model `llama3.2:1b`.
- **One normalized stream.** The browser only ever receives `data: {"delta": …}`, then `{"done": true, "usage": …}` or `{"error": …}`. The user's message is saved before the model is called. The reply is saved however the stream ends — when it finishes, when the provider fails, or when the user presses Stop — so partial answers survive a refresh.
- **Encrypted keys.** API keys are encrypted with Fernet before they're stored. The API only reports `has_key`. If a stored key can't be decrypted, only that provider shows as broken; the rest keep working.
- **Registry that follows the database.** Each request re-reads the enabled providers and rebuilds only the ones whose settings changed, so edits made in Settings apply immediately.
- **Retrieval that degrades gracefully.** Keyword search needs no model, so documents are always searchable. If embedding a document fails, it's still indexed for keywords, with a visible note. If embedding a question fails, the search falls back to keywords. Each chunk records which embedding model produced it, so vectors from different models are never compared, and a re-index button re-embeds everything after a model change.
- **Citations people can check.** Chunks never span pages, so every source points at one page. The passages are sent to the model with numbered tags and an instruction to cite them, and the same passages are saved with the reply, so the citations still match after a refresh. Weak matches are cut relative to the best one (BM25 under 40% of the top score; vectors more than 0.10 cosine below the best), so answers don't cite every loosely related file.
- **Refusals are not answers.** When Claude declines, the partial text is discarded rather than saved, and the user sees why. On Anthropic's API the newest models opt into server-side fallback (`fallbacks: "default"`), so most declines are answered by another Claude model on the same stream.
- **Tools as a bounded agent loop.** When the model asks for tools, the server runs them, sends the results back, and lets the model continue, for up to 5 rounds. A final round offers no tools, so the model must answer. Each provider uses its own native format: OpenAI's streamed `tool_calls` fragments, Ollama's whole calls, and Claude's `tool_use` / `tool_result` blocks, with thinking blocks replayed unchanged. The model only gets tools the user picked and an admin enabled. Bad arguments come back to the model as a tool error rather than failing the chat. The web reader resolves each host (including every redirect) and refuses private, loopback, and link-local addresses, so a prompt can't make the server read its own network.
- **Web search as retrieval.** Search results are treated like documents: each page is fetched through the same SSRF-guarded reader, split into passages, ranked against the question with BM25, and capped at two passages per page, so one site can't crowd out the rest. If a page can't be read, its search snippet stands in. The passages are labelled as reference material, not instructions, which reduces prompt injection from web pages. The search shows as a step in the reply, and its sources are saved with it.
- **Observable by default.** Every request gets an ID (returned as `X-Request-ID`) that appears on every log line written while handling it. Logs are JSON in production. Prometheus metrics are labelled by route template, not raw path, so one series covers every conversation ID. They include reply outcomes and token counts per provider. OpenTelemetry traces cover HTTP handling, outgoing provider calls and each SQL statement. The SQL spans use a small hook on SQLAlchemy's events, because the official instrumentation doesn't support SQLAlchemy 2.1 yet. Parameter values are never recorded.
- **Safe to run as many replicas.** On startup each backend waits for the database instead of crash-looping, and it runs migrations and first-run seeding under a Postgres advisory lock. Tested on k3s with two replicas: both started without restarts, and the migrations ran once.
- **An app shell that can't go stale.** The service worker never caches `/api` or pages, only content-hashed assets, so a deploy reaches installed apps on the next launch with no "update available" step. Offline, pages fall back to a static offline screen.
- **Channels without websockets.** Serverless hosts can't hold sockets open, so channels poll every 3 seconds (only while the tab is visible) for anything created or changed since the server time of the last poll. Edits, deletes and reactions update the message's `updated_at`, so one cheap query picks up every kind of change. A model's reply streams to the person who asked and is saved when it's finished, so everyone else sees it on their next poll.
- **Voice that degrades gracefully.** With no server engine, dictation uses the browser's SpeechRecognition and reading aloud uses speechSynthesis (split into sentences, because some browsers cut long utterances short). With an engine, the browser records with MediaRecorder and the server transcribes, so it works in every browser. Voice mode detects the end of speech locally, by watching for about 1.3 seconds of quiet after you speak, so no audio is streamed continuously. Replies are cleaned of markdown, code, links and citation markers before they're spoken.
- **Images live in the database.** Serverless hosts have no lasting disk, so generated images are stored as bytes (4 MB cap) and served from `/api/images/{id}` to their owner, or to anyone once the chat is shared. They're deleted with the reply, chat, or account they belong to. The model never sees the picture, so it's told the prompt and asked not to describe what it can't see.
- **Side-by-side answers in one request.** The user's message is saved once, then every model's reply streams at the same time on one connection, and each event is tagged with its column. Each model sees its own earlier answers, so comparisons stay fair over several turns. A web search runs once and is shared. Token usage is stored per reply for analytics.
- **A blind test that stays blind.** Arena replies are marked blind, and the API leaves out their model until one of them is rated, including in shared links. Arena replies can't be regenerated one at a time. The leaderboard is computed from ratings with Elo (K = 32, starting at 1000): in any message answered side by side, the better-rated reply wins and equal ratings tie.
- **Memory that stays small and in your control.** Memories are plain facts the user or the model wrote down on purpose (nothing is extracted from chats behind the user's back). They are added to the context after the chat's instructions. With 15 or fewer, all of them are included; beyond that, only the best keyword matches for the message plus the newest few, so the prompt doesn't grow without limit. The model saves memories through an ordinary tool call, so each save shows as a step in the reply.
- **One catalog for every model decision.** The model menu, chat requests, and the custom-model editor all go through the same catalog. A hidden model can't be used by ID either, a custom model resolves to its base model plus its instructions and knowledge, and a custom model whose base model is offline drops out of the menu instead of failing mid-chat.
- **Accounts without a session store.** A signed JWT in an HttpOnly, SameSite=Lax cookie identifies the user, so any serverless instance can verify it without shared memory. The token carries a per-user `session_version`: changing a password bumps it and signs out every other device. Roles are read from the database on each request, so approving, demoting, or deleting a user takes effect immediately. Login uses the same error and timing for unknown emails as for wrong passwords, so it doesn't reveal which accounts exist.
- **Admin-only provider settings.** Provider URLs and keys, and the connection-test endpoint (which makes the server call a URL), are restricted to admins. Other users only see the model list.
- **A demo you can safely make public.** The admin account is created from env vars at deploy time, so a stranger can't claim the site by signing up first. The rate limits count hits in the database, so they hold across serverless instances, and use only the `X-Forwarded-For` entries added by trusted proxies, so clients can't forge their IP to dodge them.
- **Vercel instead of a separate backend host.** Vercel runs FastAPI with streaming and lifespan support, and serves the built frontend from its CDN on the same domain. That avoids CORS and the 30–60 s cold start of a sleeping free container. Migrations and seeding run once per deploy instead of on every cold start.

## Project structure

```
backend/   FastAPI app (app/), providers (app/providers/), routers (app/routers/),
           Alembic migrations, tests, Dockerfile, Vercel config
frontend/  React app: api/ (typed client + SSE reader), components/, hooks/, pages/,
           nginx.conf and Dockerfile for the container image
docs/      Deployment guide and README images
```

## Credits

Inspired by [Open WebUI](https://github.com/open-webui/open-webui); independent implementation in React + FastAPI. No code, assets, or branding are taken from Open WebUI.
