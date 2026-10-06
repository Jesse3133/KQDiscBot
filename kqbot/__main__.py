"""Entry point: ``python -m kqbot``."""

import logging
import signal

import discord

from kqbot.bot import KQBot
from kqbot.config import load_config
from kqbot.instance_lock import AlreadyRunning, InstanceLock


def _stop(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    config = load_config()
    discord.utils.setup_logging(level=logging.INFO)
    # Hosts and Docker stop the bot with SIGTERM. Treat it like Ctrl+C so the
    # bot logs out and closes the database cleanly.
    signal.signal(signal.SIGTERM, _stop)
    try:
        with InstanceLock(f"{config.database_path}.lock"):
            KQBot(config).run(config.token, log_handler=None)
    except AlreadyRunning:
        raise SystemExit(
            "Another copy of the bot is already running with this database. "
            "Stop it first: two copies would post every reminder twice."
        ) from None


if __name__ == "__main__":
    main()
