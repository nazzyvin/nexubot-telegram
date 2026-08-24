import os
import asyncio
import logging

from aiohttp import web
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler

from handlers import (
    start, help_command, ping,
    eightball, coinflip, roll, choose, rps,
    convert_command,
    save_command, get_command, mylist_command, del_command,
    get_game_handlers,
    get_group_handlers,
)
from services import storage, init_pool, close_pool


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def purge_job(context: ContextTypes.DEFAULT_TYPE):
    await storage.purge_expired()


async def on_startup(app):
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        logger.warning("DATABASE_URL not set — vault & welcome will not persist")
    else:
        await storage.init_pool(dsn)
        logger.info("PostgreSQL pool initialized")


async def on_shutdown(app):
    await close_pool()
    logger.info("PostgreSQL pool closed")


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing update:", exc_info=context.error)
    if isinstance(update, object) and hasattr(update, "effective_message") and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Something went wrong handling that command.")
        except Exception:
            pass


load_dotenv()

token = os.getenv('TOKEN')


async def main():
    app = (
        Application.builder()
        .token(token)
        .build()
    )

    # Core commands
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('ping', ping))
    app.add_handler(CommandHandler('8ball', eightball))
    app.add_handler(CommandHandler('coinflip', coinflip))
    app.add_handler(CommandHandler('roll', roll))
    app.add_handler(CommandHandler('choose', choose))
    app.add_handler(CommandHandler('rps', rps))
    app.add_handler(CommandHandler('convert', convert_command))

    # Vault (owner-only)
    app.add_handler(CommandHandler('save', save_command))
    app.add_handler(CommandHandler('get', get_command))
    app.add_handler(CommandHandler('del', del_command))
    app.add_handler(CommandHandler('mylist', mylist_command))

    # Games
    for h in get_game_handlers():
        app.add_handler(h)

    # Group features
    for h in get_group_handlers():
        app.add_handler(h)

    app.job_queue.run_repeating(purge_job, interval=3600, first=30)
    app.add_error_handler(on_error)

    # --- Health check server (for Railway) ---
    async def health(request):
        return web.Response(text="OK")

    health_app = web.Application()
    health_app.router.add_get('/health', health)

    runner = web.AppRunner(health_app)
    await runner.setup()
    port = int(os.getenv('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Healthcheck server started on port {port}")

    # --- Bot lifecycle (manual, since we're already inside an event loop) ---
    # NOTE: post_init/post_shutdown builder hooks are NOT called under manual
    # lifecycle (async with app / app.start()) — those only fire inside
    # run_polling()/run_webhook(). So we call on_startup/on_shutdown ourselves.
    async with app:
        await on_startup(app)
        await app.start()
        await app.updater.start_polling(poll_interval=5)
        logger.info("Bot polling started")

        try:
            # Keep the process alive until cancelled (Ctrl+C / container stop)
            await asyncio.Event().wait()
        finally:
            logger.info("Shutting down...")
            await app.updater.stop()
            await app.stop()
            await on_shutdown(app)
            await runner.cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass