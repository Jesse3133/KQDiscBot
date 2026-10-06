# Hosting the bot at home

Reminders only go out while the bot is running. This guide sets it up on a
Windows PC or a Raspberry Pi so that it:

- **starts by itself** when the PC logs in or the Pi boots,
- **restarts by itself** if it crashes,
- **updates by itself**: when new code lands on the `main` branch on GitHub,
  it's pulled in and the bot restarts within about 5 minutes.

A small **supervisor** (`python -m kqbot.supervise`) does all of this. It
runs the bot, watches it, and checks GitHub for updates.

## How updates reach the bot

1. Changes are made on a branch and opened as a pull request into `main`.
2. CI runs the tests on the pull request (✅/❌ on GitHub).
3. You merge the pull request.
4. Within 5 minutes the supervisor sees the new commit on `main`, pulls it,
   reinstalls packages if `requirements.txt` changed, and restarts the bot.

Only `main` is followed, so nothing goes live until you merge it.

## Before you start

- **Run only one copy.** Two copies would post every reminder twice. Stop any
  bot you started by hand (Ctrl+C in its window) before setting this up. If
  you forget, the second copy refuses to start ("Another copy of the bot is
  already running") as long as both use the same folder.
- **The computer has to stay on and awake.** A sleeping PC sends no
  reminders.
- **Your data stays where it is.** The supervisor runs the bot from the
  project folder, so it keeps using your existing `.env` and `kqbot.sqlite3`.
  Nothing to migrate.

## Windows PC

**One-time setup**, in PowerShell in the project folder:

```powershell
# 1. Stop the bot if it's running in a window (Ctrl+C there).

# 2. Switch to the main branch and get the latest code.
git fetch
git checkout main
git pull

# 3. Make sure the virtual environment has everything.
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 4. Install the background task. This also starts the bot.
powershell -ExecutionPolicy Bypass -File scripts\install-windows-task.ps1
```

The bot now runs in the background with no window. It starts whenever you log
in to Windows.

**Keep the PC awake:** Settings → System → Power → **Sleep: Never** (when
plugged in). The screen can still turn off. That's fine.

**Day to day:**

| To… | Run (PowerShell, project folder) |
|---|---|
| See the bot's log | `Get-Content logs\kqbot.log -Tail 30 -Wait` (Ctrl+C stops watching) |
| See restarts and updates | `Get-Content logs\supervisor.log -Tail 30` |
| Check it's running | `Get-ScheduledTask -TaskName "Fiesta KQ Bot"` (State: Running) |
| Stop it | `Stop-ScheduledTask -TaskName "Fiesta KQ Bot"` |
| Start it again | `Start-ScheduledTask -TaskName "Fiesta KQ Bot"` |
| Remove it completely | `powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows-task.ps1` |

You can also use the Task Scheduler app and find **Fiesta KQ Bot** in the
Task Scheduler Library.

**Good to know:**

- It runs while you're **logged in**. Locking the screen is fine. Signing out
  stops it until you log in again. To run it with nobody logged in: in Task
  Scheduler, open the task, choose *Run whether user is logged on or not* and
  enter your Windows password.
- To run the bot by hand again (e.g. while testing), stop the task first.

## Raspberry Pi (or any Linux)

Raspberry Pi OS already has Python 3.11 or newer. **One-time setup:**

```bash
sudo apt install -y git python3-venv
git clone -b main https://github.com/Jesse3133/KQDiscBot.git
cd KQDiscBot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env                      # paste your token, save with Ctrl+O, exit with Ctrl+X
./scripts/install-linux-service.sh
```

If the GitHub repo is **private**, `git clone` asks for a username and
password. Use your GitHub username and a personal access token (GitHub →
Settings → Developer settings → Fine-grained tokens, with read access to this
repo) as the password. Then save it so automatic updates work:
`git config credential.helper store` and run `git pull` once, entering the
token again.

**Bring your data from the PC (optional):** copy `kqbot.sqlite3` from the PC's
project folder into `KQDiscBot/` on the Pi *before* starting the service. Stop
the PC copy first. Without it, the bot finds its roles and channels by name
but posts a new role picker (delete the old one), and event changes, notes
and the reminder text go back to their defaults.

**Day to day:**

| To… | Run |
|---|---|
| See the bot's log | `tail -f logs/kqbot.log` |
| See restarts and updates | `tail logs/supervisor.log` |
| Check it's running | `systemctl status kqbot` |
| Stop / start / restart | `sudo systemctl stop kqbot` / `start` / `restart` |
| Remove it | `sudo systemctl disable --now kqbot && sudo rm /etc/systemd/system/kqbot.service` |

## Supervisor options

The installers run `python -m kqbot.supervise` with the defaults. Options, if
you ever run it by hand or edit the task/service:

| Option | Default | Meaning |
|---|---|---|
| `--branch` | `main` | Branch to follow for updates. |
| `--update-minutes` | `5` | How often to check GitHub. |
| `--no-update` | off | Never update automatically. |

Automatic updates switch themselves off (with a message in
`logs/supervisor.log`) if the folder isn't on the `main` branch, has commits
that aren't on GitHub, or has hand-edited files that conflict with an update.
The bot keeps running on its current version in all those cases.

If the supervisor itself changes in an update, restart it to pick that up:
stop and start the task, or `sudo systemctl restart kqbot`.

## Other ways to run it

- **Docker:** the repo includes a `Dockerfile` and `docker-compose.yml`
  (database kept in `./data`). `docker compose up -d --build` starts it,
  and `git pull && docker compose up -d --build` updates it. Updates aren't
  automatic this way.
- **Cloud hosts** (Railway, Fly.io, a VPS) can run the same Docker image. Set
  `DISCORD_TOKEN` in the host's secret settings and mount a persistent volume
  at `/data`.

## Checks on GitHub

Every push and pull request runs `.github/workflows/ci.yml`:

- tests and lint on Python 3.11 and 3.13 (Linux)
- the tests on Windows, plus a check that the PowerShell scripts are valid
- a Docker image build, plus a check that the image starts

Results show on the repo's **Actions** tab and as ✅/❌ on each commit and pull
request.
