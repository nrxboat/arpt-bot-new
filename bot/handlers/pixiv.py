"""Pixiv command handlers: /pixivpid, /pixivauthor, /pixivtop, /pixivlogin, /pixivcode."""
import os
import logging
from telethon import events, Button
from services import pixiv_client as px
from services import rclone_client as rc
from config import DOWNLOAD_DIR, OWNER_ID

log = logging.getLogger("pixiv")


def register(bot):
    @bot.on(events.NewMessage)
    async def handler(event):
        text = (event.text or "").strip()
        if not text.startswith("/") or not _ok(event):
            return
        if text.startswith("/pixivpid "):
            await _pid_cmd(event, text)
            return
        if text.startswith("/pixivauthor "):
            await _author_cmd(event, text)
            return
        if text.startswith("/pixivtop"):
            await _top_cmd(event, text)
            return
        if text == "/pixivtoken" or text.startswith("/pixivtoken@"):
            await _pixivtoken_cmd(event)
            return
        if text.startswith("/pixivtoken "):
            await _pixivtoken_set_cmd(event, text)
            return

    @bot.on(events.CallbackQuery)
    async def cb(event):
        d = event.data.decode()
        if d.startswith("pxdl:"):
            parts = d.split(":")
            pid = int(parts[1])
            mode = parts[2] if len(parts) > 2 else "tg"
            await event.answer("Downloading...")
            await _download_illust(event, pid, mode)


def _ok(event):
    sid = str(event.sender_id)
    oid = str(OWNER_ID)
    return oid.startswith("-") or sid == oid


async def _pixivtoken_cmd(event):
    """Show instructions for getting a Pixiv refresh_token."""
    msg = (
        "**获取 Pixiv refresh_token**\n\n"
        "使用 [pixiv_auth.py](https://gist.githubusercontent.com/ZipFile/c9ebedb224406f4f11845ab700124362/raw/pixiv_auth.py) 脚本（[GitHub Gist](https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362)）：\n\n"
        "1. 下载脚本，安装依赖：`pip install requests`\n"
        "2. 运行：`python pixiv_auth.py login`\n"
        "  浏览器会自动打开 Pixiv 登录页\n"
        "3. 按 F12 打开开发者工具，切换到 **Network（网络）** 标签\n"
        "4. 勾选 **Preserve log（保留日志）**\n"
        "5. 在过滤框中输入：`callback?`\n"
        "6. 正常登录 Pixiv\n"
        "7. 登录成功后会看到一条请求：\n"
        "   `callback?state=...&code=...`\n"
        "   复制 `code` 参数的值，粘贴到终端中回车\n\n"
        "> 注意：`code` 有效期极短，请在步骤 6 和 7 之间尽快操作，否则需从头重试。\n\n"
        "成功后终端会输出 `access_token` 和 `refresh_token`。\n"
        "复制 `refresh_token` 的值，在此对话中发送：\n"
        "`/pixivtoken <粘贴refresh_token>`\n\n"
        "**刷新已过期的 token：**\n"
        "`python pixiv_auth.py refresh <旧的refresh_token>`"
    )
    await event.reply(msg, link_preview=False)


async def _pixivtoken_set_cmd(event, text):
    """Save a user-provided refresh_token."""
    args = text.split(maxsplit=1)
    if len(args) < 2:
        await event.reply("Usage: /pixivtoken <refresh_token>")
        return
    token = args[1].strip()
    if len(token) < 10:
        await event.reply("That doesn't look like a valid refresh_token.")
        return
    from services.pixiv_client import _save_token, _cached_token
    global _cached_token  # noqa
    _cached_token = token
    _save_token(token)
    await event.reply(
        "**Pixiv refresh_token saved!**\n\n"
        "The token has been saved and will persist across restarts.\n"
        "Try using Pixiv commands like /pixivpid 123456."
    )

async def _pid_cmd(event, text):
    args = text.split()
    if len(args) < 2:
        await event.reply("Usage: /pixivpid <illust_id>")
        return
    try:
        pid = int(args[1])
    except ValueError:
        await event.reply("Invalid illustration ID.")
        return
    msg = await event.reply("Fetching pixiv illustration #" + str(pid) + "...")
    illust = px.illust_detail(pid)
    if not illust:
        await msg.edit("Not found or not logged in. Set PIXIV_REFRESH_TOKEN in .env")
        return
    title = illust.get("title", "Untitled")
    author = illust.get("user", {}).get("name", "Unknown")
    urls = px.get_image_urls(illust)
    page_count = len(urls)
    info = "**" + title + "**\nAuthor: " + author + "\nPages: " + str(page_count)
    btns = [
        [Button.inline("Send to TG", "pxdl:" + str(pid) + ":tg"),
         Button.inline("Upload to cloud", "pxdl:" + str(pid) + ":upload")]
    ]
    await msg.edit(info, buttons=btns)


