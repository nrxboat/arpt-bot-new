"""JMComic command handlers: /jm, /jms, /jmi

Commands:
  /jm <album_id>    — Show album info and action buttons (Telegraph/Upload/TG)
  /jms <query>      — Search JMComic albums by name
  /jmi <album_id>   — Show album cover image + info + action buttons

Supports three output modes:
  - Telegraph: download -> upload images to Telegraph -> send page URL
  - Upload: download -> rclone upload to cloud -> track progress
  - TG: download -> create ZIP -> send file to Telegram
"""
import os
import asyncio
import logging
import time
import requests as _requests
from telethon import events, Button
from services import rclone_client as rc
from services.jmcomic_client import (
    fetch_album_info,
    download_album,
    download_cover,
    search_albums,
    list_album_images,
    make_zip,
    cleanup_dir,
)
from config import OWNER_ID, DOWNLOAD_DIR

log = logging.getLogger("jmcomic")

JM_TMP_DIR = os.path.join(DOWNLOAD_DIR, "jmcomic_tmp")

# Search cache: cache_id -> (query, page)
_search_cache: dict[str, tuple] = {}
_search_cache_expiry: dict[str, float] = {}
CACHE_TTL = 300  # 5 minutes


def register(bot):
    @bot.on(events.NewMessage)
    async def handler(event):
        text = (event.text or "").strip()
        if not text.startswith("/") or not _ok(event):
            return
        if text.startswith("/jm "):
            await _album_cmd(event, text)
            return
        if text.startswith("/jms "):
            await _search_cmd(event, text)
            return
        if text == "/jms" or text.startswith("/jms@"):
            await event.reply("Usage: /jms <comic_name>\nExample: /jms girl")
            return
        if text.startswith("/jmi "):
            await _info_cmd(event, text)
            return

    @bot.on(events.CallbackQuery)
    async def cb(event):
        d = event.data.decode()
        if d == "jmcnone":
            await event.answer()
            return
        if d.startswith("jmc:"):
            parts = d.split(":", 2)
            if len(parts) < 3:
                await event.answer("Invalid callback")
                return
            album_id = parts[1]
            mode = parts[2]
            await event.answer("Processing...")
            await _process_album(event, album_id, mode)
        # Search page navigation
        if d.startswith("jmsp:"):
            parts = d.split(":", 2)
            if len(parts) < 3:
                await event.answer("Invalid callback")
                return
            cache_id = parts[1]
            page = int(parts[2])
            await event.answer()
            await _show_search_page(event, cache_id, page)
        # Search result selection
        if d.startswith("jmss:"):
            album_id = d.split(":", 1)[1]
            await event.answer("Fetching album...")
            await _show_album_cover(event, album_id)


def _ok(event):
    sid = str(event.sender_id)
    oid = str(OWNER_ID)
    return oid.startswith("-") or sid == oid


# ---------------------------------------------------------------------------
# /jm <album_id>  —  Show album info + action buttons
# ---------------------------------------------------------------------------
async def _album_cmd(event, text):
    args = text.split()
    if len(args) < 2:
        await event.reply(
            "Usage: /jm <album_id>\n"
            "Example: /jm 123456"
        )
        return
    album_id = args[1].strip()
    if not album_id.isdigit():
        await event.reply("Album ID must be a number.")
        return

    msg = await event.reply(f"Fetching JMComic album #{album_id}...")

    try:
        detail = await asyncio.get_event_loop().run_in_executor(
            None, fetch_album_info, album_id
        )
    except Exception as e:
        log.exception("Failed to fetch album info")
        await msg.edit(f"Failed to fetch album #{album_id}.\nError: {e}")
        return

    title = detail.title or "Untitled"
    author = detail.author or "Unknown"
    page_count = getattr(detail, "page_count", "?")

    info = (
        f"**{title}**\n"
        f"Author: {author}\n"
        f"Pages: {page_count}\n"
        f"Album ID: {album_id}\n\n"
        "Choose an action:"
    )
    btns = _build_action_buttons(album_id)
    await msg.edit(info, buttons=btns)


