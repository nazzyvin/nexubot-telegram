import functools
import os
import re
import time
import logging

from telegram import Update
from telegram.ext import ContextTypes

from services import storage

logger = logging.getLogger(__name__)

OWNER_ID = int(os.getenv('OWNER_ID', '0'))
logger.info(f"Vault handler loaded with OWNER_ID={OWNER_ID}")

DURATION_RE = re.compile(r'^(\d+)([mhd])$', re.IGNORECASE)
UNITS = {'m': 60, 'h': 3600, 'd': 86400}


def owner_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        logger.info(f"owner_only check: user_id={user.id if user else None}, OWNER_ID={OWNER_ID}")
        if user is None or user.id != OWNER_ID:
            logger.warning(f"Access denied for user_id={user.id if user else None}")
            if update.effective_message:
                await update.effective_message.reply_text("🔒 Private storage. Owner-only feature.")
            return
        logger.info(f"Access granted for user_id={user.id}")
        return await func(update, context)
    return wrapper


def parse_duration(text):
    match = DURATION_RE.match(text.strip())
    if not match:
        return None
    seconds = int(match.group(1)) * UNITS[match.group(2).lower()]
    return seconds if seconds > 0 else None


def format_expiry(expires_at):
    if expires_at is None:
        return "forever"
    delta = max(0, int(expires_at - time.time()))
    days, rem = divmod(delta, 86400)
    hours, minutes = divmod(rem, 3600)[0], divmod(rem, 3600)[1] // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return ", ".join(parts) + " left"


def extract_media(message):
    if message.photo:
        return message.photo[-1].file_id, "photo"
    if message.video:
        return message.video.file_id, "video"
    return None, None


@owner_only
async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"save_command called by user_id={update.effective_user.id}")
    msg = update.message
    target = msg.reply_to_message
    if target is None:
        await msg.reply_text("Reply to a photo or video with /save <time>. Time like 30m, 12h, 7d, or omit for forever.")
        return
    file_id, kind = extract_media(target)
    if file_id is None:
        await msg.reply_text("That message isn't a photo or video.")
        return
    ttl = None
    if context.args:
        ttl = parse_duration(context.args[0])
        if ttl is None:
            await msg.reply_text("Bad duration. Use e.g. 30m, 12h, 7d — or omit for forever.")
            return
    code = await storage.save_media(update.effective_user.id, file_id, kind, ttl)
    await msg.reply_text(f"💾 Saved ({kind}).\nCode: {code}\nExpiry: {format_expiry(time.time() + ttl if ttl else None)}")


@owner_only
async def get_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /get <code>")
        return
    row = await storage.get_media(context.args[0])
    if row is None:
        await update.message.reply_text("❌ Not found (or expired).")
        return
    _, _, file_id, kind, _, _ = row
    if kind == "photo":
        await update.message.reply_photo(file_id)
    else:
        await update.message.reply_video(file_id)


@owner_only
async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"del_command called by user_id={update.effective_user.id} with args={context.args}")
    if not context.args:
        await update.message.reply_text("Usage: /del <code>")
        return
    if await storage.delete_media(context.args[0], update.effective_user.id):
        await update.message.reply_text("🗑 Deleted.")
    else:
        await update.message.reply_text("❌ Not found.")
        

@owner_only
async def mylist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"mylist_command called by user_id={update.effective_user.id}")
    rows = await storage.list_media(update.effective_user.id)
    if not rows:
        await update.message.reply_text("Vault is empty.")
        return
    lines = [f"`{code}` - {kind} - {format_expiry(exp)}" for code, kind, _, exp in rows]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")