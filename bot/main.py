"""ARPT-Bot 主入口。"""
import asyncio
import logging
import os
import shutil
import sys
import threading

from telethon import TelegramClient

from config import API_ID, API_HASH, BOT_TOKEN, DOWNLOAD_DIR, log_config
from services import aria2_client as a2
from handlers import download, rclone_ops, status, pixiv, jmcomic
# Clear all handlers (including loguru) and re-init
import logging as _logging
_logging.root.handlers.clear()
_logging.basicConfig(
    level=_logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# Fix loguru interference with standard logging
for h in logging.root.handlers[:]:
    try:
        h.formatter.format(logging.LogRecord('t', logging.INFO, '', 0, '', (), None))
    except (KeyError, ValueError):
        logging.root.removeHandler(h)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")


async def main():
    log_config()

    # Clean up leftover downloads from previous runs
    for sub in ("jmcomic", "jmcomic_tmp"):
        pth = os.path.join(DOWNLOAD_DIR, sub)
        if os.path.isdir(pth):
            shutil.rmtree(pth)
            log.info("Cleaned up leftover: %s", pth)

    bot = TelegramClient("arpt_session", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)

    me = await bot.get_me()
    log.info("Bot 身份: @%s (ID: %d)", me.username, me.id)

    download.register(bot)
    rclone_ops.register(bot)
    status.register(bot)
    pixiv.register(bot)
    jmcomic.register(bot)

    loop = asyncio.get_event_loop()
    a2.set_loop(loop)

    threading.Thread(target=a2.listen, daemon=True, name="aria2-listener").start()

    log.info("ARPT-Bot 已上线")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("收到退出信号")
    except Exception:
        log.exception("Bot 异常退出")
        sys.exit(1)
