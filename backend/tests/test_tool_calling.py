"""Provider wire formats for tool calls, and the agent loop in the chat endpoint."""

import json

import anthropic
import httpx
import httpx2
import pytest
import respx

import app.providers.anthropic as anthropic_module
from app.models import Provider
from app.providers.anthropic import AnthropicProvider, split_system
from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from app.providers.ollama import to_wire as ollama_wire
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.openai_compat import to_wire as openai_wire
from app.routers.chat import stream_and_persist
from app.schemas import ChatMessage, ChatParams, StreamChunk, ToolCall, ToolSpec
from app.tools.registry import TOOLS, ToolContext

CALC = ToolSpec(name="calculator", description="math", parameters=TOOLS["calculator"].parameters)

TOOL_TURNS = [
    ChatMessage(role="user", content="What is 23*47?"),
    ChatMessage(
        role="assistant",
        content="Let me compute.",
        tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "23*47"})],
    ),
    ChatMessage(role="tool", tool_call_id="c1", name="calculator", content="1081"),
]


# --- wire formats -----------------------------------------------------------------


def test_openai_wire_format() -> None:
    assert openai_wire(TOOL_TURNS) == [
        {"role": "user", "content": "What is 23*47?"},
        {
            "role": "assistant",
            "content": "Let me compute.",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "calculator", "arguments": '{"expression": "23*47"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "1081"},
    ]


def test_ollama_wire_format() -> None:
    assert ollama_wire(TOOL_TURNS)[1:] == [
        {
            "role": "assistant",
            "content": "Let me compute.",
            "tool_calls": [
                {"function": {"name": "calculator", "arguments": {"expression": "23*47"}}}
            ],
        },
        {"role": "tool", "content": "1081", "tool_name": "calculator"},
    ]


def test_anthropic_groups_tool_results_in_one_user_turn() -> None:
    turns = [
        ChatMessage(role="system", content="Be exact."),
        ChatMessage(role="user", content="Two sums"),
        ChatMessage(
            role="assistant",
            provider_state=[
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {
                    "type": "tool_use",
                    "id": "a",
                    "name": "calculator",
                    "input": {"expression": "1+1"},
                },
            ],
            tool_calls=[ToolCall(id="a", name="calculator", arguments={})],
        ),
        ChatMessage(role="tool", tool_call_id="a", name="calculator", content="2"),
        ChatMessage(role="tool", tool_call_id="b", name="calculator", content="bad", is_error=True),
    ]
    system, rest = split_system(turns)
    assert system == "Be exact."
    assert rest[1]["content"][0] == {
        "type": "thinking",
        "thinking": "",
        "signature": "sig",
    }  # replayed as-is
    assert rest[2] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "a", "content": "2", "is_error": False},
            {"type": "tool_result", "tool_use_id": "b", "content": "bad", "is_error": True},
        ],
    }


@respx.mock
async def test_openai_assembles_streamed_tool_call(http) -> None:
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_9",
                                "function": {"name": "calculator", "arguments": ""},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"expre'}}]}}
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [{"index": 0, "function": {"arguments": 'ssion": "6*7"}'}}]
                    }
                }
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    route = respx.post("https://api.test/v1/chat/completions").respond(content=body.encode())
    provider = OpenAICompatProvider(id="g", name="G", base_url="https://api.test/v1", client=http)
    out = [c async for c in provider.stream_chat("m", TOOL_TURNS[:1], ChatParams(), [CALC])]
    assert out[-1].tool_calls == [
        ToolCall(id="call_9", name="calculator", arguments={"expression": "6*7"})
    ]
    sent = json.loads(route.calls.last.request.content)
    assert sent["tools"][0]["function"]["name"] == "calculator"


@respx.mock
async def test_ollama_tool_calls(http) -> None:
    lines = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "calculator", "arguments": {"expression": "2+2"}}}
                ],
            },
            "done": False,
        },
        {"message": {"content": ""}, "done": True},
    ]
    respx.post("http://o.test/api/chat").respond(
        content=b"".join(json.dumps(x).encode() + b"\n" for x in lines)
    )
    provider = OllamaProvider(id="o", name="O", base_url="http://o.test", client=http)
    out = [c async for c in provider.stream_chat("m", TOOL_TURNS[:1], ChatParams(), [CALC])]
    assert out == [
        StreamChunk(
            done=True,
            tool_calls=[ToolCall(id="call_0", name="calculator", arguments={"expression": "2+2"})],
        )
    ]


