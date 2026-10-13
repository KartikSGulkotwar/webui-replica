"""Image engines, the Image toggle and tool in chat, and who can see an image."""

import base64
import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import select

import app.routers.chat as chat_module
import app.tools.registry as registry_module
from app.images.engines import POLLINATIONS_URL, Image, ImageConfig, ImageError, generate
from app.images.service import make_image_prompt
from app.models import GeneratedImage, Provider
from app.routers.chat import stream_and_persist
from app.schemas import ChatMessage, ChatParams, StreamChunk, ToolCall
from app.tools.registry import TOOLS, ToolContext, run_tool
from tests.conftest import signup
from tests.test_tool_calling import ScriptedProvider, events

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture
def conv(client) -> str:
    return client.post("/api/conversations", json={}).json()["id"]


@pytest.fixture
def fake_engine(monkeypatch):
    """Every engine call returns a small PNG and records the prompt."""
    prompts: list[str] = []

    async def fake(http, config, prompt):
        prompts.append(prompt)
        return Image(PNG, "image/png")

    monkeypatch.setattr(chat_module, "generate", fake)
    monkeypatch.setattr(registry_module, "generate", fake)
    return prompts


# --- engines ---------------------------------------------------------------------------


def test_config_enabled() -> None:
    assert ImageConfig("pollinations").enabled
    assert not ImageConfig("").enabled
    assert not ImageConfig("openai", base_url="https://x").enabled  # needs a model
    assert ImageConfig("openai", base_url="https://x", model="gpt-image-1").enabled
    assert ImageConfig("automatic1111", base_url="http://sd").enabled
    assert ImageConfig("pollinations", size="1536x1024").dimensions == (1536, 1024)


@respx.mock
async def test_pollinations(http) -> None:
    route = respx.get(url__startswith=POLLINATIONS_URL).respond(
        content=JPEG, headers={"content-type": "image/jpeg"}
    )
    image = await generate(http, ImageConfig("pollinations", size="512x512"), "a red fox")
    assert image == Image(JPEG, "image/jpeg")
    request = route.calls.last.request
    assert "/prompt/a%20red%20fox?" in str(request.url)
    assert request.url.params["width"] == "512" and request.url.params["nologo"] == "true"
    assert "Authorization" not in request.headers
    await generate(http, ImageConfig("pollinations", api_key="tok"), "a red fox")
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"


@respx.mock
async def test_pollinations_waits_out_its_rate_limit(http, monkeypatch) -> None:
    monkeypatch.setattr("app.images.engines.POLLINATIONS_RETRY_PAUSES", (0, 0))
    route = respx.get(url__startswith=POLLINATIONS_URL)
    route.side_effect = [httpx.Response(402), httpx.Response(429), httpx.Response(200, content=PNG)]
    assert (await generate(http, ImageConfig("pollinations"), "x")).data == PNG
    route.side_effect = [httpx.Response(402)] * 3
    with pytest.raises(ImageError, match="free tier is busy"):
        await generate(http, ImageConfig("pollinations"), "x")


@respx.mock
async def test_openai_compatible(http) -> None:
    gpt = respx.post("https://api.test/v1/images/generations").respond(
        json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]}
    )
    config = ImageConfig("openai", base_url="https://api.test/v1", api_key="k", model="gpt-image-1")
    assert (await generate(http, config, "cat")).mime == "image/png"
    body = json.loads(gpt.calls.last.request.content)
    assert body == {"model": "gpt-image-1", "prompt": "cat", "n": 1, "size": "1024x1024"}
    assert gpt.calls.last.request.headers["Authorization"] == "Bearer k"

    # DALL·E is asked for base64 too; a link-only answer is downloaded.
    gpt.respond(json={"data": [{"url": "https://cdn.test/img.png"}]})
    respx.get("https://cdn.test/img.png").respond(content=PNG)
    dalle = ImageConfig("openai", base_url="https://api.test/v1", model="dall-e-3")
    assert (await generate(http, dalle, "dog")).data == PNG
    assert json.loads(gpt.calls.last.request.content)["response_format"] == "b64_json"


@respx.mock
async def test_automatic1111(http) -> None:
    route = respx.post("http://sd.test/sdapi/v1/txt2img").respond(
        json={"images": [base64.b64encode(PNG).decode()]}
    )
    config = ImageConfig("automatic1111", base_url="http://sd.test", api_key="me:secret")
    assert (await generate(http, config, "x")).data == PNG
    expected = "Basic " + base64.b64encode(b"me:secret").decode()
    assert route.calls.last.request.headers["Authorization"] == expected


