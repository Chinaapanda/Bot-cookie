"""
เครื่องมือช่วยตั้งค่า (calibration) สำหรับบอท Cookie Run Classic

ทำอะไรได้บ้าง:
  - แสดงขนาดจอจริงของ emulator
  - จับภาพหน้าจอ + วางทับโซนตรวจจับ (ROI) ปัจจุบันให้ดูว่าตรงไหม
  - คลิกบนภาพเพื่ออ่านพิกัด (เอาไปใส่ TAP_X/TAP_Y, SLIDE_X/SLIDE_Y ใน config.py)
  - ลากกรอบเพื่อเซฟเป็น template อุปสรรค

ใช้งาน:
    python calibrate.py
ปุ่มลัดในหน้าต่าง:
    s = เซฟภาพหน้าจอลงโฟลเดอร์ shots/
    r = จับภาพใหม่ (refresh)
    j = โหมดเซฟ template แบบ "jump" (ลากกรอบแล้วปล่อย)
    k = โหมดเซฟ template แบบ "slide"
    c = ออกจากโหมดเซฟ template (กลับโหมดอ่านพิกัด)
    q = ออก
"""
from __future__ import annotations

import time

import cv2

import config
from adb_controller import ADBController
from detector import roi_to_pixels
from paths import app_dir

WIN = "calibrate (q=ออก)"

state = {
    "mode": "coord",       # "coord" หรือ "template"
    "tpl_kind": "jump",
    "dragging": False,
    "start": (0, 0),
    "end": (0, 0),
    "scale": 1.0,
    "img": None,
}


def on_mouse(event, x, y, flags, param):
    sx = x / state["scale"]
    sy = y / state["scale"]
    if state["mode"] == "coord":
        if event == cv2.EVENT_LBUTTONDOWN:
            print(f"  พิกัดจริง: x={int(sx)}, y={int(sy)}   (ใช้ตั้ง TAP/SLIDE ใน config.py)")
    else:  # template mode
        if event == cv2.EVENT_LBUTTONDOWN:
            state["dragging"] = True
            state["start"] = (int(sx), int(sy))
            state["end"] = (int(sx), int(sy))
        elif event == cv2.EVENT_MOUSEMOVE and state["dragging"]:
            state["end"] = (int(sx), int(sy))
        elif event == cv2.EVENT_LBUTTONUP and state["dragging"]:
            state["dragging"] = False
            state["end"] = (int(sx), int(sy))
            _save_template()


def _save_template():
    img = state["img"]
    if img is None:
        return
    (x1, y1), (x2, y2) = state["start"], state["end"]
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if x2 - x1 < 5 or y2 - y1 < 5:
        print("  กรอบเล็กเกินไป ยกเลิก")
        return
    crop = img[y1:y2, x1:x2]
    folder = (app_dir() / "templates" / state["tpl_kind"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{int(time.time())}.png"
    cv2.imwrite(str(path), crop)
    print(f"  เซฟ template ({state['tpl_kind']}) -> {path}")


def render(img):
    h, w = img.shape[:2]
    vis = img.copy()
    for roi, color, label in (
        (config.ROI_JUMP, (0, 165, 255), "ROI_JUMP"),
        (config.ROI_SLIDE, (255, 100, 0), "ROI_SLIDE"),
        (config.ROI_PLAYER, (0, 255, 0), "ROI_PLAYER"),
    ):
        x1, y1, x2, y2 = roi_to_pixels(roi, w, h)
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
        cv2.putText(vis, label, (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    # mark TAP / SLIDE points
    cv2.circle(vis, (config.TAP_X, config.TAP_Y), 14, (0, 0, 255), 3)
    cv2.putText(vis, "TAP", (config.TAP_X + 16, config.TAP_Y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.circle(vis, (config.SLIDE_X, config.SLIDE_Y), 14, (255, 0, 255), 3)
    cv2.putText(vis, "SLIDE", (config.SLIDE_X + 16, config.SLIDE_Y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

    if state["mode"] == "template" and state["dragging"]:
        cv2.rectangle(vis, state["start"], state["end"], (255, 255, 255), 1)

    mode_txt = f"MODE={state['mode']}"
    if state["mode"] == "template":
        mode_txt += f" ({state['tpl_kind']})  ลากกรอบเพื่อเซฟ"
    cv2.putText(vis, mode_txt, (20, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    scale = 1000 / max(w, 1)
    scale = min(scale, 1.0)
    state["scale"] = scale
    if scale < 1.0:
        vis = cv2.resize(vis, (int(w * scale), int(h * scale)))
    return vis


def main():
    adb = ADBController()
    if not adb.connect():
        return
    print("ขนาดจอ emulator:", adb.screen_size())
    print("คลิกบนภาพเพื่ออ่านพิกัด | s=เซฟภาพ r=รีเฟรช j/k=โหมด template c=กลับโหมดพิกัด q=ออก")

    cv2.namedWindow(WIN)
    cv2.setMouseCallback(WIN, on_mouse)

    img = adb.screencap()
    state["img"] = img

    while True:
        cv2.imshow(WIN, render(state["img"]))
        key = cv2.waitKey(20) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("r"):
            state["img"] = adb.screencap()
            print("รีเฟรชภาพแล้ว")
        elif key == ord("s"):
            path = config.SHOTS_DIR / f"shot_{int(time.time())}.png"
            cv2.imwrite(str(path), state["img"])
            print(f"เซฟภาพ -> {path}")
        elif key == ord("j"):
            state["mode"] = "template"
            state["tpl_kind"] = "jump"
            print("โหมด template: jump (ลากกรอบรอบอุปสรรคที่ต้องกระโดด)")
        elif key == ord("k"):
            state["mode"] = "template"
            state["tpl_kind"] = "slide"
            print("โหมด template: slide (ลากกรอบรอบอุปสรรคที่ต้องสไลด์)")
        elif key == ord("c"):
            state["mode"] = "coord"
            print("กลับโหมดอ่านพิกัด")

    cv2.destroyAllWindows()


def run_calibrate():
    """เปิดหน้าต่าง calibrate แบบ OpenCV (เรียกจาก GUI หรือ CLI)"""
    from settings import apply_user_settings
    apply_user_settings()
    main()


if __name__ == "__main__":
    run_calibrate()
