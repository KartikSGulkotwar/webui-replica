"""Request IDs, JSON logs, readiness, and Prometheus metrics."""

import json
import logging

import respx
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from sqlmodel import SQLModel

from app.main import create_app
from app.models import Provider
from app.observability import JsonFormatter, request_id_var


def metric(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def metrics_app(settings):
    settings.metrics_token = "s3cret"
    app = create_app(settings)
    SQLModel.metadata.create_all(app.state.engine)
    return app


def test_request_ids(client) -> None:
    generated = client.get("/api/health").headers["x-request-id"]
    assert len(generated) == 32
    echoed = client.get("/api/health", headers={"X-Request-ID": "trace-abc.123"})
    assert echoed.headers["x-request-id"] == "trace-abc.123"
    # Anything odd is replaced rather than echoed into logs and headers.
    odd = client.get("/api/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert odd.headers["x-request-id"] != "bad id\nwith newline"


def test_readiness(client, monkeypatch) -> None:
    assert client.get("/api/ready").json() == {"status": "ready", "database": "up"}

    def broken():
        raise RuntimeError("db down")

    monkeypatch.setattr(client.app.state.engine, "connect", broken)
    resp = client.get("/api/ready")
    assert resp.status_code == 503 and resp.json()["database"] == "down"


def test_metrics_need_the_token(client, settings) -> None:
    assert client.get("/api/metrics").status_code == 404  # off without a token
    with TestClient(metrics_app(settings)) as c:
        assert c.get("/api/metrics").status_code == 401
        assert c.get("/api/metrics", headers={"Authorization": "Bearer nope"}).status_code == 401
        ok = c.get("/api/metrics", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/plain")
        assert "webui_build_info" in ok.text


def test_request_metrics_use_route_templates(settings) -> None:
    with TestClient(metrics_app(settings)) as c:
        route = "/api/conversations/{conversation_id}"
        before = metric("webui_http_requests_total", method="GET", route=route, status="401")
        c.get("/api/conversations/abc")
        c.get("/api/conversations/def")
        after = metric("webui_http_requests_total", method="GET", route=route, status="401")
        assert after - before == 2  # one series for every conversation id
        assert metric("webui_http_request_duration_seconds_count", method="GET", route=route) >= 2


@respx.mock
def test_chat_metrics(client, session) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url="http://o.test"))
    session.commit()
    respx.post("http://o.test/api/chat").respond(
        content=json.dumps(
            {"message": {"content": "hi"}, "done": True, "prompt_eval_count": 5, "eval_count": 2}
        ).encode()
        + b"\n"
    )
    done = metric("webui_chat_replies_total", provider="ollama", outcome="done")
    prompt = metric("webui_llm_tokens_total", provider="ollama", kind="prompt")
    conv = client.post("/api/conversations", json={}).json()["id"]
    client.post(
        "/api/chat/stream", json={"conversation_id": conv, "model_id": "ollama:m", "message": "x"}
    )
    assert metric("webui_chat_replies_total", provider="ollama", outcome="done") == done + 1
    assert metric("webui_llm_tokens_total", provider="ollama", kind="prompt") == prompt + 5
    assert metric("webui_active_streams") == 0


def test_json_log_lines() -> None:
    token = request_id_var.set("req-1")
    try:
        record = logging.LogRecord("app.request", logging.INFO, "", 0, "GET %s", ("/x",), None)
        record.status = 200
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["msg"] == "GET /x" and line["status"] == 200
    assert line["request_id"] == "req-1" and line["level"] == "info"


def test_query_spans() -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from sqlalchemy import create_engine, text

    from app.observability import trace_queries

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    engine = create_engine("sqlite://")
    trace_queries(engine, provider.get_tracer("test"))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("request"), engine.connect() as conn:
        conn.execute(text("SELECT :secret"), {"secret": "hunter2"})
        try:
            conn.execute(text("SELEC broken"))
        except Exception:
            pass
    spans = {s.name: s for s in exporter.get_finished_spans()}
    select = spans["db SELECT"]
    assert select.parent.span_id == spans["request"].context.span_id
    assert select.attributes["db.system"] == "sqlite"
    assert "hunter2" not in str(select.attributes)  # values are never recorded
    assert spans["db SELEC"].status.status_code.name == "ERROR"


def test_waits_for_the_database(monkeypatch) -> None:
    from sqlalchemy.exc import OperationalError

    from app import db

    calls = []

    class Flaky:
        def connect(self):
            calls.append(1)
            if len(calls) < 3:
                raise OperationalError("SELECT 1", {}, Exception("name not known"))
            return db.make_engine("sqlite://").connect()

    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    db.wait_for_database(Flaky(), timeout=10)
    assert len(calls) == 3

    calls.clear()
    monkeypatch.setattr(db.time, "monotonic", iter([0, 0, 100, 100]).__next__)

    class Down:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("down"))

    import pytest

    with pytest.raises(OperationalError):
        db.wait_for_database(Down(), timeout=5)
