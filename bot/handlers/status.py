"""状态 / 帮助命令处理器。"""
import os
import time
import logging
import datetime
from telethon import events
from config import (
    OWNER_ID, RCLONE_REMOTE, RCLONE_UPLOAD_DIR,
    DOWNLOAD_DIR, ERROR_USER_INFO,
)

log = logging.getLogger("status")
_start_time = time.time()


def register(bot):

    @bot.on(events.NewMessage)
    async def all_handler(event):
        text = (event.text or "").strip()
        if not text.startswith("/") or not _ok(event):
            return

        if text == "/start" or text.startswith("/start@"):
            uptime = str(datetime.timedelta(seconds=int(time.time() - _start_time)))
            disk = _disk_usage(DOWNLOAD_DIR)
            await event.reply(
                f"✅ **ARPT-Bot 运行中**\n"
                f"运行时间: `{uptime}`\n"
                f"磁盘剩余: `{disk}`\n"
                f"Rclone: `{RCLONE_REMOTE}:{RCLONE_UPLOAD_DIR}`"
            )
            return

        if text == "/help" or text.startswith("/help@"):
            await event.reply("""**ARPT-Bot 命令列表**

📥 **下载**
`/mirror <URL>` — 下载直链并上传网盘
`/mirrortg <URL>` — 下载直链并发送到 TG
`/magnet <链接>` — 磁力下载并上传
`/tgdown` — 发送/转发 TG 文件，下载并上传网盘
`/list` — 查看下载列表
`/cancel <gid>` — 取消下载

📂 **网盘**
`/rclonecopy <src> <dst>` — 盘间复制
`/rclonelsd [路径]` — 列出目录
`/rclonels [路径]` — 列出文件
`/rclonecopyurl <URL>` — 直链上传（不走本地）

📊 **状态**
`/start` — 查看 Bot 状态
`/help` — 显示本帮助

💡 直接发送磁力链接或 .torrent 文件也会自动下载。""")


def _ok(event) -> bool:
    sid = str(event.sender_id)
    oid = str(OWNER_ID)
    return oid.startswith("-") or sid == oid


def _disk_usage(path: str) -> str:
    try:
        stat = os.statvfs(path)
        free = stat.f_frsize * stat.f_bavail
        for u in ("B", "KB", "MB", "GB", "TB"):
            if free < 1024:
                return f"{free:.1f} {u}"
            free /= 1024
        return f"{free:.1f} PB"
    except Exception:
        return "未知"
