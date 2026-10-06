# Fiesta KQ Bot

A Discord bot that tracks **Kingdom Quest** start times for Fiesta Online (NA)
and tells your server when they're about to begin.

| Event | Levels | Starts (Pacific time, odd hours) | Recruitment |
|---|---|---|---|
| 🏴‍☠️ Mara Pirates' Rage | 17-25 | xx:12 | 30 min |
| 🤖 The Millennium Robo Plot | 33-45 | xx:01 | 30 min |
| 🌙 Midnight Brigade Veteran | 36-65 | xx:00 | 30 min |
| 🍯 Mean Giant Honeying | 40-50 | xx:03 | 30 min |
| 🐉 Mini Dragon HC | 46-60 | xx:09 | 30 min |

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
| 5 | Admin commands: `/event`, `/shift`, `/config` | ✅ |
| 6 | Hosting + auto-deploy (home PC / Raspberry Pi, CI) | ✅ |

## Commands

**Everyone**

| Command | What it does |
|---|---|
| `/next` | Next start of every event, soonest first. Events currently recruiting are listed at the top. |
| `/next event:<name>` | Same, for one event. |

**Admins** (members with **Manage Server**)

| Command | What it does |
|---|---|
| `/event list` | Every event with its timing and recruitment length. |
| `/event add` | Add an event: name, minute, emoji, and optionally interval, first hour, recruitment length and level range (`min_level` + `max_level`). Creates its role and adds it to the role picker. |
| `/event edit` | Change any of those for an existing event. Only the options you fill in change. Renaming also renames its role; people keep it. Set both levels to `0` to remove the range. `note` adds text to that event's reminders (see below). |
| `/event remove` | Remove an event. Asks for confirmation, then deletes its role (taking it from everyone) and its picker emoji. |
| `/shift` | Move only the **next** start of one event, or all events, by up to ±180 minutes (e.g. for maintenance). `minutes:0` puts it back. Reminders and `/next` follow the new time. |
| `/config show` | Current settings. |
| `/config alerts-channel` | Post reminders in a different channel. |
| `/config roles-channel` | Move the role picker to a different channel. People keep their roles. |
| `/config reminder-text` | Text added to the bottom of every reminder (see below). |
| `/config timezone` | Time zone the game schedules events in. Overrides `GAME_TIMEZONE` in `.env`. |
| `/setup` | Create anything that's missing: roles, channels, the role picker message. Safe to run any time. |
| `/test-reminder` | Post a test reminder for every event (or one with `event:`) that really pings the roles, and list anything that would stop pings working. Test messages delete themselves after 5 minutes. |

Replies are only visible to the person who ran the command. To change who
can use the admin commands, go to Server Settings → Integrations →
Fiesta KQ Bot.

Events and the time zone are shared by every server the bot is in. Channels
and roles are per server.

### Event timing options

Events start at `minute` past the hour, every `interval` hours, on the hours
that line up with `first_hour` in game time:

| You want | interval | first_hour |
|---|---|---|
| Odd hours (01:00, 03:00, …) | every 2 hours | 1 |
| Even hours (00:00, 02:00, …) | every 2 hours | 0 |
| Every hour | every hour | any |
| 02:00, 06:00, 10:00, … | every 4 hours | 2 |
| Once a day at 20:00 | once a day | 20 |

### Custom emojis

Any emoji from a server the bot is in works: pick it from the emoji picker
when filling in `emoji:`. To use your own icons (e.g. the in-game ones)
without using up server emoji slots, upload them as **application emojis**:

1. Developer Portal → your app → **Emojis** → **Upload Emoji**.
2. Copy its markdown (it looks like `<:honey:123456789012345678>`).
3. Paste that into the `emoji:` option of `/event add` or `/event edit`.

When you change an event's emoji, people keep the role they have.

### Role picker order

Events are listed by the lowest level that can join. Events without a level
range go last. Discord can't reorder the emojis under a message, so when the
order changes (a new event lands in the middle, levels change, or an emoji
changes) the bot posts a fresh picker and deletes the old one. Everyone keeps
their roles, but their old reactions go with the old message. To drop a role
afterwards, react on the new message and then remove the reaction.

## Reminders

3 minutes before each Kingdom Quest, the bot posts in `#kq-alerts`:

> @Mean Giant Honeying 🍯 **Mean Giant Honeying** is starting soon!
> Starts 9:03 AM (in 3 minutes) · Recruitment closes 9:33 AM

- It pings only that event's role. People choose roles in `#kq-roles`.
- ✅ and ❌ are added so people can say whether they're coming.
- The message is deleted when recruitment closes, 30 minutes after the start.
- Every event gets its own message, even when two start a minute apart.
- If an event was moved with `/shift`, the reminder follows the new time and
  says "moved from …".
