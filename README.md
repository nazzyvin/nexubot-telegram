# NexuBot

A feature-rich Telegram bot built with python-telegram-bot v22, featuring games, media vault, sticker conversion, and group utilities.

## Features

### 🎮 Games
- **TicTacToe** (`/ttt @user`) — Challenge someone, they tap "Join Game"
- **Connect 4** (`/connect4 @user`) — Same flow, drop pieces in columns
- **Games status** (`/games`) — Show active game in chat

### 🎱 Fun Commands
- `/8ball <question>` — Magic 8-ball
- `/coinflip` — Heads or tails
- `/rps <rock|paper|scissors>` — Rock-paper-scissors
- `/roll <NdM>` — Dice roller (e.g., `2d6`)
- `/choose <a> <b> ...` — Random picker

### 🖼️ Sticker Conversion
- `/convert` (reply to sticker) — Converts to:
  - Static → PNG photo
  - Video sticker → MP4 video
  - Animated (.tgs) → Raw file

### 💾 Media Vault (Owner Only)
- `/save <time>` — Reply to photo/video, stores with code (e.g., `30m`, `12h`, `7d`, or forever)
- `/get <code>` — Retrieve media
- `/del <code>` — Delete entry
- `/mylist` — List your saved media

### 👥 Group Features
- `/welcome [text|off]` — Admin sets custom welcome message with `{name}`, `{username}`, `{first_name}` placeholders
- `@botname` — Mention bot for a friendly reply (rate-limited)

### ⚙️ Utility
- `/ping` — Bot latency check
- `/help` — Full command list

## Quick Start

### Local Development
```bash
# Clone
git clone https://github.com/YOUR_USERNAME/nexubot-telegram-python.git
cd nexubot-telegram-python

# Create venv
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# Install deps
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your TOKEN and OWNER_ID

# Optional: PostgreSQL for persistence
# docker run -d --name pg -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=nexubot -p 5432:5432 postgres:16
# $env:DATABASE_URL="postgresql://postgres:pass@localhost:5432/nexubot"

# Run
python main.py
```

### Railway Deploy (Recommended)
1. Push to GitHub
2. Railway → New Project → Deploy from GitHub
3. Add **PostgreSQL** plugin (free tier)
4. Set environment variables:
   - `TOKEN` — Bot token from @BotFather
   - `OWNER_ID` — Your numeric Telegram ID (from @userinfobot)
   - `DATABASE_URL` — Auto-filled by Railway's PostgreSQL
5. Deploy

## Commands Reference

| Command | Description | Scope |
|---------|-------------|-------|
| `/start` | Welcome message | All |
| `/help` | Command list | All |
| `/ping` | Latency check | All |
| `/8ball <q>` | Magic 8-ball | All |
| `/coinflip` | Coin flip | All |
| `/rps <move>` | Rock-paper-scissors | All |
| `/roll <NdM>` | Dice roll | All |
| `/choose <a> <b>` | Random choice | All |
| `/convert` | Convert replied sticker | All |
| `/ttt @user` | TicTacToe challenge | Groups/PM |
| `/connect4 @user` | Connect 4 challenge | Groups/PM |
| `/games` | Active game status | All |
| `/save <time>` | Store replied media | Owner |
| `/get <code>` | Retrieve media | Owner |
| `/del <code>` | Delete media | Owner |
| `/mylist` | List saved media | Owner |
| `/welcome [text|off]` | Set welcome message | Group admins |

## Architecture

```
main.py              # Entry point, handler registration, lifecycle
handlers/
  basic.py           # start, help, ping
  fun.py             # 8ball, coinflip, rps, roll, choose
  stickers.py        # /convert (sticker → PNG/MP4/file)
  vault.py           # save/get/del/mylist (owner-only)
  games.py           # TicTacToe, Connect4, join flow
  group.py           # welcome, mention reply, new member
  __init__.py        # Exports
services/
  storage.py         # asyncpg PostgreSQL layer
  __init__.py
sql/
  schema.sql         # Database schema
```

## Requirements

- Python 3.10+
- python-telegram-bot 22.8+
- asyncpg (PostgreSQL)
- Pillow (image conversion)
- imageio-ffmpeg (bundled ffmpeg for MP4 conversion)
- APScheduler (job queue)

## Security Notes

- **Never commit `.env`** — Contains bot token
- Bot token in `.env` should be rotated if accidentally exposed
- Owner-only commands restricted by `OWNER_ID`
- Rate limiting on mention replies (1/min/chat)

## License

MIT