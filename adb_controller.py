"""
ตัวควบคุม LDPlayer ผ่าน ADB: เชื่อมต่อ, จับภาพหน้าจอ, แตะ, ปัด
"""
from __future__ import annotations

import subprocess
import sys
import time

import cv2
import numpy as np

import config


def _subprocess_kwargs() -> dict:
    """ซ่อนหน้าต่าง console ของ adb.exe บน Windows (กันกระพริบตอน screencap รัวๆ)"""
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": si}


class ADBController:
    def __init__(self, adb_path: str = config.ADB_PATH, serial: str = config.ADB_SERIAL):
        self.adb_path = adb_path
        self.serial = serial

    # ---- low level -------------------------------------------------------
    def _run(self, args: list[str], capture: bool = True) -> subprocess.CompletedProcess:
        cmd = [self.adb_path, "-s", self.serial, *args]
        return subprocess.run(
            cmd,
            capture_output=capture,
            check=False,
            **_subprocess_kwargs(),
        )

    def connect(self) -> bool:
        """เชื่อมต่อกับ emulator. คืน True ถ้าต่อสำเร็จ"""
        # start adb server + connect
        kw = _subprocess_kwargs()
        subprocess.run([self.adb_path, "connect", self.serial],
                       capture_output=True, check=False, **kw)
        result = subprocess.run(
            [self.adb_path, "-s", self.serial, "get-state"],
            capture_output=True,
            text=True,
            check=False,
            **kw,
        )
        state = (result.stdout or "").strip()
        ok = state == "device"
        if ok:
            print(f"[ADB] เชื่อมต่อ {self.serial} สำเร็จ")
        else:
            print(f"[ADB] เชื่อมต่อไม่สำเร็จ: state={state!r} stderr={result.stderr.strip()!r}")
            print("      ตรวจว่า LDPlayer เปิดอยู่ และเปิด ADB debugging ในการตั้งค่า LDPlayer")
        return ok

    def screen_size(self) -> tuple[int, int]:
        """คืน (width, height) ของภาพจริงที่จับได้

        หมายเหตุ: `wm size` อาจรายงานเป็นแนวตั้ง (เช่น 1080x1920) ทั้งที่เกม
        แสดงผลแนวนอน ทำให้พิกัดเพี้ยน เราจึงยึดขนาดจากภาพ screencap จริง
        ซึ่งตรงกับระบบพิกัดของ input tap (ทดสอบแล้ว)
        """
        img = self.screencap()
        h, w = img.shape[:2]
        return w, h

    # ---- capture ---------------------------------------------------------
    def screencap(self) -> np.ndarray:
        """จับภาพหน้าจอ คืนเป็น BGR numpy array (ใช้กับ OpenCV)

        ถ้า config.CAPTURE_RAW = True จะดึง pixel ดิบ (RGBA) ตรง ๆ ไม่ต้อง
        encode/decode PNG -- เร็วกว่ามาก (สำคัญกับเกมที่ต้องตอบสนองไว)
        ถ้า raw ล้มเหลวจะ fallback กลับไปใช้ PNG อัตโนมัติ
        """
        if getattr(config, "CAPTURE_RAW", False):
            try:
                return self._screencap_raw()
            except Exception:
                pass
        return self._screencap_png()

    def _screencap_png(self) -> np.ndarray:
        raw = self._run(["exec-out", "screencap", "-p"]).stdout
        if not raw:
            raise RuntimeError("screencap ว่างเปล่า - ตรวจการเชื่อมต่อ ADB")
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("decode ภาพ screencap ไม่สำเร็จ")
        return img

    def _screencap_raw(self) -> np.ndarray:
        """ดึง framebuffer ดิบจาก `screencap` (ไม่มี -p)

        รูปแบบ: header [width(4), height(4), format(4), (colorspace(4) บน Android 9+)]
        แบบ little-endian ตามด้วย pixel RGBA = width*height*4 ไบต์
        เราหาขนาด header จากผลต่างความยาวจริง จึงรองรับทั้ง header 12 และ 16 ไบต์
        """
        raw = self._run(["exec-out", "screencap"]).stdout
        if not raw or len(raw) < 16:
            raise RuntimeError("screencap raw ว่างเปล่า")
        w = int.from_bytes(raw[0:4], "little")
        h = int.from_bytes(raw[4:8], "little")
        expected = w * h * 4
        header = len(raw) - expected
        if not (0 < w <= 10000 and 0 < h <= 10000) or header < 0:
            raise RuntimeError(f"screencap raw header ผิดปกติ (w={w} h={h} len={len(raw)})")
        arr = np.frombuffer(raw[header:header + expected], np.uint8).reshape(h, w, 4)
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

    # ---- input -----------------------------------------------------------
    def tap(self, x: int, y: int) -> None:
        self._run(["shell", "input", "tap", str(int(x)), str(int(y))], capture=False)

    def back(self) -> None:
        """กดปุ่ม Back ของ Android (ใช้ปิดเมนู/ป๊อปอัพที่ไม่รู้จัก)"""
        self._run(["shell", "input", "keyevent", "4"], capture=False)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 200) -> None:
        self._run(
            ["shell", "input", "swipe", str(int(x1)), str(int(y1)),
             str(int(x2)), str(int(y2)), str(int(duration_ms))],
            capture=False,
        )

    # ---- touch แบบแยก down/up (กดค้างจริง ใช้ input motionevent) ----------
    def touch_down(self, x: int, y: int) -> None:
        """แตะลง (นิ้วลง) ค้างไว้ จนกว่าจะเรียก touch_up"""
        self._run(["shell", "input", "motionevent", "DOWN", str(int(x)), str(int(y))],
                  capture=False)

    def touch_up(self, x: int, y: int) -> None:
        """ยกนิ้วขึ้น (ปล่อยที่กดค้างไว้)"""
        self._run(["shell", "input", "motionevent", "UP", str(int(x)), str(int(y))],
                  capture=False)

    def hold(self, x: int, y: int, duration_ms: int) -> None:
        """กดค้างที่จุดเดียวเป็นเวลา duration_ms (down -> รอ -> up)"""
        self.touch_down(x, y)
        time.sleep(max(duration_ms, 0) / 1000.0)
        self.touch_up(x, y)

    def single_tap(self, x: int, y: int, hold_ms: int = 25) -> None:
        """แตะครั้งเดียว (กระโดด) — ใช้ motionevent ไม่ใช้ input tap

        หลีกเลี่ยงการผสม input tap กับ motionevent บน LDPlayer
        ที่อาจทำให้เกมนับเป็นกระโดด 2 ครั้ง (double jump)
        """
        self.touch_down(x, y)
        time.sleep(max(hold_ms, 1) / 1000.0)
        self.touch_up(x, y)

    # ---- game actions ----------------------------------------------------
    def jump(self) -> None:
        self.single_tap(config.TAP_X, config.TAP_Y)

    def double_jump(self) -> None:
        self.single_tap(config.TAP_X, config.TAP_Y)
        time.sleep(0.08)
        self.single_tap(config.TAP_X, config.TAP_Y)

    def slide(self) -> None:
        # สไลด์ = ปัดลง/กดค้างอยู่กับที่
        self.swipe(
            config.SLIDE_X, config.SLIDE_Y,
            config.SLIDE_X, config.SLIDE_Y,
            duration_ms=config.SLIDE_HOLD_MS,
        )


if __name__ == "__main__":
    adb = ADBController()
    if adb.connect():
        print("ขนาดจอ:", adb.screen_size())
        img = adb.screencap()
        print("จับภาพได้ ขนาด:", img.shape)
