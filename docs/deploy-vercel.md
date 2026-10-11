# Deploying the public demo (Vercel + Neon + Groq)

One Vercel project serves both the React frontend and the FastAPI backend from the
same domain. Neon provides Postgres. Groq provides a free OpenAI-compatible model.

```
Browser ──▶ Vercel CDN ── static files (React build)
              │
              └─▶ Vercel Function (FastAPI) ──▶ Neon Postgres
                                           └─▶ Groq API
```

Total cost: $0 on the free tiers. Allow about 20 minutes.

## 1. Put the code on GitHub

```bash
gh repo create webui-replica --public --source=. --push
```

(Or create an empty repo on github.com and `git push` to it.)

## 2. Get a Groq API key

1. Sign in at <https://console.groq.com>.
2. **API Keys → Create API Key**. Copy it (starts with `gsk_`). It's shown once.

## 3. Create the database on Neon

1. Sign in at <https://neon.tech> and create a project (any region close to you).
2. On the dashboard, click **Connect**, turn on **Connection pooling**, and copy the
   connection string. It looks like
   `postgresql://user:password@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require`.

Use it as-is: the backend switches `postgresql://` to the psycopg 3 driver itself.

## 4. Generate an encryption key

```bash
openssl rand -base64 32 | tr '+/' '-_'
```

Keep it somewhere safe. If it changes, stored API keys can no longer be decrypted.

## 5. Create the Vercel project

1. Sign in at <https://vercel.com> → **Add New… → Project** → import the GitHub repo.
2. **Root Directory**: click **Edit** and choose `backend`.
   - Vercel detects **FastAPI** (`app/main.py`).
   - Leave the build settings empty; the build step is defined in
     `backend/pyproject.toml` (`python -m app.vercel_build`).
   - Under Root Directory, keep **"Include files outside the root directory in the
     Build Step"** enabled: the build compiles `../frontend`.
3. **Environment Variables** (all environments):

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | Neon connection string from step 3 |
   | `ENCRYPTION_KEY` | key from step 4 |
   | `OPENAI_COMPAT_BASE_URL` | `https://api.groq.com/openai/v1` |
   | `OPENAI_COMPAT_API_KEY` | Groq key from step 2 |
   | `OLLAMA_BASE_URL` | `http://localhost:11434` (shows Ollama as a configured but offline provider, which is honest for a cloud demo) |
   | `PROVIDERS_READ_ONLY` | `true` |
   | `AUTO_MIGRATE` | `false` |
   | `TRUSTED_PROXY_HOPS` | `1` |
   | `CHAT_RATE_LIMIT_PER_MINUTE` | `20` |
   | `FRONTEND_ORIGIN` | `https://<your-project>.vercel.app` (update after the first deploy if the name differs) |

4. Click **Deploy**.

The build step migrates the database, seeds the Groq and Ollama providers (only into
an empty table), builds the frontend, and copies it into `backend/static`, which
FastAPI serves with `app.frontend()` and Vercel promotes to its CDN.

## 6. Check it

Open `https://<your-project>.vercel.app` and confirm:

- [ ] The page loads; the model menu lists Groq models with a green dot and Ollama
      with a red one.
- [ ] A reply streams in word by word, and **Stop** works.
- [ ] Refreshing keeps the conversation; rename and delete work.
- [ ] **Settings** shows the read-only notice and no edit buttons.
- [ ] It works on your phone.

If the build fails, open the deployment's **Build Logs**. Common causes:

| Log says | Fix |
|---|---|
| `DATABASE_URL must point at Postgres` | Add `DATABASE_URL` to the environment variables, then redeploy |
| `…/frontend not found` | Enable "Include files outside the root directory in the Build Step" |
| `ENCRYPTION_KEY is not set` | Add `ENCRYPTION_KEY`, then redeploy |
| Connection or SSL errors | Use Neon's **pooled** connection string including `?sslmode=require` |

## Changing providers later

The demo's Settings page is read-only on purpose: there's no login, so anyone could
otherwise edit providers. To change the Groq key or add a provider, run the backend
locally against the Neon database with editing allowed:

```bash
cd backend
DATABASE_URL='<neon url>' ENCRYPTION_KEY='<same key>' PROVIDERS_READ_ONLY=false \
  .venv/bin/uvicorn app.main:app --port 8000
# in another terminal: cd frontend && npm run dev → http://localhost:5173/settings
```

Changes take effect on the live site immediately.

## Limits to know about

- **Request length:** Vercel's Hobby plan stops a request after 300 seconds
  (`maxDuration` in `backend/vercel.json`). Groq replies take a few seconds.
- **Groq free tier:** has its own per-minute and per-day quotas. When they're used
  up, users see Groq's error message in the chat.
- **Neon free tier:** the database sleeps when idle; the first request afterwards
  takes a moment longer.
