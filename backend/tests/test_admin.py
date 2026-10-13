from fastapi.testclient import TestClient

from tests.conftest import signup


def test_admin_lists_and_manages_users(client, app) -> None:
    with TestClient(app) as other:
        pending = signup(other, "pending@example.com", "Pat")
        users = client.get("/api/admin/users").json()
        assert [(u["email"], u["role"]) for u in users] == [
            ("admin@example.com", "admin"),
            ("pending@example.com", "pending"),
        ]

        approved = client.patch(f"/api/admin/users/{pending['id']}", json={"role": "user"})
        assert approved.json()["role"] == "user"
        assert other.get("/api/conversations").status_code == 200  # takes effect immediately

        promoted = client.patch(f"/api/admin/users/{pending['id']}", json={"role": "admin"})
        assert promoted.json()["role"] == "admin"
        assert other.get("/api/admin/users").status_code == 200

        assert (
            client.patch(
                f"/api/admin/users/{pending['id']}", json={"role": "superuser"}
            ).status_code
            == 422
        )
        assert client.patch("/api/admin/users/nope", json={"role": "user"}).status_code == 404


def test_admin_cannot_lock_themselves_out(client) -> None:
    me = client.get("/api/auth/me").json()
    assert client.patch(f"/api/admin/users/{me['id']}", json={"role": "user"}).status_code == 400
    assert client.delete(f"/api/admin/users/{me['id']}").status_code == 400


def test_deleting_a_user_removes_their_chats(client, user_client) -> None:
    conv = user_client.post("/api/conversations", json={"title": "Mine"}).json()["id"]
    target = next(u for u in client.get("/api/admin/users").json() if u["role"] == "user")

    assert client.delete(f"/api/admin/users/{target['id']}").status_code == 204

    assert user_client.get("/api/auth/me").status_code == 401  # session no longer valid
    assert [u["email"] for u in client.get("/api/admin/users").json()] == ["admin@example.com"]
    assert client.get(f"/api/conversations/{conv}").status_code == 404


def test_signup_settings(client, app) -> None:
    assert client.get("/api/admin/settings").json() == {
        "enable_signup": True,
        "default_user_role": "pending",
        "enabled_tools": [
            "calculator",
            "current_time",
            "fetch_url",
            "web_search",
            "add_memory",
            "generate_image",
        ],
        "arena_models": [],
    }
    client.put("/api/admin/settings", json={"enable_signup": True, "default_user_role": "user"})
    with TestClient(app) as a:
        assert signup(a, "auto@example.com")["role"] == "user"

    client.put("/api/admin/settings", json={"enable_signup": False, "default_user_role": "user"})
    with TestClient(app) as b:
        assert b.get("/api/config").json()["signup_enabled"] is False
        resp = b.post(
            "/api/auth/signup",
            json={"name": "B", "email": "b@example.com", "password": "password123"},
        )
        assert resp.status_code == 403 and "disabled" in resp.json()["detail"]

    bad = client.put(
        "/api/admin/settings", json={"enable_signup": True, "default_user_role": "admin"}
    )
    assert bad.status_code == 422


def test_admin_routes_need_admin(user_client, anon_client) -> None:
    for c, code in ((user_client, 403), (anon_client, 401)):
        assert c.get("/api/admin/users").status_code == code
        assert c.patch("/api/admin/users/x", json={"role": "admin"}).status_code == code
        assert c.delete("/api/admin/users/x").status_code == code
        assert c.get("/api/admin/settings").status_code == code
        body = {"enable_signup": True, "default_user_role": "user"}
        assert c.put("/api/admin/settings", json=body).status_code == code
