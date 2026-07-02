"""หาโฟลเดอร์แอป (รองรับทั้งรันจาก source และ .exe จาก PyInstaller)"""
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """โฟลเดอร์ที่รันแอป — เก็บ patterns, settings, shots (เขียนได้)"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """โฟลเดอร์ที่ PyInstaller แตกไฟล์แพ็ก (_internal) — อ่านอย่างเดียว"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_dir() / "_internal"))
    return Path(__file__).resolve().parent


def templates_dir() -> Path:
    """โฟลเดอร์ templates — อ่านจาก bundle; override ได้ที่ข้าง .exe"""
    beside = app_dir() / "templates"
    if getattr(sys, "frozen", False):
        bundled = bundle_dir() / "templates"
        if beside.is_dir() and any(beside.rglob("*.png")):
            return beside
        return bundled
    beside.mkdir(parents=True, exist_ok=True)
    return beside


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def is_git_repo() -> bool:
    return (app_dir() / ".git").is_dir()
