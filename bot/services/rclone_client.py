"""Rclone RC API async client."""
import logging
import os
import aiohttp
from config import RCLONE_HOST, RCLONE_PORT, RCLONE_REMOTE, RCLONE_UPLOAD_DIR, RCLONE_SHARE

log = logging.getLogger("rclone")
BASE = f"{RCLONE_HOST}:{RCLONE_PORT}"


async def _post(path: str, data: dict) -> dict:
    url = f"{BASE}/{path}"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=data, timeout=aiohttp.ClientTimeout(total=300)) as r:
            r.raise_for_status()
            result = await r.json()
            err = result.get("error")
            if err:
                raise RuntimeError(err)
            return result


async def upload_file(local_path: str, remote_subdir: str = "") -> str:
    """Upload a local file to remote via operations/copyfile.
    Uses proper srcFs/srcRemote/dstFs/dstRemote separation."""
    local_dir = os.path.dirname(local_path)
    local_name = os.path.basename(local_path)
    remote = f"{RCLONE_REMOTE}:{RCLONE_UPLOAD_DIR}/{remote_subdir}".rstrip("/")
    resp = await _post("operations/copyfile", {
        "srcFs": local_dir,
        "srcRemote": local_name,
        "dstFs": remote,
        "dstRemote": local_name,
        "_async": True,
    })
    jid = resp.get("jobid", 0)
    log.info("upload_file: %s -> %s/%s jobid=%s", local_path, remote, local_name, jid)
    return str(jid)


async def upload_dir(local_path: str, remote_subdir: str = "") -> str:
    remote = f"{RCLONE_REMOTE}:{RCLONE_UPLOAD_DIR}/{remote_subdir}".rstrip("/")
    resp = await _post("sync/copy", {"srcFs": local_path, "dstFs": remote, "_async": True})
    jid = resp.get("jobid", 0)
    log.info("upload_dir: %s -> %s jobid=%s", local_path, remote, jid)
    return str(jid)


async def copy_url(url: str, filename: str = "") -> str:
    resp = await _post("operations/copyurl", {
        "fs": f"{RCLONE_REMOTE}:{RCLONE_UPLOAD_DIR}",
        "remote": filename,
        "url": url,
        "autoFilename": not bool(filename),
        "_async": True,
    })
    jid = resp.get("jobid", 0)
    log.info("copyurl: %s jobid=%s", url, jid)
    return str(jid)


async def copy_remote(src: str, dst: str) -> str:
    resp = await _post("sync/copy", {"srcFs": src, "dstFs": dst, "_async": True})
    jid = resp.get("jobid", 0)
    log.info("copy_remote: %s -> %s jobid=%s", src, dst, jid)
    return str(jid)


async def list_dirs(remote_path: str = "") -> list[str]:
    fs = f"{RCLONE_REMOTE}:{remote_path}".rstrip("/")
    resp = await _post("operations/list", {"fs": fs, "remote": ""})
    return [i["Name"] for i in resp.get("list", []) if i.get("IsDir")]


async def list_files(remote_path: str = "") -> list[dict]:
    fs = f"{RCLONE_REMOTE}:{remote_path}".rstrip("/")
    resp = await _post("operations/list", {"fs": fs, "remote": ""})
    return resp.get("list", [])


async def job_finished(jobid: str) -> bool:
    resp = await _post("core/stats", {"group": f"job/{jobid}"})
    return "transferring" not in resp or not resp["transferring"]


async def job_progress(jobid: str) -> dict | None:
    resp = await _post("core/stats", {"group": f"job/{jobid}"})
    if "transferring" not in resp or not resp["transferring"]:
        return None
    t = resp["transferring"][0]
    return {
        "name": t.get("name", ""),
        "bytes": t.get("bytes", 0),
        "size": t.get("size", 0),
        "pct": t.get("percentage", 0),
        "speed": t.get("speed", 0),
        "speed_avg": t.get("speedAvg", 0),
        "eta": t.get("eta"),
    }


async def get_share_link(remote_path: str = "") -> str:
    resp = await _post("operations/publiclink", {
        "fs": f"{RCLONE_REMOTE}:{RCLONE_UPLOAD_DIR}/{remote_path}".rstrip("/"),
    })
    return resp.get("url", "")
