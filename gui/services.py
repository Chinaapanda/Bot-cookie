"""ชั้น business logic — แยกจาก UI"""
from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from paths import app_dir, is_frozen
from settings import load, save


LogFn = Callable[[str], None]
StatusFn = Callable[[str], None]


@dataclass
class PatternMeta:
    name: str
    events: int
    relays: int
    duration: float
    path: Path


class PatternService:
    @staticmethod
    def list_all() -> list[PatternMeta]:
        from pattern import load_pattern, pattern_path, list_patterns

        out: list[PatternMeta] = []
        for name in list_patterns():
            try:
                d = load_pattern(name)
                evs = d.get("events", [])
                out.append(PatternMeta(
                    name=name,
                    events=sum(1 for e in evs if e.get("a") != "relay"),
                    relays=sum(1 for e in evs if e.get("a") == "relay"),
                    duration=float(d.get("duration", 0)),
                    path=pattern_path(name),
                ))
            except Exception:
                out.append(PatternMeta(name, 0, 0, 0, pattern_path(name)))
        return out

    @staticmethod
    def create(name: str) -> Path:
        from pattern import create_pattern
        return create_pattern(name)

    @staticmethod
    def rename(old_name: str, new_name: str) -> Path:
        from pattern import rename_pattern
        return rename_pattern(old_name, new_name)

    @staticmethod
    def delete(name: str) -> None:
        from pattern import delete_pattern
        delete_pattern(name)


class AdbService:
    @staticmethod
    def test(log: LogFn) -> tuple[bool, str]:
        try:
            from settings import apply_user_settings
            apply_user_settings()
            from adb_controller import ADBController
            adb = ADBController()
            if adb.connect():
                w, h = adb.screen_size()
                msg = f"เชื่อมต่อสำเร็จ — จอ {w}×{h}"
                log(f"[ADB] {msg}")
                return True, msg
            log("[ADB] เชื่อมต่อไม่สำเร็จ")
            return False, "เชื่อมต่อไม่สำเร็จ"
        except Exception as e:
            log(f"[ADB] error: {e}")
            return False, str(e)


class BotService:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._on_done: Callable[[], None] | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _cmd(self, *args: str) -> list[str]:
        if is_frozen():
            return [sys.executable, "--bot", *args]
        return [sys.executable, str(app_dir() / "bot.py"), *args]

    def start(self, args: list[str], log: LogFn, on_done: Callable[[], None] | None = None):
        if self.running:
            raise RuntimeError("บอทกำลังทำงานอยู่")
        self._on_done = on_done
        cmd = self._cmd(*args)
        log(f">>> {' '.join(cmd)}")
        self._proc = subprocess.Popen(
            cmd, cwd=app_dir(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        threading.Thread(target=self._read, args=(log,), daemon=True).start()

    def _read(self, log: LogFn):
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            log(line.rstrip())
        log("[bot] จบการทำงาน")
        self._proc = None
        if self._on_done:
            self._on_done()

    def stop(self, log: LogFn):
        if self.running:
            self._proc.terminate()  # type: ignore[union-attr]
            log("[app] ส่งคำสั่งหยุดบอท")


def persist_settings(data: dict) -> None:
    save(data)


def read_settings() -> dict:
    from settings import to_dict
    return to_dict()
