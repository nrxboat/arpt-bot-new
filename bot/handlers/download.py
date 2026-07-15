"""下载命令处理器。"""
import os
import re
import time
import logging
import asyncio
from telethon import events, Button
from services import aria2_client as a2
from services import rclone_client as rc
from config import DOWNLOAD_DIR, OWNER_ID

log = logging.getLogger("download")

MAGNET_RE = re.compile(r"magnet:\?xt=urn:[a-z0-9]+:[a-zA-Z0-9]{32,}", re.I)

_tasks: dict = {}
_pending_tgdown: set = set()


def register(bot):

    @bot.on(events.NewMessage)
    async def handler(event):
        text = (event.text or "").strip()
        sid = event.sender_id

        if sid in _pending_tgdown:
            if text == "/cancel_tgdown":
                _pending_tgdown.discard(sid)
                await event.reply("已取消等待。")
                return
            if event.media:
                _pending_tgdown.discard(sid)
                await _handle_tgdown(event.client, event)
                return
            await event.reply("请发送一个文件（文档/视频/图片/音频），或转发包含文件的消息。发送 /cancel_tgdown 取消。")
            return

        if not _ok(event):
            return

        if text == "/tgdown":
            _pending_tgdown.add(sid)
            await event.reply(
                "📤 请发送需要上传到网盘的文件。\n"
                "支持：文档、视频、图片、音频，以及转发消息中的文件。\n"
                "发送 /cancel_tgdown 可取消等待。"
            )
            return

        if text.startswith("/mirror "):
            await _dl(event, "upload")
            return
        if text.startswith("/mirrortg "):
            await _dl(event, "tg")
            return
        if text.startswith("/magnet "):
            args = text.split(maxsplit=1)
            uri = args[1].strip() if len(args) > 1 else ""
            if not MAGNET_RE.search(uri):
                await event.reply("无效的磁力链接。")
                return
            gid = a2.add_magnet(uri)
            await _start_monitor(event.client, event, gid, "upload")
            return
        if text == "/list":
            ds = a2.all_downloads()
            if not ds:
                await event.reply("当前无下载任务。")
                return
            lines = []
            for d in ds:
                pct = f"{d.progress:.1f}%" if d.total_length else "-"
                spd = a2.fmt_spd(d.download_speed) if d.status == "active" else d.status
                lines.append(f"`{d.gid[:7]}` [{d.status}] {pct} | {spd} | {d.name[:35]}")
            await event.reply("**下载列表:**\n" + "\n".join(lines[:20]))
            return
        if text.startswith("/cancel "):
            args = text.split(maxsplit=1)
            prefix = args[1].strip() if len(args) > 1 else ""
            if not prefix:
                await event.reply("用法: `/cancel <gid前缀>`")
                return
            for gid in list(_tasks):
                if gid.startswith(prefix):
                    a2.remove_gid(gid)
                    _tasks.pop(gid, None)
                    await event.reply(f"已取消 `{gid[:7]}`")
                    return
            await event.reply(f"未找到: `{prefix}`")
            return

        if text and MAGNET_RE.search(text):
            uri = MAGNET_RE.search(text).group()
            gid = a2.add_magnet(uri)
            await _start_monitor(event.client, event, gid, "upload")
            return

        if event.document and (
            event.document.mime_type == "application/x-bittorrent"
            or (event.file and event.file.name and event.file.name.endswith(".torrent"))
        ):
            fname = (event.file.name if event.file else None) or "torrent.torrent"
            path = os.path.join(DOWNLOAD_DIR, fname)
            await event.client.download_media(event, file=path)
            gid = a2.add_torrent(path)
            await _start_monitor(event.client, event, gid, "upload")
            return

    @bot.on(events.CallbackQuery)
    async def cb_handler(event):
        d = event.data.decode()
        if d.startswith("pause:"):
            a2.pause_gid(d.split(":", 1)[1])
            await event.answer("已暂停")
        elif d.startswith("resume:"):
            a2.resume_gid(d.split(":", 1)[1])
            await event.answer("已恢复")
        elif d.startswith("cancel:"):
            gid = d.split(":", 1)[1]
            a2.remove_gid(gid)
            _tasks.pop(gid, None)
            await event.answer("已取消")
            try:
                await event.delete()
            except Exception:
                pass


def _ok(event) -> bool:
    sid = str(event.sender_id)
    oid = str(OWNER_ID)
    return oid.startswith("-") or sid == oid


async def _dl(event, mode: str):
    args = event.text.split(maxsplit=1)
    if len(args) < 2:
        cmd = "mirror" if mode == "upload" else "mirrortg"
        await event.reply(f"用法: `/{cmd} <URL>`")
        return
    url = args[1].strip()
    gid = a2.add_url(url)
    await _start_monitor(event.client, event, gid, mode)


async def _start_monitor(bot, event, gid, mode):
    btn = [[Button.inline("暂停", f"pause:{gid}"), Button.inline("取消", f"cancel:{gid}")]]
    msg = await event.reply("📥 已添加任务，等待开始...", buttons=btn)
    _tasks[gid] = {"chat": event.chat_id, "msg": msg.id, "mode": mode}
    asyncio.create_task(_poll(bot, gid))


