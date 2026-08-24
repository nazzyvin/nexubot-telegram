import random

from telegram import Update
from telegram.ext import ContextTypes



EIGHT_BALL_RESPONSES = [
    "It is certain. ✅", "Without a doubt. ✅", "Yes, definitely. ✅",
    "Most likely. 👍", "Outlook good. 👍", "Signs point to yes. 🌟",
    "Reply hazy, try again. 🌀", "Ask again later. ⏳",
    "Better not tell you now. 🤐", "Cannot predict now. 🔮",
    "Don't count on it. ❌", "My reply is no. 🚫",
    "My sources say no. 📉", "Very doubtful. 😬",
]

MOVES = ["rock", "paper", "scissors"]
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}


async def eightball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /8ball <your question>")
        return
    await update.message.reply_text(f"🎱 {random.choice(EIGHT_BALL_RESPONSES)}")


async def coinflip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🪙 {random.choice(['Heads', 'Tails'])}!")


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Give me at least two options, e.g. /choose pizza burger")
        return
    await update.message.reply_text(f"🤔 I choose: {random.choice(context.args)}")


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    spec = context.args[0] if context.args else "1d6"
    try:
        count_str, sides_str = spec.lower().split("d")
        count = int(count_str) if count_str else 1
        sides = int(sides_str)
    except ValueError:
        await update.message.reply_text("Invalid format. Use NdM, e.g. /roll 2d6")
        return
    if not (1 <= count <= 100 and 2 <= sides <= 1000):
        await update.message.reply_text("use 1-100 dice with 2-1000 sides.")
        return
    rolls = [random.randint(1, sides) for _ in range(count)]
    await update.message.reply_text(f"🎲 {' + '.join(map(str, rolls))} = {sum(rolls)}")


async def rps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in MOVES:
        await update.message.reply_text("Usage: /rps rock|paper|scissors")
        return
    player = context.args[0].lower()
    bot_move = random.choice(MOVES)
    if player == bot_move:
        outcome = "It's a tie! 🫱🏼‍🫲🏼"
    elif BEATS[player] == bot_move:
        outcome = "You win! 🎉"
    else:
        outcome = "I win! 💀"
    await update.message.reply_text(
        f"You: {EMOJI[player]} {player}\nMe: {EMOJI[bot_move]} {bot_move}\n\n{outcome}"
    )