def anthropic_stream(blocks: list[dict], stop_reason: str) -> bytes:
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 5, "output_tokens": 1},
            },
        }
    ]
    for i, b in enumerate(blocks):
        if b["type"] == "text":
            events += [
                {
                    "type": "content_block_start",
                    "index": i,
                    "content_block": {"type": "text", "text": ""},
                },
                {
                    "type": "content_block_delta",
                    "index": i,
                    "delta": {"type": "text_delta", "text": b["text"]},
                },
            ]
        else:
            events += [
                {
                    "type": "content_block_start",
                    "index": i,
                    "content_block": {
                        "type": "tool_use",
                        "id": b["id"],
                        "name": b["name"],
                        "input": {},
                    },
                },
                {
                    "type": "content_block_delta",
                    "index": i,
                    "delta": {"type": "input_json_delta", "partial_json": b["json"][:5]},
                },
                {
                    "type": "content_block_delta",
                    "index": i,
                    "delta": {"type": "input_json_delta", "partial_json": b["json"][5:]},
                },
            ]
        events.append({"type": "content_block_stop", "index": i})
    events += [
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 9},
        },
        {"type": "message_stop"},
    ]
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


@pytest.fixture
def claude(monkeypatch, http):
    state = {"body": b"", "requests": []}

    def handler(request):
        state["requests"].append(json.loads(request.content) if request.content else None)
        if request.url.path.startswith("/v1/models"):
            return httpx2.Response(
                200,
                json={
                    "type": "model",
                    "id": "claude-haiku-5-5",
                    "display_name": "x",
                    "created_at": "2026-01-01T00:00:00Z",
                    "max_tokens": 64000,
                },
            )
        return httpx2.Response(
            200, content=state["body"], headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        anthropic_module,
        "make_client",
        lambda key, url: anthropic.AsyncAnthropic(
            api_key="k",
            base_url=url,
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
        ),
    )
    return state, AnthropicProvider(
        id="anthropic", name="A", base_url="https://api.anthropic.com", client=http, api_key="k"
    )


async def test_anthropic_tool_use(claude) -> None:
    state, provider = claude
    state["body"] = anthropic_stream(
        [
            {"type": "text", "text": "Computing."},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "calculator",
                "json": '{"expression": "6*7"}',
            },
        ],
        "tool_use",
    )
    out = [
        c
        async for c in provider.stream_chat(
            "claude-haiku-5-5", TOOL_TURNS[:1], ChatParams(), [CALC]
        )
    ]
    assert out[0].delta == "Computing."
    done = out[-1]
    assert done.tool_calls == [
        ToolCall(id="toolu_1", name="calculator", arguments={"expression": "6*7"})
    ]
    assert [b["type"] for b in done.provider_state] == ["text", "tool_use"]
    tool_def = state["requests"][-1]["tools"][0]
    assert tool_def["eager_input_streaming"] is True and tool_def["input_schema"]["required"] == [
        "expression"
    ]


async def test_anthropic_truncated_tool_input_is_never_run(claude) -> None:
    state, provider = claude
    state["body"] = anthropic_stream(
        [{"type": "tool_use", "id": "t", "name": "calculator", "json": '{"expression": "6*7"}'}],
        "max_tokens",
    )
    with pytest.raises(ProviderError, match="cut off"):
        [
            c
            async for c in provider.stream_chat(
                "claude-haiku-5-5", TOOL_TURNS[:1], ChatParams(), [CALC]
            )
        ]


# --- agent loop -------------------------------------------------------------------


class ScriptedProvider(OllamaProvider):
    """Plays back one scripted reply per round and records what it was sent."""

    id = "ollama"

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.seen: list[tuple[list[ChatMessage], list[ToolSpec] | None]] = []

    async def stream_chat(self, model, messages, params, tools=None):
        self.seen.append((list(messages), tools))
        for chunk in self.rounds.pop(0):
            yield chunk


def events(out: list[str]) -> list[dict]:
    return [json.loads(e[6:]) for e in out]


@pytest.fixture
def conv(client) -> str:
    return client.post("/api/conversations", json={}).json()["id"]