@respx.mock
async def test_engine_errors(http, monkeypatch) -> None:
    config = ImageConfig("openai", base_url="https://api.test/v1", model="gpt-image-1")
    route = respx.post("https://api.test/v1/images/generations")
    route.respond(401, json={"error": {"message": "bad key"}})
    with pytest.raises(ImageError, match="rejected the API key"):
        await generate(http, config, "x")
    route.respond(400, json={"error": {"message": "Rejected by the safety system"}})
    with pytest.raises(ImageError, match="declined this prompt"):
        await generate(http, config, "x")
    respx.get(url__startswith=POLLINATIONS_URL).respond(content=b"<html>not an image</html>")
    with pytest.raises(ImageError, match="didn't return an image"):
        await generate(http, ImageConfig("pollinations"), "x")
    monkeypatch.setattr("app.images.engines.MAX_BYTES", 10)
    respx.get(url__startswith=POLLINATIONS_URL).respond(content=PNG)
    with pytest.raises(ImageError, match="too large"):
        await generate(http, ImageConfig("pollinations"), "x")
    with pytest.raises(ImageError, match="isn't set up"):
        await generate(http, ImageConfig(""), "x")


# --- prompts -----------------------------------------------------------------------------


async def test_first_request_is_drawn_as_written() -> None:
    provider = ScriptedProvider([])
    history = [ChatMessage(role="user", content="A lighthouse at dusk")]
    assert await make_image_prompt(provider, "m", history) == "A lighthouse at dusk"


async def test_follow_up_is_rewritten() -> None:
    provider = ScriptedProvider(
        [[StreamChunk(delta='"A blue lighthouse at dusk, oil painting"'), StreamChunk(done=True)]]
    )
    history = [
        ChatMessage(role="user", content="A lighthouse at dusk, oil painting"),
        ChatMessage(role="assistant", content="Here it is."),
        ChatMessage(role="user", content="Make it blue"),
    ]
    assert await make_image_prompt(provider, "m", history) == (
        "A blue lighthouse at dusk, oil painting"
    )


# --- chat --------------------------------------------------------------------------------


def context(app, client, conv, http) -> ToolContext:
    return ToolContext(
        http=http,
        engine=app.state.engine,
        user_id=client.get("/api/auth/me").json()["id"],
        conversation_id=conv,
        image_config=ImageConfig("pollinations"),
    )


async def test_image_toggle_makes_an_image_then_replies(
    app, client, conv, http, fake_engine
) -> None:
    provider = ScriptedProvider([[StreamChunk(delta="Here's your fox."), StreamChunk(done=True)]])
    out = [
        e
        async for e in stream_and_persist(
            app.state.engine,
            provider,
            conv,
            "ollama:m",
            "m",
            [ChatMessage(role="user", content="A red fox in snow")],
            ChatParams(),
            tool_context=context(app, client, conv, http),
            make_image=True,
        )
    ]
    evts = events(out)
    assert evts[0]["tool_call"]["arguments"] == {"prompt": "A red fox in snow"}
    assert evts[1]["tool_result"] == {
        "id": "generate_image",
        "output": "Created 1 image",
        "error": False,
    }
    image_id = evts[2]["images"][0]["id"]
    assert fake_engine == ["A red fox in snow"]
    # The model is told an image is shown, before the user's message.
    sent = provider.seen[0][0]
    assert sent[0].role == "system" and "A red fox in snow" in sent[0].content

    saved = client.get(f"/api/conversations/{conv}").json()["messages"][-1]
    assert saved["images"] == [{"id": image_id, "prompt": "A red fox in snow"}]
    assert saved["tools"][0]["name"] == "generate_image"
    resp = client.get(f"/api/images/{image_id}")
    assert resp.content == PNG and resp.headers["content-type"] == "image/png"


async def test_failed_image_is_reported(app, client, conv, http, monkeypatch) -> None:
    async def broken(http, config, prompt):
        raise ImageError("Pollinations rate limit reached; try again later")

    monkeypatch.setattr(chat_module, "generate", broken)
    provider = ScriptedProvider([[StreamChunk(delta="Sorry."), StreamChunk(done=True)]])
    out = [
        e
        async for e in stream_and_persist(
            app.state.engine,
            provider,
            conv,
            "ollama:m",
            "m",
            [ChatMessage(role="user", content="a cat")],
            ChatParams(),
            tool_context=context(app, client, conv, http),
            make_image=True,
        )
    ]
    evts = events(out)
    assert evts[1]["tool_result"]["error"] is True
    assert not any("images" in e for e in evts)
    assert "rate limit" in provider.seen[0][0][0].content


async def test_generate_image_tool_attaches_images(app, client, conv, http, fake_engine) -> None:
    provider = ScriptedProvider(
        [
            [
                StreamChunk(
                    done=True,
                    tool_calls=[
                        ToolCall(id="c", name="generate_image", arguments={"prompt": "a robot"})
                    ],
                )
            ],
            [StreamChunk(delta="Done!"), StreamChunk(done=True)],
        ]
    )
    out = [
        e
        async for e in stream_and_persist(
            app.state.engine,
            provider,
            conv,
            "ollama:m",
            "m",
            [ChatMessage(role="user", content="draw a robot")],
            ChatParams(),
            None,
            [TOOLS["generate_image"]],
            context(app, client, conv, http),
        )
    ]
    evts = events(out)
    images = next(e["images"] for e in evts if "images" in e)
    assert images[0]["prompt"] == "a robot"
    saved = client.get(f"/api/conversations/{conv}").json()["messages"][-1]
    assert saved["images"] == images and saved["content"] == "Done!"


