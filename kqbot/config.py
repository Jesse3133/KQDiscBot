import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    token: str
    game_tz: ZoneInfo
    dev_guild_id: int | None
    database_path: str


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")

    tz_name = os.getenv("GAME_TIMEZONE", "").strip() or "America/Los_Angeles"
    try:
        game_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        raise SystemExit(f"GAME_TIMEZONE {tz_name!r} is not a known time zone.") from None

    guild = os.getenv("DEV_GUILD_ID", "").strip()
    if guild and not guild.isdigit():
        raise SystemExit("DEV_GUILD_ID must be a numeric server ID.")

    return Config(
        token=token,
        game_tz=game_tz,
        dev_guild_id=int(guild) if guild else None,
        database_path=os.getenv("DATABASE_PATH", "").strip() or "kqbot.sqlite3",
    )
