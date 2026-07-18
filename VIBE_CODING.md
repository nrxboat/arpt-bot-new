# ARPT-Bot-New — Vibe Coding Handoff Doc

## Project Overview

Telegram download bot that integrates Aria2 + Rclone for downloading files and uploading to cloud storage. Multi-container Docker Compose architecture. Core features working, Pixiv integration partially done.

**GitHub:** https://github.com/nrxboat/arpt-bot-new

## Architecture

```
4 Docker containers (docker-compose):
  arpt-aria2   — p3terx/aria2-pro, RPC on :6800, BT on :6888
  arpt-rclone  — rclone/rclone in RC mode, API on :5572
  arpt-ariang  — nginx:alpine serving AriaNg static files on :80 (host :8080)
  arpt-bot     — Python 3.11 + Telethon, mounts ./bot:/bot (live code)

Shared volume: arpt-downloads -> /downloads
All containers share /downloads for aria2 -> rclone pipeline.
```

## File Map

```
arpt-bot/
  docker-compose.yml     — 4 services, shared downloads volume
  .env.example           — env var template (needs PIXIV_REFRESH_TOKEN)
  VIBE_CODING.md         — this file
  README.md              — user-facing docs
  aria2/
    aria2.conf           — Aria2 config (P3TERX-based, rpc-secret injected)
  rclone/
    rclone.conf          — user rclone config (gitignored, mount rw for OAuth refresh)
  nginx/
    default.conf         — nginx config (serves AriaNg, proxies /jsonrpc to aria2:6800)
    aria-ng-1.3.8/       — AriaNg static files (v1.3.8, downloaded at build)
      init.html          — auto-config page (sets localStorage, redirects to index.html)
  bot/
    Dockerfile           — Python 3.11-slim + ffmpeg + Chromium system deps
    requirements.txt     — telethon, aria2p, aiohttp, psutil, pixivpy3, pillow
    config.py            — env var loader
    main.py              — entry point: creates Telethon client, registers handlers
    handlers/
      status.py          — /start, /help
      download.py        — /mirror, /mirrortg, /magnet, /tgdown, /list, /cancel
                           auto-detects magnet links + .torrent files
                           inline buttons for pause/cancel
                           _poll() monitors aria2 download progress
                           _track_upload() monitors rclone upload progress
                           cleanup: os.remove() after upload/send
      rclone_ops.py      — /rclonecopy, /rclonelsd, /rclonels, /rclonecopyurl
      pixiv.py           — /pixivpid, /pixivauthor, /pixivtop, /pixivtoken
    services/
      aria2_client.py    — aria2p wrapper, threaded notification listener
      rclone_client.py   — aiohttp RC API client (upload_file, list_dirs, job_progress, etc.)
      pixiv_client.py    — pixivpy3 wrapper, refresh_token auth, persistence
```

## Key Technical Details

### Handler Pattern (IMPORTANT)
Telethon 1.44 `@bot.on(events.NewMessage(pattern=r"..."))` DOES NOT WORK.
All handlers use text-based checks inside the function body:

```python
@bot.on(events.NewMessage)
async def handler(event):
    text = (event.text or "").strip()
    if text.startswith("/mirror "):
        ...
```

Callback queries still use `@bot.on(events.CallbackQuery)` normally.

### Encoding Rules (CRITICAL)
PowerShell on Windows causes UTF-8 corruption. Follow these rules strictly:

- NEVER use `Set-Content -Encoding UTF8` — adds BOM, breaks Python imports
- NEVER use `Get-Content | -replace | Set-Content` — corrupts multi-byte chars
- ONLY use this pattern for writing files:

```powershell
$utf8 = New-Object System.Text.UTF8Encoding $false  # NO BOM
[System.IO.File]::WriteAllText($path, @"
...file content...
"@, $utf8)
```

- All Python source files now use English docstrings to avoid encoding issues
- When running `docker compose up --build`, the container bind mount may lock files on Windows. If `Set-Content` fails with "access denied", run `docker compose down` first.

### Rclone RC API Caveats
- `operations/copyfile` requires `dstRemote` to be non-empty (bug: "cant use empty string as a path")
- `upload_file()` properly splits path into `srcFs` (directory) and `srcRemote` (filename)
- `job/status` RC endpoint is BROKEN in current rclone image — using `core/stats?group=job/{id}` instead
- Upload progress tracking: wait 1s before first poll, require 5 consecutive empty polls to confirm done

### Docker Compose Notes
- rclone config mount MUST be read-write (`:ro` removed) — rclone needs to save refreshed OAuth tokens
- nginx config mount also read-write — nginx entrypoint tries to modify it
- `depends_on` without `condition: service_healthy` (was causing startup failures)
- Bot source mounted as `./bot:/bot` for live code updates (no rebuild needed for .py changes)

## Current Problems

### 1. Dockerfile Chromium Deps
The Dockerfile installs ~250 system packages for Chromium/Playwright support (leftover from pixiv_token_fetcher experiment). These are NOT needed for pixivpy3-only usage. Can be removed to reduce image size.

### 2. Duplicate Handler Registrations
`status.py` and `download.py` and `rclone_ops.py` and `pixiv.py` each register their own `@bot.on(events.NewMessage)` handler. All use text-based checks (`if text.startswith(...)`) and return None when not matched, so they dont conflict. The status handler is registered first (matches /start, /help), then download, rclone_ops, pixiv.

## TODO List

- [x] Core download/upload (mirror, magnet, tgdown) + progress tracking
- [x] Rclone operations (lsd, ls, copy, copyurl)
- [x] AriaNg Web UI with auto-config
- [x] File cleanup after upload
- [x] Pixiv login via refresh_token (/pixivtoken) + persistence
- [ ] YouTube/Bilibili video download (yt-dlp)
- [ ] Netease Cloud Music
- [x] JMComic doujinshi download (Album/upload/TG ZIP)
- [ ] Image search (saucenao/ascii2d/WhatAnime)
- [ ] OneDrive/SharePoint share link download
- [ ] RcloneNg Web panel
- [ ] RSS auto-download
- [ ] Multi-user whitelist

## Commands Reference

| Command | Status | Description |
|---------|--------|-------------|
| /mirror <URL> | ✅ | Download + upload to cloud |
| /mirrortg <URL> | ✅ | Download + send to TG |
| /magnet <uri> | ✅ | Magnet download + upload |
| /tgdown | ✅ | Interactive: send file to upload |
| /list | ✅ | Show active downloads |
| /cancel <gid> | ✅ | Cancel download |
| /rclonecopy <s> <d> | ✅ | Copy between remotes |
| /rclonelsd [path] | ✅ | List directories |
| /rclonels [path] | ✅ | List files |
| /rclonecopyurl <URL> | ✅ | Upload URL directly |
| /start | ✅ | Bot status |
| /help | ✅ | Help |
| /pixivpid <id> | ✅ | Get illustration info + download |
| /pixivauthor <uid> | ✅ | Browse author works (5/page, paginated) |
| /pixivtop [mode] | ✅ | Browse rankings |
| /pixivtoken | ✅ | Show token setup tutorial |
| /pixivtoken <token> | ✅ | Set refresh_token directly |

\*Requires PIXIV_REFRESH_TOKEN (via .env or /pixivtoken)

## Quick Deploy

```bash
cp .env.example .env   # fill in your tokens
# put rclone.conf in ./rclone/
docker compose up -d
```

AriaNg: http://localhost:8080 (auto-configured)