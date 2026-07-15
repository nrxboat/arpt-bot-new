"""Aria2 JSON-RPC 客户端。"""
import logging
import asyncio
import aria2p
from config import ARIA2_HOST, ARIA2_PORT, ARIA2_SECRET

log = logging.getLogger("aria2")

aria2 = aria2p.API(
    aria2p.Client(
        host=ARIA2_HOST, port=ARIA2_PORT,
        secret=ARIA2_SECRET, timeout=30,
    )
)

_loop: asyncio.AbstractEventLoop | None = None
_callbacks: list = []


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _run(coro):
    if _loop is None:
        log.error("事件循环未设置")
        return
    asyncio.run_coroutine_threadsafe(coro, _loop)


def on_complete(cb):
    _callbacks.append(cb)


def _handle_complete(api, gid):
    try:
        d = api.get_download(gid)
        for cb in _callbacks:
            _run(cb(gid, d.name, [f["path"] for f in d.files]))
    except Exception:
        log.exception("通知处理失败 gid=%s", gid)


def listen() -> None:
    log.info("启动 aria2 通知监听...")
    aria2.listen_to_notifications(
        on_download_complete=_handle_complete, threaded=True,
    )


def add_url(url: str, opts: dict | None = None) -> str:
    d = aria2.add(url, options=opts or {})
    log.info("添加直链 gid=%s", d.gid)
    return d.gid


def add_magnet(uri: str, opts: dict | None = None) -> str:
    d = aria2.add_magnet(uri, options=opts or {})
    log.info("添加磁力 gid=%s", d.gid)
    return d.gid


def add_torrent(path: str, opts: dict | None = None) -> str:
    d = aria2.add_torrent(path, options=opts or {})
    log.info("添加种子 gid=%s", d.gid)
    return d.gid


def get(gid: str):
    try:
        return aria2.get_download(gid)
    except Exception:
        return None


def all_downloads() -> list:
    return aria2.get_downloads()


def pause_gid(gid: str) -> None:
    aria2.pause([gid])


def resume_gid(gid: str) -> None:
    aria2.resume([gid])


def remove_gid(gid: str) -> None:
    aria2.remove([gid])
    try:
        aria2.remove_download_result(gid)
    except Exception:
        pass


def fmt(n: int) -> str:
    if n is None or n < 0:
        return "未知"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_spd(n: int) -> str:
    return f"{fmt(n)}/s" if n else "0 B/s"


def fmt_eta(sec: int) -> str:
    if sec is None or sec < 0:
        return "未知"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}时{m}分{s}秒"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def pbar(cur: int, tot: int, w: int = 10) -> str:
    if not tot:
        return "▱" * w
    f = min(int(w * cur / tot), w)
    return "▰" * f + "▱" * (w - f)
