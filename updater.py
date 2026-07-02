"""
ตรวจและติดตั้งอัปเดตจาก GitHub

รองรับ 2 โหมด:
  1) โฟลเดอร์ที่ clone ด้วย git (รันจาก source) -> git pull
  2) portable / .exe จาก Release zip          -> ดาวน์โหลด zip แล้ว merge
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

from paths import app_dir, is_frozen, is_git_repo
from version import GITHUB_REPO, VERSION

API_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RAW_VERSION = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.py"

# ไฟล์/โฟลเดอร์ที่อัปเดตแล้วไม่ทับ (ข้อมูลผู้ใช้)
PRESERVE = {"patterns", "settings.json", "shots", "venv", ".venv", "env", ".git",
            "_update_pkg", "_update_apply.bat"}


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


def fetch_release_info() -> UpdateInfo | None:
    """ดึงข้อมูล release ล่าสุดจาก GitHub (ไม่เช็คว่าใหม่กว่าปัจจุบันหรือไม่)"""
    return _latest_from_releases() or _latest_from_main()


def check_for_update() -> UpdateInfo | None:
    info = fetch_release_info()
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


def _zip_top_folder(extract: Path) -> Path:
    children = [p for p in extract.iterdir() if p.is_dir()]
    return children[0] if len(children) == 1 else extract


def _resolve_payload_root(top: Path) -> Path:
    """หาโฟลเดอร์ที่มีไฟล์จริงให้ copy — รองรับทั้ง release .exe และ source zip"""
    # Release: CookieRunBot-v2.0.0/CookieRunBot/CookieRunBot.exe
    bundled = top / "CookieRunBot"
    if bundled.is_dir() and (bundled / "CookieRunBot.exe").is_file():
        return bundled
    if (top / "CookieRunBot.exe").is_file():
        return top
    # Source zip: Bot-cookie-main/...
    if (top / "app.py").is_file():
        return top
    return top


def _should_skip(rel: Path) -> bool:
    if not rel.parts:
        return False
    if rel.parts[0] in PRESERVE:
        return True
    if rel.name in PRESERVE:
        return True
    return False


def _copy_payload(payload: Path, root: Path, log=print) -> int:
    updated = 0
    for src in payload.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(payload)
        if _should_skip(rel):
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
            updated += 1
        except OSError as e:
            log(f"[update] ข้าม {rel} ({e})")
    return updated


def _extract_release_zip(zip_url: str, log=print) -> tuple[Path, Path] | None:
    """คืน (work_dir, payload_root) — work_dir ใช้ลบ temp ทีหลัง"""
    log(f"[update] ดาวน์โหลด {zip_url}")
    try:
        raw = _http_get(zip_url, timeout=180)
    except Exception as e:
        log(f"[update] ดาวน์โหลดล้มเหลว: {e}")
        return None

    work_dir = Path(tempfile.mkdtemp(prefix="cookierun_update_"))
    zpath = work_dir / "update.zip"
    zpath.write_bytes(raw)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(work_dir / "unzipped")
    top = _zip_top_folder(work_dir / "unzipped")
    payload = _resolve_payload_root(top)
    n_files = sum(1 for _ in payload.rglob("*") if _.is_file())
    log(f"[update] แพ็กเกจ: {payload.name}/ ({n_files} ไฟล์)")
    return work_dir, payload


def _apply_staged_on_windows(payload: Path, root: Path, log=print) -> bool:
    """คัดลอกหลังปิดแอป — แก้ปัญหา Windows ล็อก CookieRunBot.exe"""
    staging = root / "_update_pkg"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(payload, staging)

    exe = Path(sys.executable).resolve()
    bat = root / "_update_apply.bat"
    bat.write_text(
        "\n".join([
            "@echo off",
            "chcp 65001 >nul",
            "timeout /t 2 /nobreak >nul",
            f'cd /d "{root}"',
            f'xcopy /E /Y /I "{staging}\\*" . >nul',
            f'rd /s /q "{staging}"',
            'del "%~f0" >nul 2>&1',
            f'start "" "{exe}"',
        ]),
        encoding="utf-8",
    )
    log("[update] จะปิดแอปแล้วติดตั้งอัตโนมัติ...")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen(["cmd", "/c", str(bat)], cwd=root, creationflags=flags)
    return True


def _merge_zip(zip_url: str, log=print, *, staged: bool = False) -> bool:
    root = app_dir()
    extracted = _extract_release_zip(zip_url, log)
    if extracted is None:
        return False
    work_dir, payload = extracted
    try:
        if staged and sys.platform == "win32":
            return _apply_staged_on_windows(payload, root, log)
        n = _copy_payload(payload, root, log)
        log(f"[update] อัปเดตไฟล์ {n} ไฟล์")
        return n > 0
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def apply_update(info: UpdateInfo | None = None, log=print) -> bool:
    info = info or check_for_update()

    # รันจาก .exe — ใช้ release zip เสมอ (ไม่ใช้ git pull)
    if is_frozen():
        if info is None or not info.zip_url:
            log("[update] ไม่มี URL สำหรับดาวน์โหลด")
            return False
        ok = _merge_zip(info.zip_url, log, staged=True)
        if ok:
            sys.exit(0)
        return False

    # รันจาก source ใน git repo
    if is_git_repo():
        if info is None:
            return _git_pull(log)
        if _git_pull(log):
            return True
        log("[update] git pull ไม่ได้ — ลองดาวน์โหลด release zip แทน...")

    if info is None or not info.zip_url:
        log("[update] ไม่มี URL สำหรับดาวน์โหลด")
        return False
    return _merge_zip(info.zip_url, log, staged=False)


def restart_app() -> None:
    """รีสตาร์ทแอปหลังอัปเดต"""
    exe = sys.executable
    args = sys.argv[1:]
    if is_frozen():
        subprocess.Popen([exe, *args], cwd=app_dir())
    else:
        app_py = app_dir() / "app.py"
        subprocess.Popen([exe, str(app_py), *args], cwd=app_dir())
    sys.exit(0)
