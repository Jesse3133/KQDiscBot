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
| 3 | Auto-setup: roles, channels, reaction-role message | ✅ |
| 4 | Reminders 3 min before, role pings, ✅/❌, auto-delete | ✅ |
| 5 | Admin commands: `/event`, `/shift`, `/config`, `/setup` | planned |
| 6 | Hosting + auto-deploy | planned |

## Commands

| Command | Who | What it does |
|---|---|---|
| `/next` | Everyone | Next start of every event, soonest first. Events currently recruiting are listed at the top. |
| `/next event:<name>` | Everyone | Same, for one event. |

| `/setup` | Admins (Manage Server) | Create anything that's missing: roles, channels, the role picker message. Safe to run any time. |
| `/test-reminder` | Admins (Manage Server) | Post a test reminder for every event (or one with `event:`) that really pings the roles, and list anything that would stop pings working. Test messages delete themselves after 5 minutes. |

Replies are only visible to the person who ran the command. Admin commands are
hidden from members without **Manage Server**. You can change who sees it
under Server Settings → Integrations → Fiesta KQ Bot.

## Reminders

3 minutes before each Kingdom Quest, the bot posts in `#kq-alerts`:

> @Mean Giant Honeying 🍯 **Mean Giant Honeying** is starting soon!
> Starts 9:03 AM (in 3 minutes) · Recruitment closes 9:33 AM

- It pings only that event's role. People choose roles in `#kq-roles`.
- ✅ and ❌ are added so people can say whether they're coming.
- The message is deleted when recruitment closes, 30 minutes after the start.
- Every event gets its own message, even when two start a minute apart.
- If the bot was offline and comes back within the 3 minutes, it still posts.
  If the event has already started, it skips that reminder. Reminders that
  should have been deleted while it was offline are deleted on startup.

**Pings not arriving?** Run `/test-reminder`. It posts real test pings and
lists problems such as missing permissions or a role that isn't mentionable.
You only get notified for roles you have, so react in `#kq-roles` first.

## What the bot sets up in your server

This happens automatically when the bot joins a server, or on its first
start in a server it's already in. Run `/setup` to repeat it any time.

| What | Details |
|---|---|
| 5 roles | One per event, named after it (e.g. `@Mean Giant Honeying`). Set to mentionable so reminders can ping them. |
| `#kq-alerts` | Where reminders will be posted. |
| `#kq-roles` | Holds the role picker message. |
| Role picker message | Lists each event with its emoji. React to get that event's role, remove your reaction to lose it. |

Both channels are read-only for members: they can read and click existing
reactions, but can't post or add new emojis. Admins can still post.

If something already exists **with the same name**, the bot reuses it instead
of making a duplicate. If you delete a role, channel or the picker message,
`/setup` puts it back. Renaming a channel is fine: the bot remembers channels
by ID.

> **Role order matters.** In Server Settings → Roles, the **Fiesta KQ Bot**
> role must be **above** the 5 event roles, or it can't give them out. Roles
> the bot creates start out below it, so this only comes up if you move them.

## Running it locally

You need **Python 3.11 or newer**. Check with `python --version`
(Windows: `py --list` shows every installed version).

> **Windows:** get it from <https://www.python.org/downloads/> and tick
> **"Add python.exe to PATH"** in the installer. If an older Python is also
> installed, create the virtual environment with the new one explicitly:
> `py -3.13 -m venv .venv`. Once the venv is activated, plain `python` uses
> the right version.

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
| `DATABASE_PATH` | no | `kqbot.sqlite3` | Where the bot stores its data |

The database file holds the event list and which roles, channels and message
belong to the bot. Back it up if you move the bot to another computer. If
it's lost, run `/setup`: the bot finds its roles and channels again by name.
The only side effect is a fresh role picker message, so delete the old one.

## Troubleshooting

| Problem | Fix |
|---|---|
| A new command doesn't show up after updating | Check the startup log says `Synced N command(s)` with the right number, then reload Discord with **Ctrl+R** (desktop) or restart the app (mobile). Discord caches the command list. |
| Commands take a long time to appear | Set `DEV_GUILD_ID` in `.env` so commands register to your server instantly. |
| `/setup` or `/test-reminder` missing for someone | They're only shown to members with **Manage Server**. |
| Reminders post but nobody is notified | Run `/test-reminder`. It lists permission and role problems. You're only notified for roles you have, and not if the server's *Suppress All Role @mentions* setting is on. |
| `No module named 'discord'` | Activate the venv (`.venv\Scripts\Activate.ps1`) before `python -m kqbot`, and run `pip install -r requirements.txt` once. |
| `needs Python 3.11 or newer` | Create the venv with a newer Python: `py -3.13 -m venv .venv`. |

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
  db.py            SQLite storage (events, roles, channels)
  events.py        the 5 Kingdom Quests and their default timing
  guild_setup.py   creates/repairs roles, channels, role picker message
  reminders.py     which reminders are due (timing only)
  schedule.py      "when does it start next?" math, incl. daylight saving
  formatting.py    message text
  cogs/
    schedule_commands.py   /next
    setup_commands.py      /setup, auto-setup on join and first start
    reaction_roles.py      gives/removes roles on role picker reactions
    reminders.py           reminder loop, cleanup, /test-reminder
    common.py              shared helpers for commands
tests/             unit tests (Discord is faked, no token needed)
docs/              setup guides
```

### Changing event times (for now)

The defaults live in [`kqbot/events.py`](kqbot/events.py). Each event has a
`minute`, an `interval_hours` (2) and a `first_hour` (1, which together mean
odd hours). They're copied into the database on first start, and after that
the database is what the bot uses.

Until the admin commands (phase 5) exist, to change an event: stop the bot,
edit `events.py`, delete `kqbot.sqlite3`, start the bot, run `/setup`, and
delete the old role picker message.

### How daylight saving is handled

Event hours are defined in Pacific time, so the bot follows the clock change
just like the game does:

- **Clocks fall back (first Sunday of November):** 1:00–1:59 AM happens twice.
  The bot counts the 1:xx events once, at the first one.
- **Clocks spring forward (second Sunday of March):** 2:00–2:59 AM is skipped.
  That's an even hour, so no Kingdom Quests are affected.

> **To check after Nov 1, 2026:** Mean Giant Honeying should start at
> **17:03 UTC** (9:03 AM PST). If it's still at 16:03 UTC, the game actually
> runs on UTC: set `GAME_TIMEZONE=UTC` and change `first_hour` to `0` (see
> "Changing event times" above).