async def test_tool_without_engine(http) -> None:
    out = await run_tool("generate_image", {"prompt": "x"}, ToolContext(http=http))
    assert out.error and "isn't set up" in out.output


# --- endpoints --------------------------------------------------------------------------


def set_engine(client, **body) -> None:
    resp = client.put("/api/admin/images", json={"engine": "pollinations", **body})
    assert resp.status_code == 200, resp.text


def test_admin_image_settings(client, user_client) -> None:
    assert client.get("/api/admin/images").json() == {
        "engine": "",
        "base_url": "",
        "model": "",
        "size": "1024x1024",
        "has_key": False,
    }
    assert client.get("/api/config").json()["image_generation"] is False
    assert "generate_image" not in [t["id"] for t in user_client.get("/api/tools").json()]
    assert client.put("/api/admin/images", json={"engine": "openai"}).status_code == 422
    assert (
        client.put(
            "/api/admin/images", json={"engine": "openai", "base_url": "https://api.openai.com/v1"}
        ).status_code
        == 422
    )
    saved = client.put(
        "/api/admin/images",
        json={
            "engine": "openai",
            "base_url": "https://api.openai.com/v1/",
            "model": "gpt-image-1",
            "api_key": "sk-x",
            "size": "1024x1536",
        },
    ).json()
    assert saved["base_url"] == "https://api.openai.com/v1" and saved["has_key"]
    assert client.put("/api/admin/images", json={"engine": "x"}).status_code == 422
    assert user_client.get("/api/admin/images").status_code == 403
    set_engine(client)
    assert client.get("/api/config").json()["image_generation"] is True
    assert "generate_image" in [t["id"] for t in user_client.get("/api/tools").json()]


@respx.mock
def test_admin_test_image(client) -> None:
    set_engine(client, size="512x512")
    respx.get(url__startswith=POLLINATIONS_URL).respond(content=JPEG)
    data = client.post("/api/admin/images/test", json={"prompt": "a test"}).json()
    assert data["ok"] and data["data_url"].startswith("data:image/jpeg;base64,")


def test_chat_refuses_images_when_off(client, conv, session) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url="http://o.test"))
    session.commit()
    resp = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:m",
            "message": "hi",
            "image_generation": True,
        },
    )
    assert resp.status_code == 400


@respx.mock
def test_images_end_to_end(app, client, user_client, conv, session, fake_engine) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url="http://o.test"))
    session.commit()
    set_engine(client)
    respx.post("http://o.test/api/chat").respond(
        content=json.dumps({"message": {"content": "Here it is"}, "done": True}).encode() + b"\n"
    )
    body = {"conversation_id": conv, "model_id": "ollama:m", "image_generation": True}
    resp = client.post("/api/chat/stream", json={**body, "message": "a fox"})
    assert '"images"' in resp.text
    image_id = client.get(f"/api/conversations/{conv}").json()["messages"][-1]["images"][0]["id"]

    # Only the owner can see it…
    assert user_client.get(f"/api/images/{image_id}").status_code == 404
    with TestClient(app) as anonymous:
        assert anonymous.get(f"/api/images/{image_id}").status_code == 404
        # …until the chat is shared.
        share = client.post(f"/api/conversations/{conv}/share").json()["share_id"]
        shared = client.get(f"/api/shared/{share}").json()["messages"]
        assert shared[-1]["images"][0]["id"] == image_id
        assert anonymous.get(f"/api/images/{image_id}").status_code == 200

    # Regenerating replaces the image; deleting the chat removes the rest.
    client.post("/api/chat/stream", json={**body, "action": "regenerate"})
    assert session.get(GeneratedImage, image_id) is None
    assert len(session.exec(select(GeneratedImage)).all()) == 1
    client.delete(f"/api/conversations/{conv}")
    assert session.exec(select(GeneratedImage)).all() == []


def test_deleting_a_user_deletes_their_images(app, client, session) -> None:
    with TestClient(app) as other:
        user = signup(other, "other@example.com")
        client.patch(f"/api/admin/users/{user['id']}", json={"role": "user"})
        session.add(GeneratedImage(owner_id=user["id"], prompt="p", mime="image/png", data=PNG))
        session.commit()
        client.delete(f"/api/admin/users/{user['id']}")
    assert session.exec(select(GeneratedImage)).all() == []


def test_unknown_image(client) -> None:
    assert client.get("/api/images/nope").status_code == 404
