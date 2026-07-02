"""
Macro อัตโนมัติก่อนเริ่มเล่น Cookie Run Classic (LDPlayer/ADB)

ลำดับงาน:
  1) ถ้าอยู่หน้าหลัก (lobby)         -> กด Play!  เข้าหน้า Buy Upgrades
  2) ถ้าอยู่หน้า Buy Upgrades         -> กดปุ่ม Multi เปิด modal เลือกบูสต์
  3) ใน modal                         -> กด Multi-Buy (เกมจะวนซื้อสุ่มเองจน
                                          ได้บูสต์ที่เลือก = Double Coins)
  4) เสร็จเมื่อกลับมาหน้า Buy Upgrades พร้อมแบนเนอร์ "Double Coins" เหนือปุ่ม Play

ใช้งาน:
    python auto_lobby.py            # เตรียม Double Coins อย่างเดียว
    python auto_lobby.py --play     # เตรียมเสร็จแล้วกด Play เริ่มด่านต่อ
    python auto_lobby.py --debug    # พิมพ์คะแนน match ของแต่ละสถานะ

ตรวจสถานะหน้าจอด้วย template ใน templates/states/ (สร้างด้วย make_templates.py)
ทุกพิกัด/ภาพอ้างอิงความละเอียดจริง 1920x1080
"""
from __future__ import annotations

import argparse
import time

import cv2

import config
from adb_controller import ADBController

# ---- พิกัดปุ่ม (1920x1080) ----
LOBBY_PLAY = (1434, 966)      # ปุ่ม Play! หน้าหลัก
BUY_MULTI = (1646, 338)       # ปุ่ม Multi (ชมพู) หน้า Buy Upgrades
BUY_RANDOM_ITEM = (802, 881)  # กล่อง "?" Random Boost ในตาราง (ต้องเลือกก่อนปุ่ม Multi จะโผล่)
MODAL_MULTI_BUY = (953, 883)  # ปุ่ม Multi-Buy ใน modal
BUY_PLAY = (1350, 920)        # ปุ่ม Play! หน้า Buy Upgrades
RELAY_TAP = (960, 540)        # กลางจอ -- ใช้ตอน "Tap to activate Cookie Relay Boost!"
RESULT_OK = (692, 930)        # ปุ่ม OK หน้า Result ตอนจบเกม
POST_GAME_BTN = (960, 966)    # ปุ่มกลางล่าง: Open all / Confirm (Mystery Box, เลเวลอัพ)

STATE_DIR = config.TEMPLATE_DIR / "states"
THR = 0.80
THR_DC = 0.82
THR_RELAY = 0.60   # ข้อความ relay มีพื้นหลังด่านต่างกัน จึงตั้งไว้ต่ำกว่า
THR_RESULT = 0.82
THR_INGAME = 0.62  # ปุ่ม Jump กึ่งโปร่งใส พื้นหลังด่านต่างกัน จึงตั้งไว้ต่ำ

DEBUG = False


def _load(name):
    p = STATE_DIR / f"{name}.png"
    if not p.is_file():
        raise FileNotFoundError(
            f"ไม่พบ template {p} -- รัน `python make_templates.py` ก่อน")
    t = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if t is None:
        raise FileNotFoundError(
            f"อ่าน template ไม่ได้ {p} -- ไฟล์เสียหายหรือ path ผิด")
    return t


_T = {}


def _templates():
    if not _T:
        for n in ("lobby_marker", "buy_title", "modal_multibuy", "double_coins",
                  "relay_boost", "result_title", "multi_btn", "in_game",
                  "mystery_box", "confirm_btn"):
            _T[n] = _load(n)
    return _T


def _score(img, tpl) -> float:
    if tpl.shape[0] > img.shape[0] or tpl.shape[1] > img.shape[1]:
        return 0.0
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(res)[1])


def _scores(img) -> dict:
    t = _templates()
    return {n: _score(img, tpl) for n, tpl in t.items()}


def is_lobby(img):
    return _score(img, _templates()["lobby_marker"]) >= THR


def is_buy(img):
    return _score(img, _templates()["buy_title"]) >= THR


def is_modal(img):
    return _score(img, _templates()["modal_multibuy"]) >= THR


def has_double_coins(img):
    return _score(img, _templates()["double_coins"]) >= THR_DC


def is_relay_boost(img):
    return _score(img, _templates()["relay_boost"]) >= THR_RELAY


def is_result(img):
    return _score(img, _templates()["result_title"]) >= THR_RESULT


def has_multi_btn(img):
    """ปุ่ม Multi จะโผล่เฉพาะตอนเลือกไอเทม Random Boost (กล่อง '?')"""
    return _score(img, _templates()["multi_btn"]) >= THR


