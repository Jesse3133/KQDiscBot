"""Keeps the bot running on a home PC or Raspberry Pi and updates it from GitHub.

    python -m kqbot.supervise                 # with a console window
    .venv\\Scripts\\pythonw.exe -m kqbot.supervise   # Windows, no window

What it does:
* starts the bot and restarts it if it crashes (waiting longer each time it
  crashes quickly, so a broken setup doesn't spin);
* every few minutes, checks GitHub for new commits on the branch (``main``)
  and, if there are any, pulls them, reinstalls requirements if they
  changed, and restarts the bot;
* writes logs to ``logs/`` (bot output in kqbot.log, its own in supervisor.log).

Standard library only, so it keeps working even if an update breaks the
bot's dependencies.
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from kqbot.instance_lock import AlreadyRunning, InstanceLock

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
BOT_LOG = LOG_DIR / "kqbot.log"
BOT_LOG_MAX_BYTES = 5 * 1024 * 1024
POLL_SECONDS = 5
# A bot that ran at least this long counts as healthy; restart quickly.
HEALTHY_RUN_SECONDS = 60
MAX_RESTART_DELAY = 300

log = logging.getLogger("kqbot.supervise")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, timeout=120, check=False
    )


class Updater:
    """Fast-forwards the checkout to ``origin/<branch>`` when GitHub has new commits."""

    def __init__(self, root: Path, branch: str) -> None:
        self.root = root
        self.branch = branch
        self._warned: set[str] = set()

    def _warn_once(self, key: str, message: str, *args) -> None:
        if key not in self._warned:
            self._warned.add(key)
            log.warning(message, *args)

    def update_available(self) -> bool:
        current = git(self.root, "rev-parse", "--abbrev-ref", "HEAD")
        if current.returncode != 0:
            self._warn_once("git", "Not a git checkout, so automatic updates are off")
            return False
        if current.stdout.strip() != self.branch:
            self._warn_once(
                "branch",
                "On branch %s, not %s, so automatic updates are off. Run: git checkout %s",
                current.stdout.strip(),
                self.branch,
                self.branch,
            )
            return False
        fetch = git(self.root, "fetch", "--quiet", "origin", self.branch)
        if fetch.returncode != 0:
            log.warning("Couldn't check GitHub for updates: %s", fetch.stderr.strip())
            return False
        remote = f"origin/{self.branch}"
        if git(self.root, "rev-parse", "HEAD").stdout == git(self.root, "rev-parse", remote).stdout:
            return False
        if git(self.root, "merge-base", "--is-ancestor", "HEAD", remote).returncode != 0:
            self._warn_once(
                "diverged",
                "This copy has commits that aren't on GitHub, so it won't update itself",
            )
            return False
        return True

    def apply(self) -> bool:
        """Pull the new commits. Returns True if the bot should be restarted."""
        requirements = self.root / "requirements.txt"
        before = requirements.read_bytes() if requirements.exists() else b""
        merge = git(self.root, "merge", "--ff-only", f"origin/{self.branch}")
        if merge.returncode != 0:
            log.warning(
                "Update failed (files changed by hand?), staying on the current version: %s",
                (merge.stderr or merge.stdout).strip(),
            )
            return False
        commit = git(self.root, "log", "-1", "--format=%h %s").stdout.strip()
        log.info("Updated to %s", commit)
        if requirements.exists() and requirements.read_bytes() != before:
            log.info("Requirements changed; installing")
            self.install_requirements(requirements)
        return True

    def install_requirements(self, requirements: Path) -> None:
        pip = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(requirements)],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        if pip.returncode != 0:
            log.error("pip install failed: %s", pip.stderr.strip())


class BotProcess:
    def __init__(self, command: list[str], root: Path, log_path: Path) -> None:
        self.command = command
        self.root = root
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None
        self.started_at = 0.0

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists() and self.log_path.stat().st_size > BOT_LOG_MAX_BYTES:
            self.log_path.replace(self.log_path.with_suffix(".log.1"))
        with open(self.log_path, "ab") as output:
            self.proc = subprocess.Popen(
                self.command,
                cwd=self.root,
                # The bot stops itself when this pipe closes (see KQBot).
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.STDOUT,
                env={**os.environ, "KQBOT_SUPERVISED": "1"},
            )
        self.started_at = time.monotonic()
        log.info("Bot started (pid %s)", self.proc.pid)

    def exit_code(self) -> int | None:
        return self.proc.poll() if self.proc else None

    def uptime(self) -> float:
        return time.monotonic() - self.started_at

    def stop(self, timeout: float = 30) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        log.info("Stopping bot")
        try:
            self.proc.stdin.close()  # asks the bot to shut down cleanly
        except OSError:
            pass
        try:
            self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            log.warning("Bot didn't stop in %ss; terminating it", timeout)
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class Supervisor:
    def __init__(self, bot: BotProcess, updater: Updater | None, update_seconds: float) -> None:
        self.bot = bot
        self.updater = updater
        self.update_seconds = update_seconds
        self.stopping = False
        self.restart_delay = 5.0

    def request_stop(self, *_args) -> None:
        self.stopping = True

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self.stopping and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))

    def step(self, now: float, next_update: float) -> float:
        """One round of checks. Returns when the next update check is due."""
        code = self.bot.exit_code()
        if code is not None:
            if self.bot.uptime() >= HEALTHY_RUN_SECONDS:
                self.restart_delay = 5.0
            else:
                self.restart_delay = min(self.restart_delay * 2, MAX_RESTART_DELAY)
            log.warning(
                "Bot exited with code %s; restarting in %.0fs (see %s)",
                code,
                self.restart_delay,
                self.bot.log_path,
            )
            self._sleep(self.restart_delay)
            if not self.stopping:
                self.bot.start()
            return next_update
        if self.updater and now >= next_update:
            if self.updater.update_available() and self.updater.apply():
                self.bot.stop()
                self.bot.start()
            return now + self.update_seconds
        return next_update

    def run(self) -> None:
        self.bot.start()
        next_update = time.monotonic() + self.update_seconds
        while not self.stopping:
            self._sleep(POLL_SECONDS)
            if not self.stopping:
                next_update = self.step(time.monotonic(), next_update)
        self.bot.stop()
        log.info("Supervisor stopped")


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(LOG_DIR / "supervisor.log", maxBytes=1_000_000, backupCount=3)
    ]
    if sys.stderr is not None:  # None under pythonw (no console)
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", default="main", help="branch to follow (default: main)")
    parser.add_argument(
        "--update-minutes", type=float, default=5, help="how often to check GitHub (default: 5)"
    )
    parser.add_argument("--no-update", action="store_true", help="never update automatically")
    args = parser.parse_args()
    setup_logging()

    try:
        lock = InstanceLock(LOG_DIR / "supervisor.lock")
        lock.acquire()
    except AlreadyRunning:
        log.error("The supervisor is already running; not starting a second one")
        raise SystemExit(1) from None

    updater = None if args.no_update else Updater(ROOT, args.branch)
    supervisor = Supervisor(
        BotProcess([sys.executable, "-m", "kqbot"], ROOT, BOT_LOG),
        updater,
        args.update_minutes * 60,
    )
    signal.signal(signal.SIGINT, supervisor.request_stop)
    signal.signal(signal.SIGTERM, supervisor.request_stop)
    log.info(
        "Supervisor started in %s; %s",
        ROOT,
        "updates off" if updater is None else f"following origin/{args.branch}",
    )
    try:
        supervisor.run()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
