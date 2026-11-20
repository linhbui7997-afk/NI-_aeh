import asyncio
import hashlib
import html
import io
import logging
import os
import re
import threading

from telegram import Bot
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from bot.db import save_scanned_code

log = logging.getLogger("code_scanner")
CHANNELS = ["hi88codemienphi88", "f8bet", "Hi88tinhot247", "Hi88tinmoi", "NEW88PHATCODE", "new88_official"]
CODE_RE = re.compile(os.getenv("CODE_REGEX", r"(?<![A-Za-z0-9])[A-Za-z0-9]{8,20}(?![A-Za-z0-9])"))
IGNORE = {"OFFICIAL", "REGISTER", "WELCOME", "TELEGRAM", "PASSWORD", "USERNAME", "CUSTOMER"}

def extract_codes(text):
    found = []
    for value in CODE_RE.findall(text or ""):
        code = value.strip()
        if code.upper() not in IGNORE and any(c.isalpha() for c in code) and any(c.isdigit() for c in code):
            if code not in found:
                found.append(code)
    return found

def run_scanner():
    api_id, api_hash, session, token = (os.getenv(k) for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION", "BOT_TOKEN"))
    targets = [x.strip() for x in os.getenv("SCAN_RESULT_CHAT_IDS", os.getenv("ADMIN_IDS", "")).split(",") if x.strip()]
    if not all((api_id, api_hash, session, token, targets)):
        log.warning("Scanner inactive: configure TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION, BOT_TOKEN and SCAN_RESULT_CHAT_IDS (or ADMIN_IDS).")
        return

    async def worker():
        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        bot = Bot(token)
        await client.start()
        entities = []
        for channel in CHANNELS:
            try:
                entities.append(await client.get_entity(channel))
            except Exception:
                log.exception("Cannot access source channel @%s", channel)

        @client.on(events.NewMessage(chats=entities))
        async def on_new_message(event):
            message = event.message
            chat = await event.get_chat()
            source = getattr(chat, "username", None) or str(event.chat_id)
            text_content = message.message or ""
            codes = extract_codes(text_content)
            if message.media and not codes:
                try:
                    from PIL import Image
                    import pytesseract
                    raw = await message.download_media(file=bytes)
                    if raw:
                        codes = extract_codes(pytesseract.image_to_string(Image.open(io.BytesIO(raw))))
                except Exception:
                    log.exception("Image OCR failed for @%s message %s", source, message.id)

            post_url = f"https://t.me/{source}/{message.id}" if source and not source.isdigit() else ""
            for code in codes:
                digest = hashlib.sha256((source.lower() + ":" + code.upper()).encode()).hexdigest()
                if not save_scanned_code(digest, code, source, post_url, message.id):
                    continue
                body = ("🆕 PHÁT HIỆN CODE MỚI\n"
                        f"Kênh: @{source}\n"
                        f"Mã: <code>{html.escape(code)}</code>\n"
                        f"Nguồn: {post_url or 'Telegram'}\n"
                        "Trạng thái: Chưa xác minh hiệu lực")
                for chat_id in targets:
                    try:
                        await bot.send_message(chat_id=chat_id, text=body, parse_mode="HTML", disable_web_page_preview=True)
                    except Exception:
                        log.exception("Cannot send result to chat %s", chat_id)

        log.info("Scanner connected; monitoring %d channels.", len(entities))
        await client.run_until_disconnected()

    asyncio.run(worker())

def start_scanner_thread():
    t = threading.Thread(target=run_scanner, name="telegram-code-scanner", daemon=True)
    t.start()
    return t
