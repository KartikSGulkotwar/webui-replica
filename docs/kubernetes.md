# Running WebUI Replica on Kubernetes

The manifests in [`deploy/kubernetes/`](../deploy/kubernetes) run the whole app on any cluster:
Postgres with pgvector, two or more backend replicas, the frontend on nginx, and an Ingress.
They were tested on k3s (Kubernetes 1.31).

## What you get

| Piece | Details |
|---|---|
| `postgres.yaml` | StatefulSet with a 5 Gi volume, `pg_isready` probes. Swap it for a managed database by pointing `DATABASE_URL` elsewhere. |
| `backend.yaml` | Deployment (2 replicas, rolling updates with no downtime), HorizontalPodAutoscaler (2–6 on CPU), PodDisruptionBudget, runs as non-root with no privilege escalation, Prometheus annotations. |
| `frontend.yaml` | nginx serving the built app; it also proxies `/api` to the backend Service. |
| `ingress.yaml` | ingress-nginx with buffering off and long read timeouts, so streamed replies arrive token by token. |
| `network-policy.yaml` | Only backend pods can reach Postgres. |
| `ollama.yaml` (optional) | A model server in the cluster with a 20 Gi model volume. |
| `service-monitor.yaml` (optional) | Prometheus Operator scraping of every backend pod. |

**Health checks.** `/api/health` says the process is alive (startup and liveness probes).
`/api/ready` also checks the database (readiness probe), so a pod that loses its database stops
getting traffic instead of returning errors.

**Several replicas starting at once.** Each backend waits for the database (up to
`DATABASE_WAIT_SECONDS`) instead of crash-looping, and migrations plus first-run seeding run under a
Postgres advisory lock. The first replica does the work, and the others wait and then find it done.
Sessions (JWT cookies) and rate limits live in the database, so any replica can serve any request.

## Deploy

```bash
# 1. Build and push the images (or use your CI)
docker build -t ghcr.io/<you>/webui-replica-backend:1.0 backend
docker build -t ghcr.io/<you>/webui-replica-frontend:1.0 frontend
docker push ghcr.io/<you>/webui-replica-backend:1.0
docker push ghcr.io/<you>/webui-replica-frontend:1.0

# 2. Secrets (git-ignored) and settings
cp deploy/kubernetes/secrets.env.example deploy/kubernetes/secrets.env
#    edit secrets.env; set your images in kustomization.yaml (images:),
#    and PUBLIC_URL / the Ingress host

# 3. Apply
kubectl apply -k deploy/kubernetes
kubectl -n webui rollout status deploy/backend

# Try it without an Ingress:
kubectl -n webui port-forward svc/frontend 8080:80   # http://localhost:8080
```

Sign in with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `secrets.env`.

## Observability

- **Logs** are JSON lines (`LOG_FORMAT=json`), one per API request with method, route, status,
  duration and a request ID. The ID is also returned in the `X-Request-ID` header (send your own to
  follow a request through your systems). Any log stack (Loki, ELK, Cloud Logging) can index them.
- **Metrics:** Prometheus format at `/api/metrics`, which needs `Authorization: Bearer <METRICS_TOKEN>`.
  Every pod keeps its own counters, so scrape each pod (the ServiceMonitor does). The metrics are:
  - `webui_http_requests_total` and `webui_http_request_duration_seconds`, by route template;
  - `webui_chat_replies_total`, by provider and outcome (done, error, declined, stopped, empty);
  - `webui_llm_tokens_total` (prompt and completion tokens per provider);
  - `webui_tool_calls_total`;
  - `webui_active_streams`.
- **Traces:** set `OTEL_EXPORTER_OTLP_ENDPOINT` (for example an OpenTelemetry Collector, Jaeger or
  Tempo on port 4318). Each request becomes a trace with spans for the HTTP handling, every SQL
  statement (parameter values are never recorded) and every outgoing call to a model provider.