async def test_agent_loop_runs_tool_and_continues(app, client, conv, http) -> None:
    provider = ScriptedProvider(
        [
            [
                StreamChunk(delta="Let me check."),
                StreamChunk(
                    done=True,
                    tool_calls=[
                        ToolCall(id="c1", name="calculator", arguments={"expression": "23*47"})
                    ],
                ),
            ],
            [StreamChunk(delta="It's 1081."), StreamChunk(done=True, usage={"total_tokens": 9})],
        ]
    )
    history = [ChatMessage(role="user", content="23*47?")]
    out = events(
        [
            e
            async for e in stream_and_persist(
                app.state.engine,
                provider,
                conv,
                "ollama:m",
                "m",
                history,
                ChatParams(),
                None,
                [TOOLS["calculator"]],
                ToolContext(http),
            )
        ]
    )

    assert out == [
        {"delta": "Let me check."},
        {"tool_call": {"id": "c1", "name": "calculator", "arguments": {"expression": "23*47"}}},
        {"tool_result": {"id": "c1", "output": "1081", "error": False}},
        {"delta": "\n\n"},
        {"delta": "It's 1081."},
        {"done": True, "usage": {"total_tokens": 9}, "message_id": out[-1]["message_id"]},
    ]
    second_round = provider.seen[1][0]
    assert [(m.role, m.content) for m in second_round[1:]] == [
        ("assistant", "Let me check."),
        ("tool", "1081"),
    ]
    saved = client.get(f"/api/conversations/{conv}").json()["messages"][-1]
    assert saved["content"] == "Let me check.\n\nIt's 1081."
    assert saved["tools"] == [
        {
            "id": "c1",
            "name": "calculator",
            "arguments": {"expression": "23*47"},
            "output": "1081",
            "error": False,
        }
    ]


async def test_model_cannot_call_tools_that_are_not_enabled(app, client, conv, http) -> None:
    provider = ScriptedProvider(
        [
            [
                StreamChunk(
                    done=True,
                    tool_calls=[
                        ToolCall(id="x", name="fetch_url", arguments={"url": "http://evil.test"})
                    ],
                )
            ],
            [StreamChunk(delta="ok"), StreamChunk(done=True)],
        ]
    )
    out = events(
        [
            e
            async for e in stream_and_persist(
                app.state.engine,
                provider,
                conv,
                "ollama:m",
                "m",
                [],
                ChatParams(),
                None,
                [TOOLS["calculator"]],
                ToolContext(http),
            )
        ]
    )
    result = next(e["tool_result"] for e in out if "tool_result" in e)
    assert result["error"] and "isn't enabled" in result["output"]


async def test_tool_rounds_are_capped(app, client, conv, http) -> None:
    from app.routers.chat import MAX_TOOL_ROUNDS

    looping = [
        StreamChunk(
            done=True,
            tool_calls=[ToolCall(id="c", name="calculator", arguments={"expression": "1+1"})],
        )
    ]
    provider = ScriptedProvider(
        [looping] * MAX_TOOL_ROUNDS + [[StreamChunk(delta="Done."), StreamChunk(done=True)]]
    )
    out = events(
        [
            e
            async for e in stream_and_persist(
                app.state.engine,
                provider,
                conv,
                "ollama:m",
                "m",
                [],
                ChatParams(),
                None,
                [TOOLS["calculator"]],
                ToolContext(http),
            )
        ]
    )
    assert sum("tool_call" in e for e in out) == MAX_TOOL_ROUNDS
    assert provider.seen[-1][1] is None  # last round: no tools offered, so it must answer
    assert out[-1]["done"] is True


async def test_tools_only_reply_is_still_saved(app, client, conv, http) -> None:
    provider = ScriptedProvider(
        [
            [
                StreamChunk(
                    done=True,
                    tool_calls=[
                        ToolCall(id="c", name="calculator", arguments={"expression": "2+2"})
                    ],
                )
            ],
            [StreamChunk(done=True)],
        ]
    )
    [
        e
        async for e in stream_and_persist(
            app.state.engine,
            provider,
            conv,
            "ollama:m",
            "m",
            [],
            ChatParams(),
            None,
            [TOOLS["calculator"]],
            ToolContext(http),
        )
    ]
    saved = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert saved[-1]["content"] == "" and saved[-1]["tools"][0]["output"] == "4"


async def test_empty_reply_is_reported(app, client, conv) -> None:
    # e.g. a small model writes a tool call the server can't parse: nothing comes back.
    provider = ScriptedProvider([[StreamChunk(done=True)]])
    events = [
        e
        async for e in stream_and_persist(
            app.state.engine, provider, conv, "ollama:m", "m", [], ChatParams()
        )
    ]
    assert events == ['data: {"error": "The model returned an empty reply. Try again."}\n\n']
    assert client.get(f"/api/conversations/{conv}").json()["messages"] == []


# --- endpoint ---------------------------------------------------------------------


OLLAMA = "http://ollama.test"


