"""ค่าที่ปรับได้ขณะบอทรัน (thread-safe)"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_lead_ms: int | None = None
_anchor_s: float | None = None  # None = ใช้ค่าจากไฟล์ pattern

FEATURE_DEFAULTS: dict[str, bool] = {
    "double_coins": True,    # สุ่ม Multi-Buy หา Double Coins ก่อนเล่น
    "surprise_card": True,   # แก้มินิเกม Surprise Card
    "relay_boost": True,     # แตะ Cookie Relay Boost
    "post_game": True,       # OK / Result / Mystery Box หลังจบด่าน
}

_features: dict[str, bool] | None = None
_surprise_cooldown_until: float = 0.0


def set_surprise_cooldown(seconds: float = 5.0) -> None:
    """ไม่ detect การ์ดชั่วคราวหลังออกจากมินิเกม (กัน false positive ที่ lobby)"""
    global _surprise_cooldown_until
    with _lock:
        _surprise_cooldown_until = time.time() + max(seconds, 0.0)


def surprise_on_cooldown() -> bool:
    with _lock:
        return time.time() < _surprise_cooldown_until


def set_live_lead(ms: int | None) -> None:
    """ตั้ง lead (ms) สด — None = ใช้ค่าตอนเริ่มรอบ pattern"""
    global _lead_ms
    with _lock:
        _lead_ms = ms


def get_live_lead_ms(fallback: int) -> int:
    """คืน lead ปัจจุบัน (ms) — อ่านก่อนทุกจังหวะ pattern"""
    with _lock:
        return _lead_ms if _lead_ms is not None else fallback


def set_live_anchor(seconds: float | None) -> None:
    """ตั้ง anchor (วินาที) สด — None = ใช้ค่าจากไฟล์ pattern"""
    global _anchor_s
    with _lock:
        _anchor_s = seconds


def get_live_anchor_s(pattern_anchor: float) -> float:
    """คืน anchor ปัจจุบัน (วินาที) — อ่านก่อนเริ่มเล่น pattern"""
    with _lock:
        return _anchor_s if _anchor_s is not None else pattern_anchor


def init_features(overrides: dict[str, bool] | None = None) -> None:
    """โหลดฟีเจอร์จาก settings.json (+ override จาก CLI/GUI)"""
    global _features
    from settings import load

    feats = dict(FEATURE_DEFAULTS)
    feats.update(load().get("features", {}))
    if overrides is not None:
        feats.update(overrides)
    with _lock:
        _features = feats


def set_feature(name: str, enabled: bool) -> None:
    with _lock:
        global _features
        if _features is None:
            _features = dict(FEATURE_DEFAULTS)
        _features[name] = enabled


def feature_enabled(name: str) -> bool:
    with _lock:
        global _features
        if _features is None:
            _features = dict(FEATURE_DEFAULTS)
            from settings import load
            _features.update(load().get("features", {}))
        return _features.get(name, FEATURE_DEFAULTS.get(name, True))


def features_snapshot() -> dict[str, bool]:
    with _lock:
        return {k: feature_enabled(k) for k in FEATURE_DEFAULTS}
