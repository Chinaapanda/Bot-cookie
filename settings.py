"""โหลด/เซฟการตั้งค่าผู้ใช้ (settings.json) — อัปเดตแอปจะไม่ทับไฟล์นี้"""
from __future__ import annotations

import json
from pathlib import Path

from paths import app_dir

SETTINGS_FILE = app_dir() / "settings.json"

# คีย์ที่ผู้ใช้ปรับได้ผ่าน GUI / settings.json
USER_KEYS = (
    "ADB_PATH", "ADB_SERIAL", "TAP_X", "TAP_Y", "SLIDE_X", "SLIDE_Y",
    "TARGET_FPS", "CAPTURE_RAW", "DETECT_METHOD", "MOTION_THRESHOLD",
    "default_pattern", "default_lead", "auto_check_update",
)


def load() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(data: dict) -> None:
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def apply_user_settings() -> None:
    """นำค่าจาก settings.json ไปทับ config (เรียกตอนเริ่มโปรแกรม)"""
    import config

    data = load()
    for key in USER_KEYS:
        if key in data:
            setattr(config, key, data[key])


def get(key: str, default=None):
    return load().get(key, default)


def set_value(key: str, value) -> None:
    data = load()
    data[key] = value
    save(data)


def to_dict() -> dict:
    import config

    data = load()
    defaults = {
        "ADB_PATH": config.ADB_PATH,
        "ADB_SERIAL": config.ADB_SERIAL,
        "TAP_X": config.TAP_X,
        "TAP_Y": config.TAP_Y,
        "SLIDE_X": config.SLIDE_X,
        "SLIDE_Y": config.SLIDE_Y,
        "TARGET_FPS": config.TARGET_FPS,
        "CAPTURE_RAW": config.CAPTURE_RAW,
        "DETECT_METHOD": config.DETECT_METHOD,
        "MOTION_THRESHOLD": config.MOTION_THRESHOLD,
        "default_pattern": "EP1",
        "default_lead": 0,
        "auto_check_update": True,
    }
    defaults.update(data)
    return defaults
