"""ชั้น business logic — แยกจาก UI"""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from settings import load, save


LogFn = Callable[[str], None]
StatusFn = Callable[[str], None]


class _LogStream:
    """ดัก stdout/stderr จากบอทส่งเข้า log panel"""

    def __init__(self, log: LogFn):
        self._log = log
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line:
                self._log(line)
        return len(s)

    def flush(self) -> None:
        if self._buf.strip():
            self._log(self._buf.rstrip())
            self._buf = ""


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
    """รันบอทใน background thread — ไม่ spawn .exe ซ้ำ (กันเปิดหน้าต่างรัวๆ)"""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._on_done: Callable[[], None] | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, args: list[str], log: LogFn, on_done: Callable[[], None] | None = None):
        if self.running:
            raise RuntimeError("บอทกำลังทำงานอยู่")
        self._stop_event.clear()
        self._on_done = on_done
        log(f">>> bot {' '.join(args)}")
        self._thread = threading.Thread(
            target=self._run_thread, args=(args, log), daemon=True,
        )
        self._thread.start()

    def _run_thread(self, args: list[str], log: LogFn):
        from bot import run_bot_from_argv

        stream = _LogStream(log)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = stream  # type: ignore[assignment]
        sys.stderr = stream  # type: ignore[assignment]
        try:
            run_bot_from_argv(args, stop_event=self._stop_event)
        except Exception as e:
            log(f"[bot] error: {e}")
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            stream.flush()
            log("[bot] จบการทำงาน")
            self._thread = None
            if self._on_done:
                self._on_done()

    def stop(self, log: LogFn):
        if not self.running:
            return
        self._stop_event.set()
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        log("[app] ส่งคำสั่งหยุดบอท")


def persist_settings(data: dict) -> None:
    save(data)


def read_settings() -> dict:
    from settings import to_dict
    return to_dict()
