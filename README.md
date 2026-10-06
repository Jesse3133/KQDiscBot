# Fiesta KQ Bot

A Discord bot that tracks **Kingdom Quest** start times for Fiesta Online (NA)
and tells your server when they're about to begin.

| Event | Starts (Pacific time, odd hours) | Recruitment |
|---|---|---|
| 🌙 Midnight Brigade Veteran | xx:00 | 30 min |
| 🤖 The Millennium Robo Plot | xx:01 | 30 min |
| 🍯 Mean Giant Honeying | xx:03 | 30 min |
| 🐉 Mini Dragon HC | xx:09 | 30 min |
| 🏴‍☠️ Mara Pirates' Rage | xx:12 | 30 min |

"Odd hours" means 1:00, 3:00, 5:00 … 23:00 on a US Pacific clock. The game
follows daylight saving, so in UTC the events are on even hours in summer and
odd hours in winter. The bot handles this automatically, and Discord shows
every player the times in their own time zone.

## Status

| Phase | What | State |
|---|---|---|
| 0 | Project setup | ✅ |
| 1 | Schedule math + tests | ✅ |
| 2 | Bot connects, `/next` command | ✅ |
| 3 | Auto-setup: roles, channels, reaction-role message | planned |
| 4 | Reminders 3 min before, role pings, ✅/❌, auto-delete | planned |
| 5 | Admin commands: `/event`, `/shift`, `/config`, `/setup` | planned |
| 6 | Hosting + auto-deploy | planned |

## Commands

| Command | Who | What it does |
|---|---|---|
| `/next` | Everyone | Next start of every event, soonest first. Events currently recruiting are listed at the top. |
| `/next event:<name>` | Everyone | Same, for one event. |

Replies are only visible to the person who ran the command.

## Running it locally

You need **Python 3.11 or newer**.

1. Set up the bot in Discord and get a token: see
   [docs/discord-setup.md](docs/discord-setup.md).
2. In this folder, create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   # macOS / Linux:
   source .venv/bin/activate
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1

   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`
   (and optionally `DEV_GUILD_ID`).
4. Start the bot:

   ```bash
   python -m kqbot
   ```

   You should see `Logged in as Fiesta KQ Bot ...`. Stop it with Ctrl+C.

## Settings (`.env`)

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `DISCORD_TOKEN` | yes | | Bot token from the Developer Portal |
| `GAME_TIMEZONE` | no | `America/Los_Angeles` | Time zone the game schedules events in |
| `DEV_GUILD_ID` | no | | Test server ID; slash commands register there instantly |

## Development

```bash
pip install -r requirements-dev.txt
pytest            # run the tests
ruff check .      # lint
ruff format .     # auto-format
```

### Project layout

```
kqbot/
  __main__.py      entry point (python -m kqbot)
  bot.py           bot client: loads commands, registers slash commands
  config.py        reads settings from .env
  events.py        the 5 Kingdom Quests and their timing
  schedule.py      "when does it start next?" math, incl. daylight saving
  formatting.py    message text
  cogs/
    schedule_commands.py   /next
tests/             unit tests for the schedule math and message text
docs/              setup guides
```

### Changing event times (for now)

Until the admin commands are built, event timing lives in
[`kqbot/events.py`](kqbot/events.py). Each event has a `minute`, an
`interval_hours` (2) and a `first_hour` (1, which together mean odd hours).
Edit, run `pytest`, and restart the bot.

### How daylight saving is handled

Event hours are defined in Pacific time, so the bot follows the clock change
just like the game does:

- **Clocks fall back (first Sunday of November):** 1:00–1:59 AM happens twice.
  The bot counts the 1:xx events once, at the first one.
- **Clocks spring forward (second Sunday of March):** 2:00–2:59 AM is skipped.
  That's an even hour, so no Kingdom Quests are affected.

> **To check after Nov 1, 2026:** Mean Giant Honeying should start at
> **17:03 UTC** (9:03 AM PST). If it's still at 16:03 UTC, the game actually
> runs on UTC: set `GAME_TIMEZONE=UTC` and change `first_hour` to `0` in
> `kqbot/events.py`.
