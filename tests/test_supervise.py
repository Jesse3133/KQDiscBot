import subprocess
import sys
import time

import pytest

from kqbot.instance_lock import AlreadyRunning, InstanceLock
from kqbot.supervise import BotProcess, Supervisor, Updater, git

# Instance lock -----------------------------------------------------------------


def test_lock_blocks_second_copy(tmp_path):
    path = tmp_path / "bot.lock"
    with InstanceLock(path):
        with pytest.raises(AlreadyRunning):
            InstanceLock(path).acquire()
    with InstanceLock(path):  # free again after release
        pass


def test_lock_released_when_process_dies(tmp_path):
    path = tmp_path / "bot.lock"
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time; from kqbot.instance_lock import InstanceLock; "
            f"lock = InstanceLock({str(path)!r}); lock.acquire(); "
            "print('locked', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout.readline().strip() == "locked"
    with pytest.raises(AlreadyRunning):
        InstanceLock(path).acquire()
    holder.kill()
    holder.wait()
    with InstanceLock(path):
        pass


# Updater (real git repos) ---------------------------------------------------------


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """A GitHub stand-in (bare repo), a dev clone that pushes, and the host clone."""
    for var, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(var, value)
    origin, dev, host = tmp_path / "origin.git", tmp_path / "dev", tmp_path / "host"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(dev)], check=True)

    def commit(name, content, repo=dev):
        (repo / name).write_text(content)
        subprocess.run(["git", "add", name], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"change {name}"], cwd=repo, check=True)

    def push():
        subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=dev, check=True)

    commit("requirements.txt", "discord.py\n")
    push()
    subprocess.run(["git", "clone", "-q", str(origin), str(host)], check=True)
    return dev, host, commit, push


def head(repo):
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_no_update_when_up_to_date(repos):
    _, host, _, _ = repos
    assert not Updater(host, "main").update_available()


def test_pulls_new_commits(repos):
    dev, host, commit, push = repos
    commit("bot.py", "v2")
    push()
    updater = Updater(host, "main")
    installed = []
    updater.install_requirements = installed.append
    assert updater.update_available()
    assert updater.apply()
    assert head(host) == head(dev)
    assert (host / "bot.py").read_text() == "v2"
    assert installed == []  # requirements didn't change
    assert not updater.update_available()


def test_reinstalls_when_requirements_change(repos):
    _, host, commit, push = repos
    commit("requirements.txt", "discord.py\nnewthing\n")
    push()
    updater = Updater(host, "main")
    installed = []
    updater.install_requirements = installed.append
    assert updater.update_available() and updater.apply()
    assert installed == [host / "requirements.txt"]


def test_wrong_branch_does_not_update(repos):
    _, host, commit, push = repos
    commit("bot.py", "v2")
    push()
    subprocess.run(["git", "checkout", "-q", "-b", "experiment"], cwd=host, check=True)
    assert not Updater(host, "main").update_available()


def test_local_commits_block_update(repos):
    _, host, commit, push = repos
    commit("bot.py", "v2")
    push()
    commit("local.txt", "mine", repo=host)
    assert not Updater(host, "main").update_available()


def test_hand_edited_file_blocks_update_safely(repos):
    _, host, commit, push = repos
    commit("bot.py", "v2")
    push()
    (host / "bot.py").write_text("edited by hand")  # untracked file in the way
    before = head(host)
    updater = Updater(host, "main")
    assert updater.update_available()
    assert not updater.apply()
    assert head(host) == before
    assert (host / "bot.py").read_text() == "edited by hand"


def test_not_a_git_checkout(tmp_path):
    assert not Updater(tmp_path, "main").update_available()


# Bot process ------------------------------------------------------------------------

WAIT_FOR_STDIN = [
    sys.executable,
    "-c",
    "import os, sys; print('env', os.environ.get('KQBOT_SUPERVISED'), flush=True); "
    "sys.stdin.read(); print('stopped cleanly', flush=True)",
]


def test_stop_closes_stdin_for_clean_shutdown(tmp_path):
    bot = BotProcess(WAIT_FOR_STDIN, tmp_path, tmp_path / "logs" / "kqbot.log")
    bot.start()
    time.sleep(0.5)
    assert bot.exit_code() is None
    bot.stop(timeout=10)
    assert bot.exit_code() == 0
    output = (tmp_path / "logs" / "kqbot.log").read_text()
    assert "env 1" in output and "stopped cleanly" in output


def test_stuck_bot_is_terminated(tmp_path):
    ignore_stdin = [sys.executable, "-c", "import time; time.sleep(60)"]
    bot = BotProcess(ignore_stdin, tmp_path, tmp_path / "kqbot.log")
    bot.start()
    bot.stop(timeout=1)
    assert bot.exit_code() is not None


def test_big_log_is_rotated(tmp_path):
    log_path = tmp_path / "kqbot.log"
    log_path.write_bytes(b"x" * (6 * 1024 * 1024))
    bot = BotProcess([sys.executable, "-c", "pass"], tmp_path, log_path)
    bot.start()
    bot.proc.wait(10)
    assert (tmp_path / "kqbot.log.1").stat().st_size > 5 * 1024 * 1024
    assert log_path.stat().st_size < 1024


# Supervisor ---------------------------------------------------------------------------


class FakeBot:
    def __init__(self, code=None, uptime=1000.0):
        self.code, self._uptime = code, uptime
        self.starts = self.stops = 0
        self.log_path = "kqbot.log"

    def exit_code(self):
        return self.code

    def uptime(self):
        return self._uptime

    def start(self):
        self.starts += 1
        self.code = None

    def stop(self):
        self.stops += 1


class FakeUpdater:
    def __init__(self, available):
        self.available = available
        self.applied = 0

    def update_available(self):
        return self.available

    def apply(self):
        self.applied += 1
        return True


def supervisor(bot, updater=None):
    sup = Supervisor(bot, updater, update_seconds=300)
    sup._sleep = lambda seconds: None
    return sup


def test_crashed_bot_is_restarted():
    bot = FakeBot(code=1)
    supervisor(bot).step(now=0, next_update=1000)
    assert bot.starts == 1


def test_repeated_quick_crashes_back_off():
    bot = FakeBot(code=1, uptime=2)
    sup = supervisor(bot)
    delays = []
    for _ in range(8):
        bot.code = 1
        sup.step(now=0, next_update=1000)
        delays.append(sup.restart_delay)
    assert delays == sorted(delays) and delays[-1] == 300


def test_healthy_run_resets_backoff():
    bot = FakeBot(code=1, uptime=2)
    sup = supervisor(bot)
    sup.step(0, 1000)
    assert sup.restart_delay == 10
    bot.code, bot._uptime = 1, 3600  # crashed after running a long time
    sup.step(0, 1000)
    assert sup.restart_delay == 5


def test_update_restarts_bot():
    bot, updater = FakeBot(), FakeUpdater(available=True)
    next_update = supervisor(bot, updater).step(now=500, next_update=400)
    assert updater.applied == 1 and bot.stops == 1 and bot.starts == 1
    assert next_update == 800


def test_no_update_leaves_bot_alone():
    bot, updater = FakeBot(), FakeUpdater(available=False)
    supervisor(bot, updater).step(now=500, next_update=400)
    assert updater.applied == 0 and bot.stops == 0 and bot.starts == 0


def test_update_check_waits_for_its_time():
    bot, updater = FakeBot(), FakeUpdater(available=True)
    assert supervisor(bot, updater).step(now=100, next_update=400) == 400
    assert updater.applied == 0
