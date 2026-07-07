"""
บอทเล่น Cookie Run Classic อัตโนมัติบน LDPlayer
ลูปหลัก: จับภาพ -> ตรวจอุปสรรค -> ตัดสินใจ กระโดด/สไลด์

ระหว่างเล่นยังจัดการหน้าจอพิเศษให้ด้วย:
  - "Tap to activate Cookie Relay Boost!" -> แตะกลางจอ
  - ปุ่ม OK (Result / popup ทั่วไป)       -> กดเสมอ
  - หน้า Result (จบเกม)                    -> กด OK (และเริ่มใหม่ถ้าใส่ --loop)

ใช้งาน:
    python bot.py                       # รันบอทโหมด react สด (ต้องอยู่ในด่านเอง)
    python bot.py --debug               # แสดงหน้าต่าง debug + คะแนนการตรวจจับ
    python bot.py --loop                # ขับเองครบวงจรจากทุกหน้าจอ:
                                        #   หน้าเมนู -> เตรียม Double Coins -> Play
                                        #   ในด่าน  -> react/หรือ pattern + Relay Boost
                                        #   จบเกม   -> OK -> วนกลับไปเริ่มใหม่

โหมด pattern (อัดจังหวะที่ดีไว้แล้วเล่นซ้ำ -- เก็บเหรียญสม่ำเสมอสุด):
    python bot.py --record EP1          # อัด pattern ด่านนี้ (คุมด้วยคีย์บอร์ด)
    python bot.py --play-pattern EP1    # เล่นซ้ำ 1 รอบ
    python bot.py --loop --pattern EP1 --lead 80   # เล่นวนด้วย pattern อัตโนมัติ

หยุดด้วย Ctrl+C (หรือกด q ในหน้าต่าง debug)
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

import cv2

import config
from settings import apply_user_settings
from adb_controller import ADBController
from detector import build_detector, crop, roi_to_pixels
from auto_lobby import (
    RELAY_TAP, POST_GAME_BTN, is_relay_boost, is_result,
    is_lobby, is_buy, is_in_game, is_mystery_box, is_confirm,
    is_ok_btn, ok_btn_tap, prepare_for_run,
)
from surprise_card import is_surprise_card, handle_surprise_card
from pattern import record_pattern, play_pattern
from runtime import set_live_lead, init_features, feature_enabled


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cookie Run Classic auto-play bot (LDPlayer/ADB)")
    parser.add_argument("--debug", action="store_true", help="แสดงหน้าต่าง debug")
    parser.add_argument("--prefer", choices=["jump", "slide"], default="jump",
                        help="ถ้าตรวจเจอทั้งสองพร้อมกัน ให้เลือกอันไหนก่อน")
    parser.add_argument("--loop", action="store_true",
                        help="จบเกมแล้วกด OK + เตรียม Double Coins + เริ่มด่านใหม่อัตโนมัติ")
    parser.add_argument("--record", metavar="NAME",
                        help="อัด pattern ใหม่ (คุมเกมด้วยคีย์บอร์ด) แล้วออก")
    parser.add_argument("--play-pattern", metavar="NAME",
                        help="เตรียม lobby+Play แล้วเล่น pattern 1 รอบ (จัดการ Relay ให้ด้วย)")
    parser.add_argument("--no-prep", action="store_true",
                        help="ไม่เตรียม lobby/Play ก่อนเล่น pattern (ต้องอยู่ในด่านแล้ว)")
    parser.add_argument("--pattern", metavar="NAME",
                        help="ใช้ pattern นี้เล่นช่วงอยู่ในด่าน (แทนการ react สด) -- ใช้คู่กับ --loop ได้")
    parser.add_argument("--lead", type=int, default=0,
                        help="ยิง action ของ pattern เร็วขึ้นกี่ ms (ชดเชย lag)")
    parser.add_argument("--jump-gap", type=int, default=None,
                        help="ระยะห่างขั้นต่ำระหว่างกระโดด (ms) กัน double jump (ค่าเริ่มต้นจาก settings)")
    parser.add_argument("--no-double-coins", action="store_true",
                        help="ไม่สุ่ม Double Coins ก่อนเล่น")
    parser.add_argument("--no-surprise-card", action="store_true",
                        help="ไม่แก้มินิเกม Surprise Card")
    parser.add_argument("--no-relay", action="store_true",
                        help="ไม่แตะ Cookie Relay Boost")
    parser.add_argument("--no-post-game", action="store_true",
                        help="ไม่กด OK/Result/Mystery Box หลังจบด่าน")
    return parser


def run_bot_from_argv(argv: list[str], stop_event: threading.Event | None = None) -> None:
    apply_user_settings()
    args = _build_parser().parse_args(argv)

    jump_gap = args.jump_gap
    if jump_gap is None:
        jump_gap = getattr(config, "JUMP_MIN_GAP_MS", 0)

    set_live_lead(args.lead)
    cli_feats: dict[str, bool] = {}
    if args.no_double_coins:
        cli_feats["double_coins"] = False
    if args.no_surprise_card:
        cli_feats["surprise_card"] = False
    if args.no_relay:
        cli_feats["relay_boost"] = False
    if args.no_post_game:
        cli_feats["post_game"] = False
    init_features(cli_feats or None)

    adb = ADBController()
    if not adb.connect():
        return

    # --- โหมดจัดการ pattern แบบครั้งเดียวจบ ---
    if args.record:
        record_pattern(adb, args.record, stop_event=stop_event)
        return
    if args.play_pattern and args.loop:
        # --play-pattern + --loop = เล่นวนครบวงจร (รวมจบเกมกลับ lobby)
        args.pattern = args.play_pattern
    elif args.play_pattern:
        if not args.no_prep and not (stop_event is not None and stop_event.is_set()):
            try:
                if not is_in_game(adb.screencap()):
                    print("[bot] ยังไม่อยู่ในด่าน -> เตรียม lobby + กด Play")
                    prepare_for_run(adb, want_play=True,
                                    use_double_coins=feature_enabled("double_coins"),
                                    stop_event=stop_event)
                    time.sleep(2.5)
            except Exception as e:  # noqa: BLE001
                print(f"[bot] เตรียม lobby ล้มเหลว: {e}")
        status = play_pattern(adb, args.play_pattern, lead_ms=args.lead,
                              jump_gap_ms=jump_gap,
                              watch_relay=feature_enabled("relay_boost"),
                              watch_surprise=feature_enabled("surprise_card"),
                              stop_event=stop_event)
        if status == "game_over" and feature_enabled("post_game"):
            try:
                time.sleep(0.8)
                cap = adb.screencap()
                if is_result(cap) or is_ok_btn(cap):
                    print("[bot] หน้า Result / ปุ่ม OK -> กด OK")
                    adb.tap(*ok_btn_tap(cap))
            except Exception:
                pass
        return

    detector = build_detector()
    frame_interval = 1.0 / max(config.TARGET_FPS, 1)
    last_action_t = 0.0
    last_status_t = 0.0
    last_screen_t = 0.0
    unknown_since = 0.0
    prev_jump = False          # สำหรับ trigger แบบ rising-edge (เลิกกระโดดรัว)
    prev_slide = False
    SCREEN_COOLDOWN = 0.5

    print(f"[bot] เริ่มทำงาน (วิธีตรวจจับ={config.DETECT_METHOD}, fps≈{config.TARGET_FPS})")
    print("[bot] เปิดเกม Cookie Run Classic แล้วเริ่มด่าน จากนั้นปล่อยให้บอททำงาน")
    print("[bot] หยุดด้วย Ctrl+C")

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                print("[bot] หยุดจากแอป")
                break
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
                if feature_enabled("post_game") and is_result(img):
                    last_screen_t = now
                    handled = True
                    print("[bot] หน้า Result (จบเกม) -> กด OK")
                    adb.tap(*ok_btn_tap(img))
                    time.sleep(1.2)
                    if not args.loop:
                        print("[bot] จบเกมแล้ว (ใส่ --loop เพื่อเล่นวนอัตโนมัติ)")
                elif feature_enabled("post_game") and is_ok_btn(img):
                    last_screen_t = now
                    handled = True
                    print("[bot] เจอปุ่ม OK -> กด")
                    adb.tap(*ok_btn_tap(img))
                    time.sleep(0.8)
                elif feature_enabled("surprise_card") and not (is_lobby(img) or is_buy(img)) and is_surprise_card(img):
                    last_screen_t = now
                    handled = True
                    print("[bot] Surprise Card minigame -> แก้อัตโนมัติ")
                    handle_surprise_card(adb, img)
                    time.sleep(0.5)
                elif feature_enabled("relay_boost") and is_relay_boost(img):
                    last_screen_t = now
                    handled = True
                    print("[bot] Cookie Relay Boost! -> แตะกลางจอ")
                    adb.tap(*RELAY_TAP)
                elif feature_enabled("post_game") and (is_mystery_box(img) or is_confirm(img)):
                    last_screen_t = now
                    handled = True
                    print("[bot] Mystery Box / Confirm -> กดปุ่มกลางล่าง")
                    adb.tap(*POST_GAME_BTN)
                    time.sleep(0.8)
                elif args.loop and (is_lobby(img) or is_buy(img)):
                    last_screen_t = now
                    handled = True
                    if feature_enabled("double_coins"):
                        print("[bot] --loop: อยู่หน้าเมนู -> เตรียม Double Coins แล้วเริ่มด่านใหม่")
                    else:
                        print("[bot] --loop: อยู่หน้าเมนู -> กด Play (ข้าม Double Coins)")
                    prepare_for_run(adb, want_play=True,
                                    use_double_coins=feature_enabled("double_coins"),
                                    stop_event=stop_event)
                    if stop_event is not None and stop_event.is_set():
                        break
                    time.sleep(3.0)

            if handled:
                unknown_since = 0.0
                prev_jump = prev_slide = False
                continue

            if is_in_game(img):
                # --- อยู่ในด่าน ---
                unknown_since = 0.0

                if args.pattern:
                    print(f"[bot] เข้าด่าน -> เล่นตาม pattern '{args.pattern}' (lead={args.lead}ms)")
                    status = play_pattern(adb, args.pattern, lead_ms=args.lead,
                                          jump_gap_ms=jump_gap,
                                          wait_anchor=False, verbose=True,
                                          watch_relay=feature_enabled("relay_boost"),
                                          watch_surprise=feature_enabled("surprise_card"),
                                          stop_event=stop_event)
                    prev_jump = prev_slide = False
                    if status == "stopped":
                        # ผู้ใช้กดหยุด -> ออกจากลูปหลักทันที
                        break
                    if status == "game_over":
                        # pattern หยุดกลางคัน -> ลูปจัดการ Result/กล่อง/lobby ต่อ
                        continue
                    continue

                # --- โหมด react สด: ตรวจอุปสรรคและสั่งกระโดด/สไลด์ ---
                result = detector.detect(img)
                cooled = now - last_action_t >= config.ACTION_COOLDOWN_S
                # trigger เฉพาะ "ขอบขาขึ้น" (เพิ่งเริ่มเจออุปสรรค) เพื่อไม่ให้กดรัว
                jump_edge = result.jump and not prev_jump
                slide_edge = result.slide and not prev_slide
                if cooled:
                    order = ("jump", "slide") if args.prefer == "jump" else ("slide", "jump")
                    for action in order:
                        if action == "jump" and jump_edge:
                            adb.jump()
                            last_action_t = now
                            print(f"[bot] JUMP  (score={result.jump_score:.3f}) "
                                  f"-> tap ({config.TAP_X},{config.TAP_Y})")
                            break
                        if action == "slide" and slide_edge:
                            adb.slide()
                            last_action_t = now
                            print(f"[bot] SLIDE (score={result.slide_score:.3f})")
                            break
                prev_jump, prev_slide = result.jump, result.slide
                if now - last_status_t >= 1.5:
                    last_status_t = now
                    print(f"[bot] เล่นอยู่... jump={result.jump_score:.3f} "
                          f"slide={result.slide_score:.3f} (threshold={config.MOTION_THRESHOLD})")
            else:
                # --- ไม่ใช่หน้าที่รู้จัก และไม่ได้อยู่ในด่าน ---
                prev_jump = prev_slide = False
                # มินิเกมการ์ดบังปุ่ม Jump -> is_in_game เป็น False แต่ต้องแก้การ์ด
                if feature_enabled("surprise_card") and not (is_lobby(img) or is_buy(img)) and is_surprise_card(img):
                    print("[bot] Surprise Card (หน้าจอพิเศษ) -> แก้อัตโนมัติ")
                    handle_surprise_card(adb, img)
                    unknown_since = 0.0
                    time.sleep(0.5)
                    continue
                if args.loop:
                    if unknown_since == 0.0:
                        unknown_since = now
                    elif now - unknown_since > 4.0:
                        # อย่ากด Back ถ้าน่าจะเป็นมินิเกมการ์ด (กันกดพลาดออกจากเกม)
                        if feature_enabled("surprise_card") and not (is_lobby(img) or is_buy(img)) and is_surprise_card(img):
                            unknown_since = 0.0
                            continue
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


def main():
    run_bot_from_argv(sys.argv[1:])


if __name__ == "__main__":
    main()
