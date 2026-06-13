# Kronk — Whiteout Survival Discord Bot

Discord bot for SVS event coordination. Tracks pet buff timers and posts warnings to the channel where the command was used.

---

## Commands

| Command | Description |
|---|---|
| `/pet-buff` | Starts your 2-hour pet buff timer. Posts a warning at 1h40m and a deactivation message at 2h. Running it again silently replaces the existing timer. |

---

## Setup

### 1. Clone / copy the project

```
bot/
  main.py
  web.py
  utils.py
  requirements.txt
  .env.example
  commands/
    pet_buff.py
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

| Variable | Where to find it |
|---|---|
| `BOT_TOKEN` | Discord Developer Portal → your app → **Bot** tab → **Token** |

Optional:

| Variable | Default | Description |
|---|---|---|
| `WEB_PORT` | `8080` | Port for the Terms / Privacy web server |

### 4. Invite the bot

In the Discord Developer Portal → **OAuth2 → URL Generator**:
- Scopes: `bot`, `applications.commands`
- Bot permissions: `Send Messages`, `Mention Everyone`

Open the generated URL and add the bot to your server.

### 5. Run

```bash
python main.py
```

The bot registers slash commands globally on startup. Commands may take up to an hour to appear in Discord the first time — usually a few minutes.

---

## Persistence & crash recovery

Active timers are saved to `timers.json`. On restart the bot reads this file and:
- Re-schedules timers that haven't expired yet
- Immediately posts a deactivation message for any that expired while offline

---

## Legal pages (required by Discord)

The web server exposes two routes used in the Developer Portal:

| Route | URL |
|---|---|
| Terms of Service | `http://your-server-ip:8080/terms` |
| Privacy Policy | `http://your-server-ip:8080/privacy` |

---

## Deployment (DigitalOcean)

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

---

## Adding future commands

1. Create `commands/your_command.py` with a `setup(bot)` function and a `commands.Cog` class
2. Add `"commands.your_command"` to the `COGS` list in `main.py`
# kronk
