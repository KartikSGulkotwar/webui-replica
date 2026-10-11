from fastapi.testclient import TestClient

import app.main as main_module
from app.main import create_app


def test_serves_built_frontend_when_present(settings, tmp_path, monkeypatch) -> None:
    backend = tmp_path / "backend"
    static = backend / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>WebUI Replica</title>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(main_module, "BACKEND_DIR", backend)

    client = TestClient(create_app(settings))

    assert client.get("/api/health").json()["status"] == "ok"  # API wins
    assert client.get("/assets/app.js").text == "console.log(1)"
    page = client.get("/c/some-conversation", headers={"Accept": "text/html"})
    assert page.status_code == 200 and "WebUI Replica" in page.text  # SPA fallback


def test_no_frontend_routes_without_build(settings, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main_module, "BACKEND_DIR", tmp_path)
    client = TestClient(create_app(settings))
    assert client.get("/", headers={"Accept": "text/html"}).status_code == 404
