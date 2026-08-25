import time

from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""🤖 Welcome to Nexu-Bot!

Your all-in-one Telegram companion. 🚀

Use /help to see what I can do. ⚡""")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""📖 NexuBot Commands

🎱 Fun
/8ball <question> - Ask the magic 8-ball
/coinflip - Flip a coin
/rps <rock|paper|scissors> - Play rock-paper-scissors
/convert - Convert replied-to sticker (PNG, MP4, file)

🎲 Games
/roll <NdM> - Roll dice (e.g. 2d6)
/choose <a> <b> ... - Pick a random option
/ttt <@user> - TicTacToe
/connect4 <@user> - Connect 4
/games - Show active game
/forfeit (or /quit) - Give up your active game
/leaderboard - Show this chat's game leaderboard

⚙️ Utility
/ping - Check bot latency
/save [time] - Store replied media (reply to it)
/get <code> - Retrieve stored media
/del <code> - Delete stored media
/mylist - Show my saved codes

👥 Group
/welcome [text|off] - Set welcome message (admin)
@botname - Mention bot for a reply""")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    latency = max(0, round((time.time() - update.message.date.timestamp()) * 1000))
    await update.message.reply_text(f"🏓 Pong! {latency}ms")
