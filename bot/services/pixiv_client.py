"""Pixiv API client with interactive OAuth flow via bot commands."""
import logging
import os
import zipfile
import hashlib
import secrets
import base64
import urllib.parse
import aiohttp
from pixivpy3 import AppPixivAPI
from config import DOWNLOAD_DIR, PIXIV_REFRESH_TOKEN

log = logging.getLogger("pixiv")
api = AppPixivAPI()
_authed = False

_client_id = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
_client_secret = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
_user_agent = "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)"

_cached_token: str | None = None
TOKEN_FILE = "/bot/pixiv_token.txt"


def _save_token(token: str):
    """Persist refresh_token to file so it survives bot restarts."""
    try:
        with open(TOKEN_FILE, "w") as f:
            f.write(token.strip())
        log.info("Saved refresh_token to %s", TOKEN_FILE)
    except Exception as e:
        log.warning("Failed to save token to %s: %s", TOKEN_FILE, e)


def _load_token() -> str | None:
    """Load persisted refresh_token from file."""
    try:
        if os.path.isfile(TOKEN_FILE):
            with open(TOKEN_FILE) as f:
                token = f.read().strip()
            if token:
                return token
    except Exception as e:
        log.warning("Failed to load token from %s: %s", TOKEN_FILE, e)
    return None


def ensure_auth():
    global _authed, _cached_token
    if _authed:
        return True

    # Try: memory cache -> file persistence -> env var
    token = _cached_token or _load_token() or (PIXIV_REFRESH_TOKEN or None)

    if not token:
        log.error("No refresh_token available. Run /pixivlogin or set PIXIV_REFRESH_TOKEN in .env")
        return False
    try:
        api.auth(refresh_token=token)
        _cached_token = token
        _authed = True
        return True
    except Exception as e:
        log.exception("Pixiv API auth failed")
        return False


def illust_detail(pid):
    if not ensure_auth():
        return None
    resp = api.illust_detail(pid)
    if resp.get("error"):
        return None
    return resp.get("illust")


def author_illusts(uid):
    if not ensure_auth():
        return ("", [])
    resp = api.user_detail(uid)
    user = resp.get("user", {})
    name = user.get("name", str(uid))
    resp2 = api.user_illusts(uid)
    if resp2.get("error"):
        return (name, [])
    return (name, resp2.get("illusts", []))


def illust_ranking(mode="day", date=None):
    if not ensure_auth():
        return []
    kwargs = {}
    if date:
        kwargs["date"] = date
    resp = api.illust_ranking(mode, **kwargs)
    if resp.get("error"):
        return []
    return resp.get("illusts", [])


def get_image_urls(illust):
    urls = []
    if illust.get("meta_pages"):
        for page in illust["meta_pages"]:
            url = page.get("image_urls", {}).get("original", "")
            if url:
                urls.append(url)
    elif illust.get("meta_single_page"):
        url = illust["meta_single_page"].get("original_image_url", "")
        if url:
            urls.append(url)
    if not urls:
        url = illust.get("image_urls", {}).get("original", "")
        if url:
            urls.append(url)
    return urls


async def download_images(urls, pid):
    out_dir = os.path.join(DOWNLOAD_DIR, "pixiv", str(pid))
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    headers = {"Referer": "https://www.pixiv.net/"}
    for i, url in enumerate(urls):
        ext = ".jpg"
        if url:
            ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
        fname = str(pid) + "_p" + str(i) + ext
        fpath = os.path.join(out_dir, fname)
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as r:
                r.raise_for_status()
                data = await r.read()
                with open(fpath, "wb") as f:
                    f.write(data)
        paths.append(fpath)
        log.info("Downloaded pixiv: %s (%d bytes)", fname, len(data))
    return paths


def make_zip(paths, pid):
    zip_path = os.path.join(DOWNLOAD_DIR, "pixiv", str(pid), str(pid) + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            zf.write(p, os.path.basename(p))
    log.info("Created ZIP: %s", zip_path)
    return zip_path