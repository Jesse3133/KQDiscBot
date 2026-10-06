# Hosting the bot

Reminders only go out while the bot is running. Hosting moves it from your
PC to a machine that's always on.

## Before you move it

**Run only one copy at a time.** Two copies of the bot would post every
reminder twice. Stop the one on your PC (Ctrl+C) before starting the hosted
one, and don't start the PC copy again while the hosted one is running.

**Bring your data, or start fresh.** Everything you set up in Discord (event
notes, levels, the reminder text, the time zone, shifts) is stored in
`kqbot.sqlite3` in your project folder.

- *Copy it* to the host so everything carries over. How depends on the host,
  see its section below.
- *Or start fresh.* The bot finds its existing roles and channels by name,
  so nobody loses a role. But it posts a new role picker (delete the old
  one), and event changes, notes and the reminder text go back to their
  defaults.

**The token goes in the host's settings, never in git.** Each host has a
place for "environment variables" or "secrets". Set `DISCORD_TOKEN` there.
You can also set `GAME_TIMEZONE`. Leave `DEV_GUILD_ID` unset in production.

**The database needs persistent storage.** On a host, the bot's files are
replaced on every update. The Docker image keeps the database in `/data`, so
that folder must be a persistent volume. If it isn't, everything resets on
each deploy.

## Running with Docker (your own server, VPS or PC)

The repo includes a `Dockerfile` and `docker-compose.yml`. On any machine with
Docker installed:

```bash
git clone -b <branch> https://github.com/Jesse3133/KQDiscBot.git
cd KQDiscBot
cp .env.example .env        # then put your token in .env
mkdir -p data
cp /path/to/old/kqbot.sqlite3 data/   # optional: bring your data
docker compose up -d --build
docker compose logs -f      # watch it start; Ctrl+C stops watching, not the bot
```

The bot restarts on its own after crashes and reboots
(`restart: unless-stopped`).

To update after new code is pushed:

```bash
git pull
docker compose up -d --build
```

## Checks on GitHub

Every push and pull request runs `.github/workflows/ci.yml` on GitHub:

- tests and lint on Python 3.11 and 3.13
- a Docker image build, plus a check that the image starts

You can see the results on the repo's **Actions** tab, or as a ✅/❌ next to each
commit.