- If the bot was offline and comes back within the 3 minutes, it still posts.
  If the event has already started, it skips that reminder. Reminders that
  should have been deleted while it was offline are deleted on startup.

### Adding your own text to reminders

Two optional texts, both empty until you set them:

| Text | Set with | Shows on |
|---|---|---|
| Event note | `/event edit event:<name> note:<text>` | That event's reminders only, e.g. where to meet or what to bring. |
| Shared text | `/config reminder-text text:<text>` | Every reminder, under the event's note, e.g. "React ✅ if you're coming". |

- Type `\n` for a new line: `Meet at Elderine\nBring fire resistance`.
- Discord formatting works: `**bold**`, `*italics*`, links, `#channel` mentions.
- Set either to `-` to remove it.
- `/event list` shows each event's note, and `/config show` shows the shared
  text. Run `/test-reminder` to see how a reminder looks.
- Limits: 500 characters per note, 1000 for the shared text.

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
| Role picker message | Lists each event with its emoji and level range, lowest level first. React to get that event's role, remove your reaction to lose it. |

Both channels are read-only for members: they can read and click existing
reactions, but can't post or add new emojis. Admins can still post.

If someone reacts while the bot is offline, they get the role when the bot
starts. Removing a reaction while the bot is offline isn't caught up (Discord
doesn't tell bots about that without an extra privileged permission), so
that person should react and un-react again.

If something already exists **with the same name**, the bot reuses it instead
of making a duplicate. If you delete a role, channel or the picker message,
`/setup` puts it back. Renaming a channel is fine: the bot remembers channels
by ID.

> **Role order matters.** In Server Settings → Roles, the **Fiesta KQ Bot**
> role must be **above** the 5 event roles, or it can't give them out. Roles
> the bot creates start out below it, so this only comes up if you move them.

## Running it 24/7

To keep the bot running on a Windows PC or Raspberry Pi, restarting and
updating itself from GitHub's `main` branch, follow
**[docs/hosting.md](docs/hosting.md)**. The steps below are for running it by
hand, e.g. while testing.

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
| `GAME_TIMEZONE` | no | `America/Los_Angeles` | Time zone the game schedules events in. `/config timezone` overrides it. |
| `DEV_GUILD_ID` | no | | Test server ID; slash commands register there instantly |
| `DATABASE_PATH` | no | `kqbot.sqlite3` | Where the bot stores its data |

The database file holds the events, settings changed with `/config`, shifts,
and which roles, channels and message belong to the bot. Back it up if you move the bot to another computer. If
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
| `Another copy of the bot is already running` | The background task/service is already running it. Stop that first (see [docs/hosting.md](docs/hosting.md)), or use it instead of starting by hand. |
| Bot isn't updating after a merge | Check `logs/supervisor.log`. It says why, e.g. the folder isn't on `main` or has hand-edited files. |
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
  supervise.py     keeps the bot running and updates it (python -m kqbot.supervise)
  instance_lock.py stops two copies running against one database
  schedule.py      "when does it start next?" math, incl. daylight saving
  formatting.py    message text
  cogs/
    schedule_commands.py   /next
    setup_commands.py      /setup, auto-setup on join and first start
    reaction_roles.py      gives/removes roles on role picker reactions
    reminders.py           reminder loop, cleanup, /test-reminder
    common.py              shared helpers for commands
tests/             unit tests (Discord is faked, no token needed)
docs/              setup and hosting guides
scripts/           install the bot as a Windows task or Linux service
Dockerfile         container image (data in /data)
docker-compose.yml run with Docker on your own machine
.github/workflows/ CI: tests, lint and Docker build on every push
```

### Where events are stored

The 5 starting events are defined in [`kqbot/events.py`](kqbot/events.py) and
copied into the database the first time the bot starts. After that the
database is what counts: change events with the `/event` commands, not by
editing `events.py`.

### How daylight saving is handled

Event hours are defined in Pacific time, so the bot follows the clock change
just like the game does:

- **Clocks fall back (first Sunday of November):** 1:00–1:59 AM happens twice.
  The bot counts the 1:xx events once, at the first one.
- **Clocks spring forward (second Sunday of March):** 2:00–2:59 AM is skipped.
  That's an even hour, so no Kingdom Quests are affected.

> **To check after Nov 1, 2026:** Mean Giant Honeying should start at
> **17:03 UTC** (9:03 AM PST). If it's still at 16:03 UTC, the game actually
> runs on UTC: run `/config timezone name:UTC`, then
> `/event edit first_hour:0` for each event.