# ---------------------------------------------------------------------------
# /jms <query>  —  Search JMComic albums
# ---------------------------------------------------------------------------
async def _search_cmd(event, text):
    query = text.split(maxsplit=1)[1].strip()
    if not query:
        await event.reply("Usage: /jms <comic_name>")
        return

    msg = await event.reply(f"Searching: {query}...")
    await _show_search_page(event, None, 1, msg=msg, query=query)


async def _show_search_page(event, cache_id, page, msg=None, query=None):
    """Display a page of search results with inline buttons."""
    # Resolve query from cache if needed
    if query is None and cache_id is not None:
        cached = _search_cache.get(cache_id)
        if cached is None:
            if msg:
                await msg.edit("Search expired, please search again.")
            else:
                await event.edit("Search expired, please search again.")
            return
        query = cached[0]

    try:
        items, total_pages, current_page = await asyncio.get_event_loop().run_in_executor(
            None, search_albums, query, page
        )
    except Exception as e:
        log.exception("Search failed")
        err_text = f"Search failed: {e}"
        if msg:
            await msg.edit(err_text)
        else:
            await event.edit(err_text)
        return

    if not items:
        text = f"No results found for: {query}"
        if msg:
            await msg.edit(text)
        else:
            await event.edit(text)
        return

    # Cache the query for pagination
    cache_key = cache_id or str(int(time.time() * 1000))[-10:]
    _search_cache[cache_key] = (query, page)
    _search_cache_expiry[cache_key] = time.time() + CACHE_TTL

    lines = [f"Search results for: **{query}** (Page {page}/{total_pages})", ""]
    btns = []

    for aid, title in items[:8]:
        t = (title or "?")[:50]
        lines.append(f"  {aid} - {t}")
        btns.append([Button.inline(f"[{aid}] {t[:35]}", f"jmss:{aid}")])

    # Pagination buttons
    nav_btns = []
    if page > 1:
        nav_btns.append(
            Button.inline("<< Prev", f"jmsp:{cache_key}:{page - 1}")
        )
    nav_btns.append(Button.inline(f"{page}/{total_pages}", "jmcnone"))
    if page < total_pages:
        nav_btns.append(
            Button.inline("Next >>", f"jmsp:{cache_key}:{page + 1}")
        )
    btns.append(nav_btns)

    result_text = "\n".join(lines)
    if msg:
        await msg.edit(result_text, buttons=btns)
    else:
        await event.edit(result_text, buttons=btns)


# ---------------------------------------------------------------------------
# /jmi <album_id>  —  Show cover image + album info + action buttons
# ---------------------------------------------------------------------------
async def _info_cmd(event, text):
    args = text.split()
    if len(args) < 2:
        await event.reply(
            "Usage: /jmi <album_id>\n"
            "Example: /jmi 123456"
        )
        return
    album_id = args[1].strip()
    if not album_id.isdigit():
        await event.reply("Album ID must be a number.")
        return

    await _show_album_cover(event, album_id)


