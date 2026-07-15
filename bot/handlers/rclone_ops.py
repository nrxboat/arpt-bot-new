"""Rclone 操作命令处理器。"""
import logging
import asyncio
from telethon import events
from services import rclone_client as rc
from services.aria2_client import fmt, fmt_spd, fmt_eta, pbar
from config import RCLONE_REMOTE, RCLONE_UPLOAD_DIR

log = logging.getLogger("rclone_ops")


def register(bot):

    @bot.on(events.NewMessage)
    async def handler(event):
        text = (event.text or "").strip()
        if not text.startswith("/"):
            return

        if text.startswith("/rclonecopy "):
            args = text.split(maxsplit=2)
            if len(args) < 3:
                await event.reply("用法: `/rclonecopy <src> <dst>`\n例: `/rclonecopy gd:films od:backup`")
                return
            src, dst = args[1], args[2]
            msg = await event.reply(f"📂 正在从 `{src}` 复制到 `{dst}` ...")
            jid = await rc.copy_remote(src, dst)
            await _track_rc_job(event.client, event.chat_id, msg.id, jid, f"远程复制: {src} -> {dst}")
            return

        if text.startswith("/rclonelsd"):
            args = text.split(maxsplit=1)
            path = args[1].strip() if len(args) > 1 else ""
            fs = f"{RCLONE_REMOTE}:{RCLONE_UPLOAD_DIR}/{path}".rstrip("/")
            try:
                dirs = await rc.list_dirs(f"{RCLONE_UPLOAD_DIR}/{path}".strip("/"))
                if not dirs:
                    await event.reply(f"`{fs}` 下无子目录。")
                    return
                text_out = f"**{fs}**\n" + "\n".join(f"📁 {d}" for d in dirs[:30])
                await event.reply(text_out)
            except Exception as e:
                await event.reply(f"❌ 列出失败: {e}")
            return

        if text.startswith("/rclonels"):
            args = text.split(maxsplit=1)
            path = args[1].strip() if len(args) > 1 else ""
            fs = f"{RCLONE_REMOTE}:{RCLONE_UPLOAD_DIR}/{path}".rstrip("/")
            try:
                items = await rc.list_files(f"{RCLONE_UPLOAD_DIR}/{path}".strip("/"))
                if not items:
                    await event.reply(f"`{fs}` 下无文件。")
                    return
                lines = []
                for item in items[:25]:
                    name = item.get("Name", "")
                    if item.get("IsDir"):
                        lines.append(f"📁 {name}")
                    else:
                        size = fmt(item.get("Size", 0))
                        lines.append(f"📄 {name}  ({size})")
                await event.reply(f"**{fs}**\n" + "\n".join(lines))
            except Exception as e:
                await event.reply(f"❌ 列出失败: {e}")
            return

        if text.startswith("/rclonecopyurl "):
            args = text.split(maxsplit=1)
            if len(args) < 2:
                await event.reply("用法: `/rclonecopyurl <URL>`")
                return
            url = args[1].strip()
            msg = await event.reply("📤 正在通过 rclone 直接上传...")
            jid = await rc.copy_url(url)
            await _track_rc_job(event.client, event.chat_id, msg.id, jid, f"copyurl: {url[:50]}")
            return


async def _track_rc_job(bot, chat_id, msg_id, jobid, title):
    try:
        while not await rc.job_finished(jobid):
            prog = await rc.job_progress(jobid)
            if prog:
                bar = pbar(prog["bytes"], prog["size"])
                text = (
                    f"📤 **{title}**\n{bar}\n"
                    f"进度: {prog['pct']:.1f}% | {fmt(prog['bytes'])}/{fmt(prog['size'])}\n"
                    f"速度: {fmt_spd(prog['speed'])} | 剩余: {fmt_eta(prog['eta'])}"
                )
            else:
                text = f"📤 **{title}**\n准备传输中..."
            try:
                await bot.edit_message(chat_id, msg_id, text)
            except Exception:
                pass
            await asyncio.sleep(2)
        await bot.edit_message(chat_id, msg_id, f"✅ 上传完成: **{title}**")
    except Exception:
        log.exception("track_rc jobid=%s", jobid)
        try:
            await bot.edit_message(chat_id, msg_id, f"❌ 上传失败: **{title}**")
        except Exception:
            pass
