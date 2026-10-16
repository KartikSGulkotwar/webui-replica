"""Logs, metrics and traces.

- Every request gets an ID (the caller's X-Request-ID, or a new one), returned
  in the response and attached to every log line written while handling it.
- Logs are JSON lines in production (one object per line, easy to search in
  Vercel, Kubernetes or any log stack) and plain text in a terminal.
- Prometheus metrics are served at /api/metrics when METRICS_TOKEN is set.
- OpenTelemetry tracing turns on when OTEL_EXPORTER_OTLP_ENDPOINT is set.
"""

import contextvars
import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, datetime

from prometheus_client import Counter, Gauge, Histogram, Info

logger = logging.getLogger("app.request")

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# --- metrics -------------------------------------------------------------------------

BUILD_INFO = Info("webui_build", "Version of the running backend")
HTTP_REQUESTS = Counter(
    "webui_http_requests_total", "HTTP requests handled", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "webui_http_request_duration_seconds",
    "Time to finish a response (streams included)",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
ACTIVE_STREAMS = Gauge("webui_active_streams", "Chat replies being streamed right now")
CHAT_REPLIES = Counter(
    "webui_chat_replies_total",
    "Chat replies by how they ended (done, error, declined, stopped)",
    ["provider", "outcome"],
)
LLM_TOKENS = Counter("webui_llm_tokens_total", "Tokens reported by providers", ["provider", "kind"])
TOOL_CALLS = Counter("webui_tool_calls_total", "Tool runs", ["tool", "outcome"])


# --- logging ------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the request ID and any `extra` fields."""

    _STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if request_id := request_id_var.get():
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in self._STANDARD and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = f"{record.levelname} {record.name}: {record.getMessage()}"
        if request_id := request_id_var.get():
            line += f" [{request_id}]"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(log_format: str = "auto", level: str = "INFO") -> None:
    """`auto` means JSON unless writing to a terminal."""
    use_json = log_format == "json" or (log_format == "auto" and not sys.stderr.isatty())
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if use_json else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Uvicorn's own access log would duplicate ours.
    logging.getLogger("uvicorn.access").disabled = True


# --- per-request middleware ------------------------------------------------------------


class ObservabilityMiddleware:
    """Request ID, a log line and metrics for every HTTP request.

    Plain ASGI (not BaseHTTPMiddleware) so streamed replies pass straight
    through and their duration is measured to the last byte.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500

        async def send_with_id(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [
                    *message["headers"],
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            duration = time.perf_counter() - start
            # The route template ("/api/conversations/{conversation_id}") keeps
            # metrics from growing a series per ID; unknown paths share one.
            route = getattr(scope.get("route"), "path", None)
            path = scope.get("path", "")
            if route is None:
                route = "static" if not path.startswith("/api/") else "unmatched"
            method = scope.get("method", "")
            if route != "/api/metrics":
                HTTP_REQUESTS.labels(method, route, str(status)).inc()
                HTTP_LATENCY.labels(method, route).observe(duration)
            if path.startswith("/api/") and route not in ("/api/health", "/api/metrics"):
                logger.info(
                    "%s %s %s %.0fms",
                    method,
                    path,
                    status,
                    duration * 1000,
                    extra={
                        "method": method,
                        "path": path,
                        "route": route,
                        "status": status,
                        "duration_ms": round(duration * 1000, 1),
                    },
                )
            request_id_var.reset(token)


# --- tracing ------------------------------------------------------------------------


def setup_tracing(app, engine, service_name: str, version: str) -> bool:
    """Send OpenTelemetry traces to the OTLP endpoint in OTEL_EXPORTER_OTLP_ENDPOINT
    (the SDK reads the standard OTEL_* variables). Imported lazily: it's only
    paid for when used."""
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name, "service.version": version})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls="api/health,api/metrics"
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    trace_queries(engine, provider.get_tracer("app.db"))
    return True


def trace_queries(engine, tracer) -> None:
    """A span per SQL statement. (The SQLAlchemy instrumentation package doesn't
    support SQLAlchemy 2.1 yet, and this is all it would do.) The statement is
    recorded with placeholders; parameter values never are."""
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def start(conn, cursor, statement, parameters, context, executemany):
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "SQL"
        context._otel_span = tracer.start_span(
            f"db {verb}",
            kind=SpanKind.CLIENT,
            attributes={"db.system": engine.dialect.name, "db.statement": statement[:1000]},
        )

    @event.listens_for(engine, "after_cursor_execute")
    def end(conn, cursor, statement, parameters, context, executemany):
        span = getattr(context, "_otel_span", None)
        if span is not None:
            span.end()

    @event.listens_for(engine, "handle_error")
    def failed(exception_context):
        span = getattr(exception_context.execution_context, "_otel_span", None)
        if span is not None:
            span.record_exception(exception_context.original_exception)
            span.set_status(Status(StatusCode.ERROR))
            span.end()
