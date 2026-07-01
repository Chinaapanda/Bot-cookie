"""หาโฟลเดอร์แอป (รองรับทั้งรันจาก source และ .exe จาก PyInstaller)"""
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def is_git_repo() -> bool:
    return (app_dir() / ".git").is_dir()
