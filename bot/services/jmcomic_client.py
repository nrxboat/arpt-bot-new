"""JMComic download service wrapper.

Wraps the jmcomic library (hect0x7/JMComic-Crawler-Python) for searching,
downloading JMComic (18comic) albums and returning local file paths.
"""
import os
import zipfile
import shutil
import logging
import jmcomic
from config import DOWNLOAD_DIR

log = logging.getLogger("jmcomic")
JMCOMIC_DIR = os.path.join(DOWNLOAD_DIR, "jmcomic")

# Disable verbose jmcomic internal logging
jmcomic.disable_jm_log()


def _get_option():
    """Create a JMComic option with custom download directory.

    Uses 'Bd_Aid' rule: files go to {base_dir}/{album_id}/.
    """
    return jmcomic.create_option_by_str(
        f"""dir_rule:
  base_dir: {JMCOMIC_DIR}
  rule: Bd_Aid
"""
    )


def _get_client():
    """Create a JMComic API client."""
    return _get_option().new_jm_client()


def fetch_album_info(album_id: str) -> jmcomic.JmAlbumDetail:
    """Fetch album metadata (title, author, page_count) without downloading.

    Returns a JmAlbumDetail object.
    """
    client = _get_client()
    return client.get_album_detail(album_id)


def download_album(album_id: str):
    """Download a JMComic album to local storage.

    Returns (local_directory_path, JmAlbumDetail).
    """
    option = _get_option()
    detail, downloader = jmcomic.download_album(str(album_id), option)
    album_dir = os.path.join(JMCOMIC_DIR, str(album_id))
    return album_dir, detail


def search_albums(query: str, page: int = 1):
    """Search JMComic albums by name.

    Returns (list_of_(id, title)_tuples, total_pages, current_page).
    """
    client = _get_client()
    result = client.search_work(query, page=page)
    items = list(result.iter_id_title())
    return items, result.page_count, page


def download_cover(album_id: str, save_path: str):
    """Download album cover image to local path.

    Returns the path the cover was saved to.
    """
    client = _get_client()
    client.download_album_cover(album_id, save_path)
    return save_path


def list_album_images(album_dir: str) -> list[str]:
    """Return sorted list of image file paths in an album directory."""
    if not os.path.isdir(album_dir):
        return []
    files = []
    for fname in sorted(os.listdir(album_dir)):
        fpath = os.path.join(album_dir, fname)
        if os.path.isfile(fpath) and fname.lower().endswith((
                ".jpg", ".jpeg", ".png", ".webp"
        )):
            files.append(fpath)
    return files


def make_zip(album_dir: str, zip_path: str = None) -> str:
    """Create a ZIP archive of the album directory.

    Returns the path to the created ZIP file.
    """
    if zip_path is None:
        zip_path = album_dir.rstrip(os.sep) + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for root, _, files in os.walk(album_dir):
            for fname in sorted(files):
                if fname.lower().endswith(".zip"):
                    continue  # skip old ZIP files
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, album_dir)
                zf.write(fpath, arcname)
    log.info("Created ZIP: %s", zip_path)
    return zip_path


def cleanup_dir(path: str):
    """Recursively remove a directory."""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
            log.info("Cleaned up: %s", path)
    except Exception as e:
        log.warning("Cleanup failed for %s: %s", path, e)