async def _author_cmd(event, text):
    args = text.split()
    if len(args) < 2:
        await event.reply("Usage: /pixivauthor <user_id>")
        return
    try:
        uid = int(args[1])
    except ValueError:
        await event.reply("Invalid user ID.")
        return
    msg = await event.reply("Fetching author works...")
    name, illusts = px.author_illusts(uid)
    if not name:
        await msg.edit("Author not found or not logged in.")
        return
    count = len(illusts)
    lines = ["**" + name + "** (ID: " + str(uid) + ")", "Total works: " + str(count), ""]
    for ill in illusts[:5]:
        pid = ill["id"]
        t = ill.get("title", "Untitled")
        pages = len(ill.get("meta_pages", []) or [1])
        lines.append("" + str(pid) + " " + t + " (" + str(pages) + "p)")
    text_out = "\n".join(lines)
    if count > 5:
        text_out += "\n...and " + str(count - 5) + " more"
    btns = []
    for ill in illusts[:10]:
        pid = ill["id"]
        btns.append([Button.inline(
            ill.get("title", str(pid))[:40],
            "pxdl:" + str(pid) + ":tg"
        )])
    await msg.edit(text_out, buttons=btns)


async def _top_cmd(event, text):
    args = text.split()
    mode = "day"
    valid_modes = ["day", "week", "month", "day_male", "day_female",
                   "week_original", "week_rookie", "day_manga"]
    for a in args[1:]:
        if a in valid_modes:
            mode = a
            break
    msg = await event.reply("Fetching " + mode + " ranking...")
    illusts = px.illust_ranking(mode)
    if not illusts:
        await msg.edit("Failed to fetch ranking.")
        return
    lines = ["Pixiv " + mode + " ranking:"]
    btns = []
    row = []
    for i, ill in enumerate(illusts[:30]):
        pid = ill["id"]
        t = ill.get("title", "?")[:35]
        lines.append(str(i+1) + ". " + str(pid) + " " + t)
        row.append(Button.inline(str(i+1), "pxdl:" + str(pid) + ":tg"))
        if len(row) == 5:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    await msg.edit("\n".join(lines[:20]), buttons=btns)


async def _download_illust(event, pid, mode):
    illust = px.illust_detail(pid)
    if not illust:
        await event.edit("Illustration not found.")
        return
    urls = px.get_image_urls(illust)
    if not urls:
        await event.edit("No images found.")
        return
    title = illust.get("title", str(pid))
    chat_id = event.chat_id
    msg_id = event.message_id

    await event.client.edit_message(chat_id, msg_id, "Downloading " + title + " (" + str(len(urls)) + " pages)...")

    try:
        paths = await px.download_images(urls, pid)
    except Exception as e:
        log.exception("Pixiv download failed")
        await event.client.edit_message(chat_id, msg_id, "Download failed: " + str(e))
        return

    if mode == "upload":
        dir_path = os.path.join(DOWNLOAD_DIR, "pixiv", str(pid))
        await event.client.edit_message(chat_id, msg_id, "Uploading " + title + " to cloud...")
        try:
            jid = await rc.upload_dir(dir_path, "pixiv/" + str(pid))
            from handlers.download import _track_upload as _tu
            await _tu(event.client, chat_id, msg_id, jid, title)
            for p in paths:
                try:
                    os.remove(p)
                except Exception:
                    pass
            try:
                os.rmdir(dir_path)
            except Exception:
                pass
        except Exception as e:
            log.exception("Pixiv upload failed")
            await event.client.edit_message(chat_id, msg_id, "Upload failed: " + str(e))
            return
    else:
        if len(paths) == 1:
            await event.client.edit_message(chat_id, msg_id, "Sending image...")
            await event.client.send_file(chat_id, paths[0], caption=title)
            await event.client.edit_message(chat_id, msg_id, "Sent: **" + title + "**")
        else:
            zip_path = px.make_zip(paths, pid)
            await event.client.edit_message(chat_id, msg_id, "Sending album...")
            await event.client.send_file(chat_id, zip_path, caption=title + " (" + str(len(paths)) + " pages)")
            await event.client.edit_message(chat_id, msg_id, "Sent: **" + title + "** (" + str(len(paths)) + " pages)")
            try:
                os.remove(zip_path)
            except Exception:
                pass
        for p in paths:
            try:
                os.remove(p)
            except Exception:
                pass
        dir_path = os.path.join(DOWNLOAD_DIR, "pixiv", str(pid))
        try:
            os.rmdir(dir_path)
        except Exception:
            pass