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

On the same tab, leave all three **Privileged Gateway Intents** turned off.
The bot doesn't need them.

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

Only the first three are used in the current version. The rest are for the
upcoming setup and reminder features, so you won't need to re-invite later.

## 4. (Optional) Get your server ID for faster testing

Global slash commands can take a while to appear. While developing, set
`DEV_GUILD_ID` in `.env` so commands show up in your server immediately:

1. Discord → **User Settings → Advanced → Developer Mode** on.
2. Right-click your server icon → **Copy Server ID**.
3. Paste it into `.env` as `DEV_GUILD_ID=...`.

Leave it blank once the bot is hosted for real.
