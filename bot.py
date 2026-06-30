"""
บอทเล่น Cookie Run Classic อัตโนมัติบน LDPlayer
ลูปหลัก: จับภาพ -> ตรวจอุปสรรค -> ตัดสินใจ กระโดด/สไลด์

ระหว่างเล่นยังจัดการหน้าจอพิเศษให้ด้วย:
  - "Tap to activate Cookie Relay Boost!" -> แตะกลางจอ
  - หน้า Result (จบเกม)                    -> กด OK (และเริ่มใหม่ถ้าใส่ --loop)

ใช้งาน:
    python bot.py            # รันบอท (ต้องอยู่ในด่านเอง)
    python bot.py --debug    # แสดงหน้าต่าง debug + คะแนนการตรวจจับ
    python bot.py --loop     # ขับเองครบวงจรจากทุกหน้าจอ:
                             #   หน้าเมนู -> เตรียม Double Coins -> Play
                             #   ในด่าน  -> กระโดด/สไลด์ + Cookie Relay Boost
                             #   จบเกม   -> OK -> วนกลับไปเริ่มใหม่
หยุดด้วย Ctrl+C (หรือกด q ในหน้าต่าง debug)
"""
from __future__ import annotations

import argparse
import time

import cv2

import config
from adb_controller import ADBController
from detector import build_detector, crop, roi_to_pixels
from auto_lobby import (
    RELAY_TAP, RESULT_OK, POST_GAME_BTN, is_relay_boost, is_result,
    is_lobby, is_buy, is_in_game, is_mystery_box, is_confirm,
    prepare_double_coins,
)


def draw_debug(img, result):
    h, w = img.shape[:2]
    overlay = img.copy()
    for roi, color, label in (
        (config.ROI_JUMP, (0, 165, 255), f"JUMP {result.jump_score:.3f}"),
        (config.ROI_SLIDE, (255, 100, 0), f"SLIDE {result.slide_score:.3f}"),
        (config.ROI_PLAYER, (0, 255, 0), "PLAYER"),
    ):
        x1, y1, x2, y2 = roi_to_pixels(roi, w, h)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.putText(overlay, label, (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    if result.jump:
        cv2.putText(overlay, "ACTION: JUMP", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 165, 255), 3)
    if result.slide:
        cv2.putText(overlay, "ACTION: SLIDE", (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 100, 0), 3)
    scale = 900 / max(w, 1)
    if scale < 1:
        overlay = cv2.resize(overlay, (int(w * scale), int(h * scale)))
    return overlay


def main():
    parser = argparse.ArgumentParser(description="Cookie Run Classic auto-play bot (LDPlayer/ADB)")
    parser.add_argument("--debug", action="store_true", help="แสดงหน้าต่าง debug")
    parser.add_argument("--prefer", choices=["jump", "slide"], default="jump",
                        help="ถ้าตรวจเจอทั้งสองพร้อมกัน ให้เลือกอันไหนก่อน")
    parser.add_argument("--loop", action="store_true",
                        help="จบเกมแล้วกด OK + เตรียม Double Coins + เริ่มด่านใหม่อัตโนมัติ")
    args = parser.parse_args()

    adb = ADBController()
    if not adb.connect():
        return

    detector = build_detector()
    frame_interval = 1.0 / max(config.TARGET_FPS, 1)
    last_action_t = 0.0
    last_status_t = 0.0
    last_screen_t = 0.0
    unknown_since = 0.0
    SCREEN_COOLDOWN = 0.5

    print(f"[bot] เริ่มทำงาน (วิธีตรวจจับ={config.DETECT_METHOD}, fps≈{config.TARGET_FPS})")
    print("[bot] เปิดเกม Cookie Run Classic แล้วเริ่มด่าน จากนั้นปล่อยให้บอททำงาน")
    print("[bot] หยุดด้วย Ctrl+C")

    try:
        while True:
            t0 = time.time()
            try:
                img = adb.screencap()
            except Exception as e:  # noqa: BLE001
                print(f"[bot] จับภาพล้มเหลว: {e}; ลองใหม่...")
                time.sleep(0.5)
                continue

            now = time.time()
            result = None

            # --- จัดการหน้าจอพิเศษ (เมนู/จบเกม/บูสต์) ---
            handled = False
            if now - last_screen_t >= SCREEN_COOLDOWN:
                if is_result(img):
                    last_screen_t = now
                    handled = True
                    print("[bot] หน้า Result (จบเกม) -> กด OK")
                    adb.tap(*RESULT_OK)
                    time.sleep(1.2)
                    if not args.loop:
                        print("[bot] จบเกมแล้ว (ใส่ --loop เพื่อเล่นวนอัตโนมัติ)")
                elif is_relay_boost(img):
                    last_screen_t = now
                    handled = True
                    print("[bot] Cookie Relay Boost! -> แตะกลางจอ")
                    adb.tap(*RELAY_TAP)
                elif is_mystery_box(img) or is_confirm(img):
                    last_screen_t = now
                    handled = True
                    print("[bot] Mystery Box / Confirm -> กดปุ่มกลางล่าง")
                    adb.tap(*POST_GAME_BTN)
                    time.sleep(0.8)
                elif args.loop and (is_lobby(img) or is_buy(img)):
                    last_screen_t = now
                    handled = True
                    print("[bot] --loop: อยู่หน้าเมนู -> เตรียม Double Coins แล้วเริ่มด่านใหม่")
                    prepare_double_coins(adb, want_play=True)
                    time.sleep(3.0)

            if handled:
                unknown_since = 0.0
                continue

            if is_in_game(img):
                # --- อยู่ในด่าน: ตรวจอุปสรรคและสั่งกระโดด/สไลด์ ---
                unknown_since = 0.0
                result = detector.detect(img)
                if now - last_action_t >= config.ACTION_COOLDOWN_S:
                    order = ("jump", "slide") if args.prefer == "jump" else ("slide", "jump")
                    for action in order:
                        if action == "jump" and result.jump:
                            adb.jump()
                            last_action_t = now
                            print(f"[bot] JUMP  (score={result.jump_score:.3f}) "
                                  f"-> tap ({config.TAP_X},{config.TAP_Y})")
                            break
                        if action == "slide" and result.slide:
                            adb.slide()
                            last_action_t = now
                            print(f"[bot] SLIDE (score={result.slide_score:.3f})")
                            break
                if now - last_status_t >= 1.5:
                    last_status_t = now
                    print(f"[bot] เล่นอยู่... jump={result.jump_score:.3f} "
                          f"slide={result.slide_score:.3f} (threshold={config.MOTION_THRESHOLD})")
            else:
                # --- ไม่ใช่หน้าที่รู้จัก และไม่ได้อยู่ในด่าน ---
                if args.loop:
                    if unknown_since == 0.0:
                        unknown_since = now
                    elif now - unknown_since > 4.0:
                        # ค้างหน้าจอแปลกนานเกินไป -> กด Back กู้คืน
                        print("[bot] หน้าจอไม่รู้จักค้างนาน -> กด Back กู้คืน")
                        adb.back()
                        time.sleep(1.0)
                        unknown_since = 0.0
                if now - last_status_t >= 2.0:
                    last_status_t = now
                    print("[bot] รอ... (ไม่ได้อยู่ในด่าน)")

            if args.debug:
                cv2.imshow("CookieRun bot - debug (q=ออก)",
                           draw_debug(img, result) if result is not None else img)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            elapsed = time.time() - t0
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
    except KeyboardInterrupt:
        print("\n[bot] หยุดทำงาน")
    finally:
        if args.debug:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
