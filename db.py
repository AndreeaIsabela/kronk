import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_db: AsyncIOMotorDatabase | None = None


def init_db() -> None:
    global _db
    uri = os.getenv("MONGO_URI", "")
    # Atlas URIs use the srv scheme and require TLS; local URIs do not.
    kwargs = {"tlsCAFile": certifi.where()} if uri.startswith("mongodb+srv://") else {}
    client = AsyncIOMotorClient(uri, **kwargs)
    _db = client[os.getenv("MONGO_DB_NAME", "kronk")]


def get_db() -> AsyncIOMotorDatabase:
    return _db


# --- timers ---

async def load_timers(guild_id: str) -> dict:
    """Returns {user_id: {username, end_ts, channel_id}}"""
    result = {}
    async for doc in get_db().timers.find({"guild_id": guild_id}):
        result[doc["user_id"]] = {
            "username": doc["username"],
            "end_ts": doc["end_ts"],
            "channel_id": doc["channel_id"],
        }
    return result


async def upsert_timer(guild_id: str, user_id: str, username: str, end_ts: float, channel_id: int) -> None:
    await get_db().timers.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": {"username": username, "end_ts": end_ts, "channel_id": channel_id}},
        upsert=True,
    )


async def delete_timer(guild_id: str, user_id: str) -> None:
    await get_db().timers.delete_one({"guild_id": guild_id, "user_id": user_id})


# --- rally leaders ---

async def load_rally_leaders(guild_id: str) -> list[dict]:
    doc = await get_db().rally_leaders.find_one({"guild_id": guild_id})
    return doc.get("leaders", []) if doc else []


async def save_rally_leaders(guild_id: str, leaders: list[dict]) -> None:
    await get_db().rally_leaders.update_one(
        {"guild_id": guild_id},
        {"$set": {"leaders": leaders}},
        upsert=True,
    )


# --- events ---

async def upsert_event(guild_id: str, event_name: str, data: dict) -> None:
    """Insert or fully replace an event document."""
    await get_db().events.replace_one(
        {"guild_id": guild_id, "event_name": event_name},
        {"guild_id": guild_id, "event_name": event_name, **data},
        upsert=True,
    )


async def load_events(guild_id: str) -> list[dict]:
    """Return all events for a guild (without MongoDB _id field)."""
    result = []
    async for doc in get_db().events.find({"guild_id": guild_id}, {"_id": 0}):
        result.append(doc)
    return result


async def get_event(guild_id: str, event_name: str) -> dict | None:
    return await get_db().events.find_one(
        {"guild_id": guild_id, "event_name": event_name},
        {"_id": 0},
    )


async def delete_event(guild_id: str, event_name: str) -> bool:
    """Returns True if an event was found and deleted."""
    result = await get_db().events.delete_one({"guild_id": guild_id, "event_name": event_name})
    return result.deleted_count > 0
