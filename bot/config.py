"""ARPT-Bot 配置模块。"""
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("config")


def _require(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        log.error("缺少必需环境变量: %s", key)
        sys.exit(1)
    return val


def _int_env(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        log.error("环境变量 %s 必须是整数", key)
        sys.exit(1)


# ==================== Telegram ====================
API_ID = _int_env("API_ID")
API_HASH = _require("API_HASH")
BOT_TOKEN = _require("BOT_TOKEN")
OWNER_ID = _int_env("OWNER_ID")

# ==================== Aria2 ====================
ARIA2_HOST = os.environ.get("ARIA2_HOST", "http://localhost")
ARIA2_PORT = _int_env("ARIA2_PORT", 6800)
ARIA2_SECRET = _require("ARIA2_SECRET")

# ==================== Rclone ====================
RCLONE_HOST = os.environ.get("RCLONE_HOST", "http://localhost")
RCLONE_PORT = _int_env("RCLONE_PORT", 5572)
RCLONE_REMOTE = _require("RCLONE_REMOTE")
RCLONE_UPLOAD_DIR = os.environ.get("RCLONE_UPLOAD_DIR", "").strip("/")
RCLONE_SHARE = os.environ.get("RCLONE_SHARE", "false").strip().lower() == "true"

# ==================== 路径 ====================
DOWNLOAD_DIR = "/downloads"

# ==================== 其它 ====================
ERROR_USER_INFO = os.environ.get("ERROR_USER_INFO", "你没有使用权限。")


def log_config() -> None:
    log.info("--- ARPT-Bot 配置 ---")
    log.info("OWNER_ID: %d", OWNER_ID)
    log.info("ARIA2: %s:%d", ARIA2_HOST, ARIA2_PORT)
    log.info("RCLONE: %s:%d remote=%s dir=%s",
             RCLONE_HOST, RCLONE_PORT, RCLONE_REMOTE, RCLONE_UPLOAD_DIR)
    log.info("RCLONE_SHARE: %s", RCLONE_SHARE)
