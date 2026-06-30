"""
ตัวควบคุม LDPlayer ผ่าน ADB: เชื่อมต่อ, จับภาพหน้าจอ, แตะ, ปัด
"""
from __future__ import annotations

import subprocess
import time

import cv2
import numpy as np

import config


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
        )

    def connect(self) -> bool:
        """เชื่อมต่อกับ emulator. คืน True ถ้าต่อสำเร็จ"""
        # start adb server + connect
        subprocess.run([self.adb_path, "connect", self.serial], capture_output=True, check=False)
        result = subprocess.run(
            [self.adb_path, "-s", self.serial, "get-state"],
            capture_output=True,
            text=True,
            check=False,
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
        """จับภาพหน้าจอ คืนเป็น BGR numpy array (ใช้กับ OpenCV)"""
        raw = self._run(["exec-out", "screencap", "-p"]).stdout
        if not raw:
            raise RuntimeError("screencap ว่างเปล่า - ตรวจการเชื่อมต่อ ADB")
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("decode ภาพ screencap ไม่สำเร็จ")
        return img

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

    # ---- game actions ----------------------------------------------------
    def jump(self) -> None:
        self.tap(config.TAP_X, config.TAP_Y)

    def double_jump(self) -> None:
        self.tap(config.TAP_X, config.TAP_Y)
        time.sleep(0.06)
        self.tap(config.TAP_X, config.TAP_Y)

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
