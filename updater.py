"""
ตรวจและติดตั้งอัปเดตจาก GitHub

รองรับ 2 โหมด:
  1) โฟลเดอร์ที่ clone ด้วย git  -> git pull
  2) โฟลเดอร์/portable zip        -> ดาวน์โหลด release zip แล้ว merge
     (ไม่ทับ patterns/, settings.json, shots/)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from paths import app_dir, is_git_repo
from version import GITHUB_REPO, VERSION

API_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RAW_VERSION = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.py"

# ไฟล์/โฟลเดอร์ที่อัปเดตแล้วไม่ทับ (ข้อมูลผู้ใช้)
PRESERVE = {"patterns", "settings.json", "shots", "venv", ".venv", "env", ".git"}


@dataclass
class UpdateInfo:
    current: str
    latest: str
    url: str
    notes: str
    zip_url: str | None


def parse_version(v: str) -> tuple[int, ...]:
    v = re.sub(r"^v", "", v.strip())
    parts: list[int] = []
    for p in re.split(r"[.\-]", v):
        if p.isdigit():
            parts.append(int(p))
        elif parts:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _http_get(url: str, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "CookieRunBot-Updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _latest_from_releases() -> UpdateInfo | None:
    try:
        data = json.loads(_http_get(API_RELEASE).decode("utf-8"))
    except Exception:
        return None
    tag = data.get("tag_name", "")
    if not tag:
        return None
    zip_url = None
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".zip") and "CookieRunBot" in name:
            zip_url = asset.get("browser_download_url")
            break
    if not zip_url:
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith(".zip"):
                zip_url = asset.get("browser_download_url")
                break
    return UpdateInfo(
        current=VERSION,
        latest=tag.lstrip("v"),
        url=data.get("html_url", ""),
        notes=data.get("body", "") or "",
        zip_url=zip_url,
    )


def _latest_from_main() -> UpdateInfo | None:
    """fallback ถ้ายังไม่มี GitHub Release — อ่าน VERSION จาก main branch"""
    try:
        text = _http_get(RAW_VERSION).decode("utf-8")
        m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', text)
        if not m:
            return None
        remote = m.group(1)
        return UpdateInfo(
            current=VERSION,
            latest=remote,
            url=f"https://github.com/{GITHUB_REPO}",
            notes="อัปเดตจาก main branch (ยังไม่มี Release)",
            zip_url=f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip",
        )
    except Exception:
        return None


def check_for_update() -> UpdateInfo | None:
    info = _latest_from_releases() or _latest_from_main()
    if info is None:
        return None
    if parse_version(info.latest) <= parse_version(info.current):
        return None
    return info


def _git_pull(log=print) -> bool:
    root = app_dir()
    log("[update] git pull...")
    r = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        log(f"[update] git pull ล้มเหลว: {r.stderr or r.stdout}")
        return False
    log(r.stdout or "[update] git pull สำเร็จ")
    return True


def _merge_zip(zip_url: str, log=print) -> bool:
    root = app_dir()
    log(f"[update] ดาวน์โหลด {zip_url}")
    try:
        raw = _http_get(zip_url, timeout=120)
    except Exception as e:
        log(f"[update] ดาวน์โหลดล้มเหลว: {e}")
        return False

    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "update.zip"
        zpath.write_bytes(raw)
        extract = Path(tmp) / "extract"
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(extract)

        # หา root ของ zip (มักเป็น RepoName-branch/)
        children = [p for p in extract.iterdir() if p.is_dir()]
        src_root = children[0] if len(children) == 1 else extract

        updated = 0
        for src in src_root.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(src_root)
            if rel.parts and rel.parts[0] in PRESERVE:
                continue
            if rel.name in PRESERVE:
                continue
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            updated += 1
        log(f"[update] อัปเดตไฟล์ {updated} ไฟล์")
    return True


def apply_update(info: UpdateInfo | None = None, log=print) -> bool:
    if is_git_repo():
        return _git_pull(log)
    info = info or check_for_update()
    if info is None or not info.zip_url:
        log("[update] ไม่มี URL สำหรับดาวน์โหลด")
        return False
    return _merge_zip(info.zip_url, log)


def restart_app() -> None:
    """รีสตาร์ทแอปหลังอัปเดต"""
    exe = sys.executable
    args = sys.argv[1:]
    if getattr(sys, "frozen", False):
        subprocess.Popen([exe, *args], cwd=app_dir())
    else:
        app_py = app_dir() / "app.py"
        subprocess.Popen([exe, str(app_py), *args], cwd=app_dir())
    sys.exit(0)
