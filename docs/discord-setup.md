# Setting up the bot in Discord

You only do this once. It creates the bot account, gets its token, and adds it
to your server.

## 1. Create the application

1. Go to <https://discord.com/developers/applications> and sign in.
2. Click **New Application**, name it **Fiesta KQ Bot**, accept the terms.
3. On **General Information**, set the **App Icon** to the Fiesta Online logo.
   This is the bot's profile picture.

## 2. Get the bot token

1. Open the **Bot** tab.
2. Set the **Username** to `Fiesta KQ Bot` if it isn't already.
3. Click **Reset Token**, then **Copy**.
4. Paste it into your `.env` file as `DISCORD_TOKEN=...`.

> **Keep the token secret.** Anyone with it can control the bot. It lives only
> in `.env`, which git ignores. If it ever leaks, click **Reset Token** again
> and update `.env`.

On the same tab:

- Turn **Public Bot** **off**. Otherwise anyone can add your bot to their own
  server, and since events and settings are shared between servers, their
  admins could change your reminders.
- Leave all three **Privileged Gateway Intents** turned off. The bot doesn't
  need them.

## 3. Invite the bot to your server

Copy your **Application ID** from **General Information**, put it in place of
`YOUR_APP_ID` below, and open the link:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot+applications.commands&permissions=268504144
```

Pick your server and click **Authorize**. That permission number grants:

| Permission | Why |
|---|---|
| View Channels, Send Messages, Read Message History | Post reminders and read its own messages |
| Add Reactions | Add ✅ / ❌ to reminders and the emojis to the role-picker message |
| Manage Roles | Create the 5 event roles and give/remove them on reaction |
| Manage Channels | Create the alerts and roles channels |

In Server Settings → Roles, keep the **Fiesta KQ Bot** role just above the
event roles and **below** your moderator and admin roles.

## 4. Lock the bot to your server

Get your server's ID:

1. Discord → **User Settings** (gear icon) → **Advanced** → turn on
   **Developer Mode**. (Mobile: **You** tab → gear → **Advanced** →
   **Developer Mode**.)
2. Right-click your server's icon in the left-hand server list (mobile:
   long-press it) → **Copy Server ID**. It's a long number like
   `123456789012345678`.
3. Put it in `.env`:

   ```
   ALLOWED_GUILD_IDS=123456789012345678
   ```

4. Restart the bot (or the task/service, see [hosting.md](hosting.md)).

The bot now only works in that server. It leaves any other server it's added
to, and ignores commands from servers it was already in. The startup log
warns you while `ALLOWED_GUILD_IDS` is empty.

## 5. (Optional) Faster slash command updates while testing

Global slash commands can take a while to appear. While developing, also put
your server ID in `.env` as `DEV_GUILD_ID=...` so commands show up
immediately. Leave it blank once the bot is hosted for real.