def is_in_game(img):
    """อยู่ในด่านวิ่งจริง (เจอปุ่ม Jump มุมซ้ายล่าง)"""
    return _score(img, _templates()["in_game"]) >= THR_INGAME


def is_mystery_box(img):
    """หน้า Mystery Box หลังจบเกม (ปุ่ม Open all / Confirm)"""
    return _score(img, _templates()["mystery_box"]) >= THR


def is_confirm(img):
    """มีปุ่ม Confirm กลางล่าง (รางวัล/เลเวลอัพ)"""
    return _score(img, _templates()["confirm_btn"]) >= THR


def wait_for(adb, pred, timeout=30.0, interval=0.6):
    """รอจนกว่า pred(img) เป็นจริง หรือหมดเวลา คืน img ที่ผ่านเงื่อนไข หรือ None"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        img = adb.screencap()
        if pred(img):
            return img
        time.sleep(interval)
    return None


def prepare_double_coins(adb, want_play=False, max_multibuy=5) -> bool:
    img = adb.screencap()
    if DEBUG:
        print("  scores:", {k: round(v, 2) for k, v in _scores(img).items()})

    # 1) หน้าหลัก -> Play
    if is_lobby(img) and not is_buy(img):
        print("[lobby] กด Play! เข้าหน้าซื้อ")
        adb.tap(*LOBBY_PLAY)
        wait_for(adb, lambda im: is_buy(im) or is_modal(im), timeout=8)

    # 2) มี Double Coins อยู่แล้ว?
    if has_double_coins(adb.screencap()):
        print("[ok] มี Double Coins อยู่แล้ว")
    else:
        # 3) วนจัดการจนได้ Double Coins (มี deadline + กู้คืนหน้าจอแปลกด้วย Back)
        deadline = time.time() + 75
        buys = 0
        unknown = 0
        while time.time() < deadline and buys < max_multibuy:
            cur = adb.screencap()
            if has_double_coins(cur):
                break
            if is_modal(cur):
                buys += 1
                print(f"[modal] กด Multi-Buy ครั้งที่ {buys} (รอเกมวนซื้อจนได้ Double Coins)")
                adb.tap(*MODAL_MULTI_BUY)
                if wait_for(adb, has_double_coins, timeout=35) is not None:
                    break
                unknown = 0
            elif is_buy(cur):
                if not has_multi_btn(cur):
                    print("[buy] ยังไม่ได้เลือก Random Boost -> กดกล่อง ? ก่อน")
                    adb.tap(*BUY_RANDOM_ITEM)
                    wait_for(adb, has_multi_btn, timeout=5)
                print("[buy] กดปุ่ม Multi เปิด modal")
                adb.tap(*BUY_MULTI)
                wait_for(adb, is_modal, timeout=6)
                unknown = 0
            elif is_lobby(cur):
                print("[lobby] กด Play! เข้าหน้าซื้อ")
                adb.tap(*LOBBY_PLAY)
                wait_for(adb, is_buy, timeout=8)
                unknown = 0
            else:
                # หน้าจอไม่รู้จัก (ป๊อปอัพ/เมนูอื่น) -> กด Back เพื่อกลับ
                unknown += 1
                print(f"[recover] หน้าจอไม่รู้จัก -> กด Back ({unknown})")
                adb.back()
                time.sleep(1.0)
                if unknown >= 6:
                    print("[warn] ออกจากหน้าจอที่ไม่รู้จักไม่ได้ ยกเลิกการเตรียม")
                    break

    ok = has_double_coins(adb.screencap())
    if ok:
        print("[done] พร้อมแล้ว: Double Coins อยู่บนปุ่ม Play")
    else:
        print("[warn] ยังไม่ได้ Double Coins (เหรียญพอไหม / template ตรงไหม) ลอง --debug")

    # 4) เริ่มด่านต่อถ้าต้องการ
    if want_play:
        print("[play] กด Play! เริ่มด่าน")
        adb.tap(*BUY_PLAY)
    return ok


def main():
    global DEBUG
    parser = argparse.ArgumentParser(description="Cookie Run lobby macro: เตรียม Double Coins อัตโนมัติ")
    parser.add_argument("--play", action="store_true", help="กด Play เริ่มด่านหลังเตรียมเสร็จ")
    parser.add_argument("--debug", action="store_true", help="พิมพ์คะแนน match ของแต่ละสถานะ")
    parser.add_argument("--max-buys", type=int, default=5, help="จำนวนครั้งสูงสุดที่กด Multi-Buy")
    args = parser.parse_args()
    DEBUG = args.debug

    adb = ADBController()
    if not adb.connect():
        return
    prepare_double_coins(adb, want_play=args.play, max_multibuy=args.max_buys)


if __name__ == "__main__":
    main()