async def _show_album_cover(event, album_id):
    """Fetch album info + download cover + send as image with buttons."""
    chat_id = event.chat_id

    msg = await event.reply(f"Fetching album #{album_id}...")

    try:
        detail = await asyncio.get_event_loop().run_in_executor(
            None, fetch_album_info, album_id
        )
    except Exception as e:
        log.exception("Failed to fetch album info")
        await msg.edit(f"Failed to fetch album #{album_id}.\nError: {e}")
        return

    title = detail.title or "Untitled"
    author = detail.author or "Unknown"
    page_count = getattr(detail, "page_count", "?")

    caption = (
        f"**{title}**\n"
        f"Author: {author}\n"
        f"Pages: {page_count}\n"
        f"Album ID: {album_id}"
    )
    btns = _build_action_buttons(album_id)

    # Download cover
    os.makedirs(JM_TMP_DIR, exist_ok=True)
    cover_path = os.path.join(JM_TMP_DIR, f"{album_id}.jpg")

    try:
        await asyncio.get_event_loop().run_in_executor(
            None, download_cover, album_id, cover_path
        )
    except Exception as e:
        log.warning("Cover download failed: %s", e)
        # Still show info even without cover
        await msg.edit(caption, buttons=btns)
        return

    # Send the cover as a new message with info + buttons
    try:
        await event.client.delete_messages(chat_id, msg)
    except Exception:
        pass

    try:
        await event.client.send_file(
            chat_id, cover_path,
            caption=caption,
            buttons=btns,
        )
    except Exception as e:
        log.warning("Failed to send cover as image: %s", e)
        # Fallback: send text
        await event.reply(caption, buttons=btns)
    finally:
        try:
            os.remove(cover_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _build_action_buttons(album_id: str):
    """Build the standard action button row for an album."""
    return [
        [
            Button.inline("Send as Album", f"jmc:{album_id}:album"),
            Button.inline("Upload to Cloud", f"jmc:{album_id}:upload"),
        ],
        [
            Button.inline("Send ZIP to TG", f"jmc:{album_id}:tg"),
        ],
    ]











async def _dump_cache():
    """Periodically clean expired cache entries."""
    now = time.time()
    expired = [k for k, v in _search_cache_expiry.items() if v < now]
    for k in expired:
        _search_cache.pop(k, None)
        _search_cache_expiry.pop(k, None)


# ---------------------------------------------------------------------------
# /jm <id> callback processing: download -> tele / upload / tg
# ---------------------------------------------------------------------------
async def _process_album(event, album_id: str, mode: str):
    """Download album, then process according to mode."""
    chat_id = event.chat_id
    msg_id = event.message_id
    album_dir = None

    try:
        await event.client.edit_message(
            chat_id, msg_id, f"Downloading album #{album_id}..."
        )

        # Start download with progress updates
        loop = asyncio.get_event_loop()
        from services.jmcomic_client import JMCOMIC_DIR
        dl_task = loop.run_in_executor(None, download_album, album_id)
        album_dir_expected = os.path.join(JMCOMIC_DIR, str(album_id))
        last_count = 0
        while not dl_task.done():
            try:
                if os.path.isdir(album_dir_expected):
                    count = len(os.listdir(album_dir_expected))
                    if count != last_count:
                        last_count = count
                        await event.client.edit_message(
                            chat_id, msg_id,
                            f"Downloading album #{album_id} ({count} files)..."
                        )
                await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(2)
        album_dir, detail = dl_task.result()
        title = detail.title or f"JMComic #{album_id}"

        # Verify images were actually downloaded
        images = list_album_images(album_dir)
        if not images:
            await event.client.edit_message(
                chat_id, msg_id,
                f"Download complete but no images found in {album_dir}."
            )
            return

        if mode == "album":
            await _send_tg_album(event, chat_id, msg_id, album_dir, title, len(images), album_id)
        elif mode == "upload":
            author = detail.author or ""
            await _upload_to_cloud(event, chat_id, msg_id, album_dir, title, album_id, author)
        elif mode == "tg":
            await _send_zip_tg(event, chat_id, msg_id, album_dir, title, album_id)
        else:
            await event.client.edit_message(
                chat_id, msg_id, f"Unknown mode: {mode}"
            )

    except Exception as e:
        log.exception("JMComic processing failed")
        try:
            await event.client.edit_message(
                chat_id, msg_id, f"Failed: {e}"
            )
        except Exception:
            pass
    finally:
        if album_dir:
            cleanup_dir(album_dir)




def _convert_webp(filepath):
    """Convert .webp to .jpg if needed. Returns (path_to_send, is_temp)."""
    if not filepath.lower().endswith(".webp"):
        return filepath, False
    try:
        from PIL import Image
        outpath = filepath.rsplit(".", 1)[0] + ".jpg"
        img = Image.open(filepath).convert("RGB")
        img.save(outpath, "JPEG", quality=85)
        return outpath, True
    except Exception:
        return filepath, False


async def _send_tg_album(event, chat_id, msg_id, album_dir, title, count, album_id):
    """Download -> split into media groups -> send to Telegram as album."""
    images = list_album_images(album_dir)
    total = len(images)

    await event.client.edit_message(
        chat_id, msg_id,
        f"Sending {total} images as album..."
    )

    # Send in batches of 10 (Telegram album limit)
    sent = 0
    failed = 0
    batch_size = 10
    first_batch = True

    for start in range(0, total, batch_size):
        batch_raw = images[start:start + batch_size]
        batch = []
        temp_files = []
        for fp in batch_raw:
            send_path, is_temp = _convert_webp(fp)
            batch.append(send_path)
            if is_temp:
                temp_files.append(send_path)
        try:
            caption = f"**{title}**\nAlbum ID: {album_id}\nPages: {start+1}-{min(start+batch_size, total)}/{total}" if first_batch else ""
            await event.client.send_file(
                chat_id,
                batch,
                caption=caption,
            )
            sent += len(batch)
            for tf in temp_files:
                try:
                    os.remove(tf)
                except Exception:
                    pass
            first_batch = False
            if start + batch_size < total:
                await asyncio.sleep(1)
        except Exception as e:
            log.warning("Failed to send batch starting at image %d: %s", start + 1, e)
            failed += len(batch)

    if failed > 0:
        await event.client.edit_message(
            chat_id, msg_id,
            f"Sent **{title}**\nImages: {sent}/{total}\nFailed: {failed}"
        )
    else:
        await event.client.edit_message(
            chat_id, msg_id,
            f"Sent: **{title}** ({sent} images)"
        )
async def _upload_to_cloud(event, chat_id, msg_id, album_dir, title, album_id, author):
    """Download -> zip -> rclone upload to cloud -> track progress."""
    import re as _re

    # Sanitize filename: remove illegal chars
    safe_title = _re.sub(r'[\\/*?:"<>|]', '', (title or '').strip())[:50]
    safe_author = _re.sub(r'[\\/*?:"<>|]', '', (author or '').strip())[:30]
    zip_name = f"jmid_{album_id}_{safe_title}_{safe_author}.zip"

    await event.client.edit_message(
        chat_id, msg_id,
        f"Creating ZIP: **{zip_name}**..."
    )

    try:
        zip_path = await asyncio.get_event_loop().run_in_executor(
            None, make_zip, album_dir, os.path.join(os.path.dirname(album_dir), zip_name)
        )
    except Exception as e:
        log.exception("ZIP creation failed")
        await event.client.edit_message(chat_id, msg_id, f"ZIP creation failed: {e}")
        return

    await event.client.edit_message(
        chat_id, msg_id,
        f"Uploading to cloud: **{zip_name}**..."
    )

    try:
        jid = await rc.upload_file(zip_path, "jmcomic")
    except Exception as e:
        log.exception("rclone upload start failed")
        await event.client.edit_message(chat_id, msg_id, f"Upload failed to start: {e}")
        try:
            os.remove(zip_path)
        except Exception:
            pass
        return

    from handlers.download import _track_upload
    await _track_upload(event.client, chat_id, msg_id, jid, zip_name)

    try:
        os.remove(zip_path)
    except Exception:
        pass

async def _send_zip_tg(event, chat_id, msg_id, album_dir, title, album_id):
    """Download -> ZIP -> send file to Telegram."""
    await event.client.edit_message(
        chat_id, msg_id,
        f"Creating ZIP: **{title}**..."
    )

    zip_path = await asyncio.get_event_loop().run_in_executor(
        None, make_zip, album_dir
    )

    images = list_album_images(album_dir)
    total = len(images)

    await event.client.edit_message(
        chat_id, msg_id,
        f"Sending ZIP: **{title}**..."
    )

    try:
        await event.client.send_file(
            chat_id, zip_path,
            caption=f"{title} ({total} pages)"
        )
        await event.client.edit_message(
            chat_id, msg_id,
            f"Sent: **{title}** ({total} pages)"
        )
    except Exception as e:
        log.exception("Failed to send ZIP to TG")
        await event.client.edit_message(
            chat_id, msg_id,
            f"Downloaded but failed to send: {e}"
        )
    finally:
        try:
            os.remove(zip_path)
        except Exception:
            pass