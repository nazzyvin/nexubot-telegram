import random
import re
import time
from typing import List

from telegram import Update
from telegram.ext import ContextTypes, filters, MessageHandler, CommandHandler

from services import storage


WELCOME_RESPONSES = [
    "Welcome! 🎉",
    "Hey there! 👋",
    "New face! 😎",
    "Join the party! 🎊",
]


async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == 'private':
        await update.message.reply_text("This command only works in groups.")
        return

    # Only admins/owner can set welcome
    member = await chat.get_member(user.id)
    if member.status not in ('administrator', 'creator'):
        await update.message.reply_text("Admins only.")
        return

    if not context.args:
        current = await storage.get_welcome(chat.id)
        status = "ON" if current else "OFF"
        text = current or "(none)"
        await update.message.reply_text(f"Welcome: {status}\nMessage: {text}")
        return

    if context.args[0].lower() in ('off', 'disable', '0'):
        await storage.set_welcome(chat.id, None, False)
        await update.message.reply_text("Welcome messages disabled.")
        return

    text = ' '.join(context.args)
    await storage.set_welcome(chat.id, text, True)
    await update.message.reply_text(f"Welcome set to:\n{text}")


async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.my_chat_member:
        return
    change = update.my_chat_member
    if change.new_chat_member.status == 'member' and change.old_chat_member.status == 'left':
        # New member joined
        welcome = await storage.get_welcome(change.chat.id)
        if welcome:
            name = change.new_chat_member.user.full_name
            username = change.new_chat_member.user.username or ""
            text = welcome.replace('{name}', name).replace('{username}', f"@{username}").replace('{first_name}', change.new_chat_member.user.first_name)
            await context.bot.send_message(change.chat.id, text)


MENTION_RE = re.compile(r'@(\w+)')


async def mention_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Check if bot was mentioned
    bot = context.bot
    bot_username = bot.username
    if not message.text or f'@{bot_username}' not in message.text:
        return

    # Simple rate limit per chat (1/minute in memory)
    last = context.chat_data.get('last_mention', 0)
    if time.time() - last < 60:
        return
    context.chat_data['last_mention'] = time.time()

    responses = [
        "Yes? 🤔",
        "How can I help? 😊",
        "That's me! 👋",
        random.choice(WELCOME_RESPONSES),
    ]
    await message.reply_text(random.choice(responses))


def get_group_handlers() -> List:
    return [
        CommandHandler('welcome', welcome_command),
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_chat_member),
        MessageHandler(filters.TEXT & ~filters.COMMAND, mention_handler),
    ]