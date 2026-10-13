"""Admin analytics: usage over time and a model leaderboard from user ratings."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from itertools import combinations

from sqlmodel import Session, col, func, select

from app.models import Conversation, Message, User, utcnow

ELO_START = 1000.0
ELO_K = 32.0


# --- leaderboard ------------------------------------------------------------------


def _turns(messages: list[Message]) -> list[list[Message]]:
    """Replies grouped by the message they answer (messages ordered by conversation, id)."""
    turns: list[list[Message]] = []
    current: list[Message] = []
    conversation = None
    for m in messages:
        if m.role != "assistant" or m.conversation_id != conversation:
            if current:
                turns.append(current)
            current = []
            conversation = m.conversation_id
        if m.role == "assistant":
            current.append(m)
    if current:
        turns.append(current)
    return turns


def leaderboard(session: Session) -> list[dict]:
    """Every rated model, best first.

    👍/👎 count for any reply. Replies shown side by side (multi-model chats and
    the arena) are also matches: the better-rated reply wins (unrated counts as
    neutral; equal ratings are a tie). Elo ratings are updated match by match,
    oldest first.
    """
    rated = select(Message.conversation_id).where(col(Message.rating).is_not(None)).distinct()
    messages = list(
        session.exec(
            select(Message)
            .where(col(Message.conversation_id).in_(rated))
            .order_by(col(Message.conversation_id), col(Message.id))
        )
    )
    stats: dict[str, dict] = defaultdict(
        lambda: {"elo": ELO_START, "wins": 0, "losses": 0, "ties": 0, "likes": 0, "dislikes": 0}
    )
    for m in messages:
        if m.role == "assistant" and m.model_id and m.rating is not None:
            stats[m.model_id]["likes" if m.rating > 0 else "dislikes"] += 1

    turns = sorted(_turns(messages), key=lambda t: (t[0].created_at, t[0].id or 0))
    for turn in turns:
        for a, b in combinations(turn, 2):
            if not a.model_id or not b.model_id or a.model_id == b.model_id:
                continue
            if a.rating is None and b.rating is None:
                continue
            ra, rb = a.rating or 0, b.rating or 0
            score = 1.0 if ra > rb else 0.0 if ra < rb else 0.5
            sa, sb = stats[a.model_id], stats[b.model_id]
            expected = 1 / (1 + 10 ** ((sb["elo"] - sa["elo"]) / 400))
            sa["elo"] += ELO_K * (score - expected)
            sb["elo"] -= ELO_K * (score - expected)
            if score == 0.5:
                sa["ties"] += 1
                sb["ties"] += 1
            else:
                (sa if score == 1 else sb)["wins"] += 1
                (sb if score == 1 else sa)["losses"] += 1

    board = [
        {
            "model_id": model_id,
            **s,
            "elo": round(s["elo"]),
            "matches": s["wins"] + s["losses"] + s["ties"],
        }
        for model_id, s in stats.items()
    ]
    return sorted(board, key=lambda r: (-r["elo"], -(r["likes"] - r["dislikes"]), r["model_id"]))


# --- usage ------------------------------------------------------------------------


def usage_report(session: Session, days: int = 30) -> dict:
    """Totals, per-day activity and per-model use over the last `days` days (UTC)."""
    today = utcnow().date()
    first = today - timedelta(days=days - 1)
    since = datetime.combine(first, time.min, tzinfo=UTC)

    rows = session.exec(
        select(
            Message.created_at,
            Message.role,
            Message.model_id,
            Message.prompt_tokens,
            Message.completion_tokens,
            Message.rating,
            Conversation.owner_id,
        )
        .join(Conversation, col(Conversation.id) == col(Message.conversation_id))
        .where(Message.created_at >= since, col(Message.role).in_(["user", "assistant"]))
    ).all()

    daily: dict[date, dict] = {
        first + timedelta(days=i): {"messages": 0, "replies": 0, "tokens": 0, "users": set()}
        for i in range(days)
    }
    models: dict[str, dict] = defaultdict(
        lambda: {
            "replies": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "likes": 0,
            "dislikes": 0,
        }
    )
    users: set[str] = set()
    for created, role, model_id, prompt, completion, rating, owner in rows:
        day = daily.get(created.date())
        if day is None:
            continue
        if role == "user":
            day["messages"] += 1
            day["users"].add(owner)
            users.add(owner)
            continue
        tokens = (prompt or 0) + (completion or 0)
        day["replies"] += 1
        day["tokens"] += tokens
        m = models[model_id or "unknown"]
        m["replies"] += 1
        m["prompt_tokens"] += prompt or 0
        m["completion_tokens"] += completion or 0
        if rating is not None:
            m["likes" if rating > 0 else "dislikes"] += 1

    def count(stmt) -> int:
        return session.exec(stmt).one()

    return {
        "days": days,
        "totals": {
            "users": count(
                select(func.count()).select_from(User).where(col(User.is_guest).is_(False))
            ),
            "guests": count(
                select(func.count()).select_from(User).where(col(User.is_guest).is_(True))
            ),
            "conversations": count(select(func.count()).select_from(Conversation)),
            "messages": count(
                select(func.count()).select_from(Message).where(Message.role == "user")
            ),
            "active_users": len(users),
            "period_messages": sum(d["messages"] for d in daily.values()),
            "period_tokens": sum(d["tokens"] for d in daily.values()),
        },
        "daily": [
            {
                "date": day.isoformat(),
                "messages": d["messages"],
                "replies": d["replies"],
                "tokens": d["tokens"],
                "active_users": len(d["users"]),
            }
            for day, d in daily.items()
        ],
        "models": sorted(
            ({"model_id": k, **v} for k, v in models.items()),
            key=lambda r: (-r["replies"], r["model_id"]),
        ),
    }