async def _poll(bot, gid: str):
    t = _tasks.get(gid)
    if not t:
        return
    cid, mid, mode = t["chat"], t["msg"], t["mode"]
    try:
        while True:
            d = a2.get(gid)
            if d is None:
                await bot.edit_message(cid, mid, "任务已被移除。")
                return
            if d.status in ("complete", "removed"):
                break
            if d.status == "error":
                await bot.edit_message(cid, mid, f"❌ 下载失败: {d.error_message or '未知'}")
                return
            pct = f"{d.progress:.1f}%" if d.total_length else "-"
            eta = a2.fmt_eta(d.eta) if d.eta else "-"
            bar = a2.pbar(d.completed_length, d.total_length)
            spd = a2.fmt_spd(d.download_speed) if d.status == "active" else f"[{d.status}]"
            text = (
                f"📥 **{d.name or '(无名称)'}**\n"
                f"状态: {d.status} | {pct}\n{bar}\n"
                f"速度: {spd} | 剩余: {eta}\n"
                f"大小: {a2.fmt(d.total_length)}"
            )
            try:
                await bot.edit_message(cid, mid, text)
            except Exception:
                pass
            await asyncio.sleep(2)
        d = a2.get(gid)
        name = d.name if d else "(未知)"
        if not d:
            await bot.edit_message(cid, mid, "任务已完成并被移除。")
            return
        if mode == "upload":
            path = d.files[0]["path"] if d.files else os.path.join(DOWNLOAD_DIR, name)
            await bot.edit_message(cid, mid, f"✅ 下载完成: **{name}**\n📤 正在上传...")
            try:
                jid = await rc.upload_file(path)
                await _track_upload(bot, cid, mid, jid, name)
                try:
                    os.remove(path)
                    log.info("已清理: %s", path)
                except Exception:
                    pass
            except Exception as e:
                log.exception("上传失败")
                await bot.edit_message(cid, mid, f"✅ 下载完成: **{name}**\n❌ 上传失败: {e}")
        elif mode == "tg":
            path = d.files[0]["path"] if d.files else os.path.join(DOWNLOAD_DIR, name)
            try:
                await bot.send_file(cid, path, caption=f"✅ {name}")
                await bot.edit_message(cid, mid, f"✅ 已发送: **{name}**")
                try:
                    os.remove(path)
                    log.info("已清理: %s", path)
                except Exception:
                    pass
            except Exception as e:
                log.exception("发送TG失败")
                await bot.edit_message(cid, mid, f"✅ 下载完成: **{name}**\n❌ 发送失败: {e}")
        else:
            await bot.edit_message(cid, mid, f"✅ 下载完成: **{name}**")
    except Exception:
        log.exception("_poll gid=%s", gid)
    finally:
        _tasks.pop(gid, None)


async def _track_upload(bot, chat_id, msg_id, jobid, name):
    try:
        await asyncio.sleep(1)
        finished_count = 0
        while True:
            prog = await rc.job_progress(jobid)
            if prog:
                finished_count = 0
                bar = a2.pbar(prog["bytes"], prog["size"])
                text = (
                    f"📤 **{name}**\n{bar}\n"
                    f"进度: {prog['pct']:.1f}% | {a2.fmt(prog['bytes'])}/{a2.fmt(prog['size'])}\n"
                    f"速度: {a2.fmt_spd(prog['speed'])} | 剩余: {a2.fmt_eta(prog['eta'])}"
                )
            else:
                finished_count += 1
                if finished_count >= 5:
                    break
                text = f"📤 上传中: **{name}**..."
            try:
                await bot.edit_message(chat_id, msg_id, text)
            except Exception:
                pass
            await asyncio.sleep(2)
        await bot.edit_message(chat_id, msg_id, f"✅ 上传完成: **{name}**")
    except Exception:
        log.exception("_track_upload jobid=%s", jobid)
        try:
            await bot.edit_message(chat_id, msg_id, f"❌ 上传失败: **{name}**")
        except Exception:
            pass


async def _handle_tgdown(bot, event):
    fname = None
    if event.file and event.file.name:
        fname = event.file.name
    elif hasattr(event.media, "document") and event.media.document:
        for attr in event.media.document.attributes:
            if hasattr(attr, "file_name") and attr.file_name:
                fname = attr.file_name
                break
    if not fname:
        ext_map = {"video": ".mp4", "photo": ".jpg", "audio": ".mp3", "voice": ".ogg", "sticker": ".webp"}
        for mtype, ext in ext_map.items():
            if getattr(event, mtype, None):
                fname = f"{mtype}_{int(time.time())}{ext}"
                break
    if not fname:
        fname = f"tgfile_{int(time.time())}"

    msg = await event.reply(f"📥 正在下载: **{fname}**...")
    last_ts = 0

    async def dl_progress(current, total):
        nonlocal last_ts
        now = time.time()
        if now - last_ts < 1.5:
            return
        last_ts = now
        bar = a2.pbar(current, total) if total else "▰▰▰▰▰▰▰▰▰▰"
        pct = f"{current/total*100:.1f}%" if total else "下载中..."
        txt = f"📥 下载中: **{fname}**\n{bar}\n{pct} | {a2.fmt(current)}" + (f"/{a2.fmt(total)}" if total else "")
        try:
            await msg.edit(txt)
        except Exception:
            pass

    dest_path = os.path.join(DOWNLOAD_DIR, fname)
    try:
        dl_path = await bot.download_media(event.message, file=dest_path, progress_callback=dl_progress)
    except Exception as e:
        log.exception("TG下载失败")
        await msg.edit(f"❌ 下载失败: {e}")
        return
    if dl_path is None:
        await msg.edit("❌ 下载失败: 无法获取文件。")
        return

    await msg.edit(f"📤 正在上传到网盘: **{fname}**...")
    try:
        jid = await rc.upload_file(dl_path)
        await _track_upload(bot, event.chat_id, msg.id, jid, fname)
        try:
            os.remove(dl_path)
            log.info("已清理: %s", dl_path)
        except Exception:
            pass
    except Exception as e:
        log.exception("上传失败")
        await msg.edit(f"✅ 下载完成: **{fname}**\n❌ 上传失败: {e}")
