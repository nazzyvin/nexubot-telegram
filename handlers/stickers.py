import io
import os
import subprocess
import tempfile

from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes, filters


class StickerFilter(filters.MessageFilter):
    def filter(self, message):
        return message.sticker is not None


sticker_filter = StickerFilter()


def _get_replied_sticker(update: Update):
    target = update.message.reply_to_message
    if target and target.sticker:
        return target.sticker
    return None


def _ffmpeg_exe():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return None


async def _download_sticker_bytes(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes:
    file = await context.bot.get_file(file_id)
    return await file.download_as_bytearray()


async def _send_as_photo(update: Update, buf: io.BytesIO, name: str):
    buf.seek(0)
    buf.name = name
    await update.message.reply_photo(photo=buf)


async def _send_as_document(update: Update, buf: io.BytesIO, name: str):
    buf.seek(0)
    buf.name = name
    await update.message.reply_document(document=buf)


async def _send_as_video(update: Update, path: str):
    with open(path, "rb") as f:
        await update.message.reply_video(video=f, supports_streaming=True)


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sticker = _get_replied_sticker(update)
    if not sticker:
        await update.message.reply_text(
            "Reply to a sticker with /convert to convert it."
        )
        return

    try:
        data = await _download_sticker_bytes(context, sticker.file_id)
    except Exception:
        await update.message.reply_text("Failed to download the sticker file.")
        return

    if sticker.is_animated:
        buf = io.BytesIO(data)
        await _send_as_document(update, buf, f"{sticker.file_unique_id}.tgs")
        return

    if sticker.is_video:
        exe = _ffmpeg_exe()
        if exe is None:
            await update.message.reply_text("Video conversion unavailable (ffmpeg not bundled).")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, f"{sticker.file_unique_id}.webm")
            dst = os.path.join(tmpdir, f"{sticker.file_unique_id}.mp4")
            with open(src, "wb") as f:
                f.write(data)

            cmd = [
                exe, "-y", "-i", src,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-an",
                dst,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            except subprocess.CalledProcessError as e:
                await update.message.reply_text(f"Conversion failed:\n{e.stderr.decode().strip()[-500:]}")
                return
            except subprocess.TimeoutExpired:
                await update.message.reply_text("Conversion timed out.")
                return

            if os.path.getsize(dst) == 0:
                await update.message.reply_text("Conversion produced an empty file.")
                return

            await _send_as_video(update, dst)
        return

    buf = io.BytesIO(data)
    try:
        img = Image.open(buf)
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        out.name = f"{sticker.file_unique_id}.png"
        await update.message.reply_photo(photo=out)
    except Exception:
        await update.message.reply_text("Failed to convert the static sticker.")