def ollama_lines(*objs) -> bytes:
    return b"".join(json.dumps(o).encode() + b"\n" for o in objs)


@respx.mock
def test_chat_endpoint_offers_selected_tools(client, session, conv) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()
    route = respx.post(f"{OLLAMA}/api/chat")
    route.side_effect = [
        httpx.Response(
            200,
            content=ollama_lines(
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "calculator",
                                    "arguments": {"expression": "23*47"},
                                }
                            }
                        ],
                    },
                    "done": False,
                },
                {"message": {"content": ""}, "done": True},
            ),
        ),
        httpx.Response(
            200,
            content=ollama_lines(
                {"message": {"content": "1081"}, "done": False},
                {"message": {"content": ""}, "done": True},
            ),
        ),
    ]
    resp = client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:m",
            "message": "23*47?",
            "tools": ["calculator", "fetch_url"],
        },
    )
    assert [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")][
        1
    ]["tool_result"]["output"] == "1081"
    first, second = (json.loads(c.request.content) for c in route.calls)
    assert sorted(t["function"]["name"] for t in first["tools"]) == ["calculator", "fetch_url"]
    assert second["messages"][-1] == {"role": "tool", "content": "1081", "tool_name": "calculator"}


@respx.mock
def test_admin_can_disable_tools(client, user_client, session) -> None:
    # web_search is enabled but hidden: no search engine is set up.
    assert [t["id"] for t in user_client.get("/api/tools").json()] == [
        "calculator",
        "current_time",
        "fetch_url",
        "add_memory",
    ]
    client.put(
        "/api/admin/settings",
        json={"enable_signup": True, "default_user_role": "user", "enabled_tools": ["calculator"]},
    )
    assert [t["id"] for t in user_client.get("/api/tools").json()] == ["calculator"]
    # Admins can still see every tool to switch them back on; users can't.
    assert len(client.get("/api/tools?all=true").json()) == 5
    assert len(user_client.get("/api/tools?all=true").json()) == 1
    # Updating other settings keeps the tool list.
    client.put("/api/admin/settings", json={"enable_signup": False, "default_user_role": "user"})
    assert client.get("/api/admin/settings").json()["enabled_tools"] == ["calculator"]
    bad = client.put(
        "/api/admin/settings",
        json={"enable_signup": True, "default_user_role": "user", "enabled_tools": ["rm_rf"]},
    )
    assert bad.status_code == 422

    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()
    route = respx.post(f"{OLLAMA}/api/chat").respond(
        content=ollama_lines({"message": {"content": "hi"}, "done": True})
    )
    conv = user_client.post("/api/conversations", json={}).json()["id"]
    user_client.post(
        "/api/chat/stream",
        json={
            "conversation_id": conv,
            "model_id": "ollama:m",
            "message": "hi",
            "tools": ["fetch_url", "calculator"],
        },
    )
    assert [
        t["function"]["name"] for t in json.loads(route.calls.last.request.content)["tools"]
    ] == ["calculator"]


@respx.mock
def test_custom_model_default_tools(client, session, conv) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()
    respx.get(f"{OLLAMA}/api/tags").respond(json={"models": [{"name": "m"}]})
    made = client.post(
        "/api/custom-models",
        json={"name": "Math tutor", "base_model_id": "ollama:m", "tool_ids": ["calculator"]},
    )
    assert made.status_code == 201 and made.json()["tool_ids"] == ["calculator"]
    assert (
        client.post(
            "/api/custom-models",
            json={"name": "x", "base_model_id": "ollama:m", "tool_ids": ["nope"]},
        ).status_code
        == 422
    )
    route = respx.post(f"{OLLAMA}/api/chat").respond(
        content=ollama_lines({"message": {"content": "hi"}, "done": True})
    )
    client.post(
        "/api/chat/stream",
        json={"conversation_id": conv, "model_id": "persona:math-tutor", "message": "hi"},
    )
    assert [
        t["function"]["name"] for t in json.loads(route.calls.last.request.content)["tools"]
    ] == ["calculator"]


@respx.mock
def test_no_tools_field_when_none_selected(client, session, conv) -> None:
    session.add(Provider(id="ollama", name="Ollama", kind="ollama", base_url=OLLAMA))
    session.commit()
    route = respx.post(f"{OLLAMA}/api/chat").respond(
        content=ollama_lines({"message": {"content": "hi"}, "done": True})
    )
    client.post(
        "/api/chat/stream", json={"conversation_id": conv, "model_id": "ollama:m", "message": "hi"}
    )
    assert "tools" not in json.loads(route.calls.last.request.content)
