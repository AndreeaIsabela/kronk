# Kronk — Whiteout Survival Discord Bot

Discord bot for SVS event coordination. Tracks pet buff timers and posts notifications to the channel where the command was used. Supports multiple servers independently.

---

## Commands

### Pet Buff

| Command | Description |
|---|---|
| `/pet-buff` | Starts your 2-hour pet buff 🐯💥 timer. |
| `/pet-buff targets: @P1 @P2` | Starts timers for the mentioned players. |
| `/pet-buff targets: rally-leaders` | Starts timers for everyone on the rally leaders list. Autocompletes. |
| `/pet-buff-cancel` | Cancels your active timer. |
| `/pet-buff-cancel targets: @P1 @P2` | Cancels timers for the mentioned players. |
| `/pet-buff-cancel targets: rally-leaders` | Cancels timers for all rally leaders. Autocompletes. |

**Timer behaviour:**
- Each player can only have one active timer at a time — use `/pet-buff-cancel` before starting a new one
- Activation and cancellation post a single public message listing all affected players as clickable mentions (no notification sent)
- ⚠️ Warning fires 20 minutes before expiry with an `@everyone` ping
- ❌ Deactivation message posts when the 2 hours are up
- Warnings and expiry messages for players whose timers fire at the same time are batched into a single message

### Rally Leaders

| Command | Description |
|---|---|
| `/set-rally-leaders roster: @P1 @P2 …` | Saves the rally leaders list (replaces any existing one). |
| `/rally-leaders` | Shows the current rally leaders list (only visible to you). |

### Events

| Command | Description |
|---|---|
| `/set-event event_name date_time frequency` | Schedules a notification in the current channel. Reusing an event name replaces it. |
| `/list-events` | Lists all scheduled events in this server with their details (only visible to you). |
| `/cancel-event event_name` | Cancels a scheduled event by name. |

**Parameters for `/set-event`:**
- `event_name` — unique per server; reusing it silently replaces the existing event
- `date_time` — UTC, two formats accepted:
  - `HH:MM` — today at that time, or tomorrow if it has already passed
  - `YYYY-MM-DD HH:MM` — exact date (returns an error if in the past)
- `frequency` — `once` / `daily` / `bi-daily` / `weekly` / `monthly`
- `custom_message` _(optional)_ — text sent when the event fires; defaults to the event name
- `players` _(optional)_ — @mention any number of players to ping; defaults to @everyone

**Event behaviour:**
- Confirmation after `/set-event` is ephemeral (only the setter sees it)
- Notification when the event fires is public and visible to everyone in the channel
- Recurring events survive bot restarts — missed occurrences are skipped and the next future one is scheduled automatically
- Missed one-time events fire immediately on the next bot startup

---

## Setup

### 1. Project structure

```
bot/
  main.py
  web.py
  db.py
  utils.py
  requirements.txt
  .env.example
  commands/
    pet_buff.py
    rally_leaders.py
    set_event.py
  templates/
    terms.html
    privacy.html
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Required | Where to find it |
|---|---|---|
| `BOT_TOKEN` | ✅ | Discord Developer Portal → your app → **Bot** tab → **Token** |
| `MONGO_URI` | ✅ | MongoDB Atlas connection string, or `mongodb://localhost:27017` for local |
| `MONGO_DB_NAME` | — | Database name (default: `kronk`) |
| `WEB_PORT` | — | Port for the Terms/Privacy web server (default: `8080`) |

### 4. Set up MongoDB

**Option A — Local (for testing):**
Download and install [MongoDB Community Server](https://www.mongodb.com/try/download/community). It runs as a Windows service automatically. Use `MONGO_URI=mongodb://localhost:27017`.

**Option B — MongoDB Atlas (for production, free tier):**
1. Create a free account at [mongodb.com](https://www.mongodb.com)
2. Create a free **M0** cluster
3. Add a database user under **Database Access**
4. Allow `0.0.0.0/0` under **Network Access**
5. Click **Connect** → **Drivers** → copy the connection string into `MONGO_URI`

The `kronk` database and its collections are created automatically on first use.

### 5. Invite the bot

In the Discord Developer Portal → **OAuth2 → URL Generator**:
- Scopes: `bot`, `applications.commands`
- Bot permissions: `Send Messages`, `Mention Everyone`

Open the generated URL and add the bot to your server.

### 6. Run

```bash
python main.py
```

Slash commands register globally on startup. They may take up to an hour to appear in Discord the first time — usually a few minutes. Press **Ctrl+R** in Discord to refresh if they don't show immediately.

---

## Persistence & crash recovery

All timers are stored in MongoDB, scoped by server ID. On restart the bot:
- Re-schedules timers that haven't expired yet (with correct remaining time)
- Immediately posts a deactivation message for any that expired while offline

This works across all servers the bot is in simultaneously.

---

## Legal pages (required by Discord)

The web server exposes two routes to fill in the Developer Portal:

| Page | URL |
|---|---|
| Terms of Service | `http://your-server-ip:8080/terms` |
| Privacy Policy | `http://your-server-ip:8080/privacy` |

---

## Deployment (DigitalOcean Droplet)

```bash
# Install Python 3.11+
sudo apt update && sudo apt install python3 python3-pip -y

# Install dependencies
pip install -r requirements.txt

# Create and fill .env
cp .env.example .env && nano .env

# Run as a systemd service so it restarts on reboot/crash
sudo nano /etc/systemd/system/kronk.service
```

`kronk.service`:
```ini
[Unit]
Description=Kronk Discord Bot
After=network.target

[Service]
WorkingDirectory=/home/your-user/bot
ExecStart=/usr/bin/python3 main.py
Restart=always
EnvironmentFile=/home/your-user/bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable kronk
sudo systemctl start kronk
sudo systemctl status kronk
```

**Recommended stack:** $4/month DigitalOcean Droplet + MongoDB Atlas free tier.

---

## Adding future commands

1. Create `commands/your_command.py` with a `commands.Cog` class and a `setup(bot)` function
2. Add `"commands.your_command"` to the `COGS` list in `main.py`
3. Use `db.py` for any persistent data — scope all queries by `guild_id` for multi-server support
