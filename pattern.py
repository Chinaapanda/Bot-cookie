"""
ระบบ "อัด & เล่นซ้ำ" จังหวะการเล่น (record & replay pattern)

แนวคิด: ด่านวิ่งใน Cookie Run Classic เป็น fixed pattern (อุปสรรควาง
ตำแหน่งเดิมทุกรอบของแต่ละ episode) ดังนั้นถ้าเราอัด "จังหวะกระโดด/สไลด์"
ที่ดีไว้ 1 รอบ แล้วเล่นซ้ำตาม timeline เดิม จะผ่านด่านและเก็บเหรียญได้
สม่ำเสมอกว่าการ react สด ๆ มาก

วิธีอัด (เล่นเองผ่านคีย์บอร์ดของคอม ส่งคำสั่งไปเกม + บันทึกเวลาให้อัตโนมัติ):
    python pattern.py record ชื่อด่าน
        W / J / Space = กระโดด
        D         = double jump (กระโดดสองชั้น)
        K / S     = สไลด์ (มุด)
        Q / Esc   = จบและบันทึก

วิธีเล่นซ้ำ:
    python pattern.py play ชื่อด่าน                 # เล่น 1 รอบ
    python pattern.py play ชื่อด่าน --lead 80       # ยิง action เร็วขึ้น 80ms ชดเชย lag
    python pattern.py list                          # ดู pattern ที่มี

จุด anchor (จุดเริ่มจับเวลา) = ตอนที่ตรวจเจอว่า "เข้าด่านแล้ว" (is_in_game)
ทั้งตอนอัดและตอนเล่นใช้ anchor เดียวกัน เวลาจึงตรงกัน ถ้าจังหวะเพี้ยน
ให้ปรับ --lead (เพิ่ม = ยิงเร็วขึ้น)
"""
from __future__ import annotations

import argparse
import json
import re
import time

import config
from adb_controller import ADBController

try:
    import msvcrt  # คีย์บอร์ดแบบ non-blocking บน Windows
except ImportError:  # pragma: no cover - เผื่อรันบนระบบอื่น
    msvcrt = None

PATTERN_DIR = config.BASE_DIR / "patterns"
PATTERN_DIR.mkdir(exist_ok=True)


class GameOver(Exception):
    """จบเกมก่อน pattern เล่นครบ (เจอหน้า Result)"""


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------
def pattern_path(name: str):
    return PATTERN_DIR / f"{name}.json"


def load_pattern(name) -> dict:
    if isinstance(name, dict):
        return name
    p = pattern_path(name)
    if not p.exists():
        raise FileNotFoundError(f"ไม่พบ pattern: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def list_patterns() -> list[str]:
    return sorted(p.stem for p in PATTERN_DIR.glob("*.json"))


def sanitize_name(name: str) -> str:
    """ชื่อ pattern ที่ปลอดภัย (ใช้เป็นชื่อไฟล์)"""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "_", name)
    return name


def create_pattern(name: str) -> Path:
    """สร้าง pattern เปล่าใหม่"""
    name = sanitize_name(name)
    if not name:
        raise ValueError("ชื่อ pattern ว่างเปล่า")
    p = pattern_path(name)
    if p.exists():
        raise FileExistsError(f"มี pattern '{name}' อยู่แล้ว")
    data = {
        "name": name,
        "duration": 0,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "events": [],
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def rename_pattern(old_name: str, new_name: str) -> Path:
    """เปลี่ยนชื่อ pattern (ย้ายไฟล์ + อัปเดต name ใน JSON)"""
    old_name = sanitize_name(old_name)
    new_name = sanitize_name(new_name)
    if not old_name or not new_name:
        raise ValueError("ชื่อ pattern ว่างเปล่า")
    if old_name == new_name:
        return pattern_path(old_name)
    src = pattern_path(old_name)
    dst = pattern_path(new_name)
    if not src.exists():
        raise FileNotFoundError(f"ไม่พบ pattern: {old_name}")
    if dst.exists():
        raise FileExistsError(f"มี pattern '{new_name}' อยู่แล้ว")
    data = json.loads(src.read_text(encoding="utf-8"))
    data["name"] = new_name
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    src.unlink()
    # อัปเดต default_pattern ใน settings ถ้าตรงกับชื่อเดิม
    try:
        from settings import load, save
        cfg = load()
        if cfg.get("default_pattern") == old_name:
            cfg["default_pattern"] = new_name
            save(cfg)
    except Exception:
        pass
    return dst


def delete_pattern(name: str) -> None:
    """ลบ pattern"""
    name = sanitize_name(name)
    p = pattern_path(name)
    if not p.exists():
        raise FileNotFoundError(f"ไม่พบ pattern: {name}")
    p.unlink()


def _wait_in_game(adb, timeout: float = 60.0) -> bool:
    """รอจน 'เข้าด่าน' (is_in_game) เป็นจริง = จุด anchor เริ่มจับเวลา"""
    from auto_lobby import is_in_game  # import ช้าเพื่อเลี่ยง circular/โหลด template เร็วเกิน
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if is_in_game(adb.screencap()):
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------
# แมปปุ่ม -> action สำหรับโหมดสำรอง (msvcrt อ่านเป็นตัวอักษร)
_KEY_JUMP = ("w", "j", "space")
_KEY_DOUBLE = ("d",)
_KEY_SLIDE = ("k", "s")
_KEY_QUIT = ("q", "esc")

# โหมด global: แมปจาก "scan code" แทนตัวอักษร -> ไม่สนภาษาคีย์บอร์ด (ไทย/อังกฤษ)
# scan code มาตรฐาน (set 1) บน Windows
_SCAN_ACTION = {
    17: "jump",    # W
    36: "jump",    # J
    57: "jump",    # Space
    32: "jump",    # D  (จะ double jump ก็แค่กด jump สองที)
    31: "slide",   # S
    37: "slide",   # K
    16: "quit",    # Q
    1: "quit",     # Esc
}

# ระยะกดค้างเริ่มต้น (ms) เผื่อ pattern เก่าที่ไม่มีข้อมูล dur
_DEFAULT_TAP_MS = 60
# กันบันทึกกระโดดซ้ำจากคีย์บอร์ดเด้ง / ส่งซ้ำเร็วเกินไป
_JUMP_DEBOUNCE_S = 0.12


def _point(action: str):
    """จุดที่ต้องแตะของแต่ละ action"""
    if action == "slide":
        return (config.SLIDE_X, config.SLIDE_Y)
    return (config.TAP_X, config.TAP_Y)  # jump (และ double)


def _save_pattern(name, t0, events, quiet: bool = False) -> dict:
    data = {
        "name": name,
        "duration": round(time.time() - t0, 3),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "events": events,
    }
    pattern_path(name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not quiet:
        print(f"[record] บันทึก {len(events)} จังหวะ ({data['duration']}s) -> {pattern_path(name)}")
    return data


def record_pattern(adb, name: str, wait_anchor: bool = True) -> dict:
    print(f"[record] เตรียมอัด pattern '{name}'")
    if wait_anchor:
        print("[record] รอเข้าด่าน... (กด Play ในเกมได้เลย)")
        if not _wait_in_game(adb):
            print("[record] ไม่พบว่าเข้าด่านภายในเวลาที่กำหนด ยกเลิก")
            return {}

    # พยายามใช้ global keyboard hook ก่อน (จับปุ่มได้แม้โฟกัสอยู่หน้าต่างเกม)
    try:
        import keyboard  # noqa: F401
        return _record_global(adb, name)
    except ImportError:
        print("[record] ไม่พบไลบรารี 'keyboard' -> ใช้โหมดสำรอง (ต้องโฟกัสที่หน้าต่าง Terminal นี้)")
        print("          ติดตั้งเพื่อกดในเกมได้เลย:  pip install keyboard")
        return _record_console(adb, name)


def _record_global(adb, name: str) -> dict:
    """อัดด้วย global hook: กดปุ่มที่ไหนก็ได้ (รวมถึงตอนโฟกัสหน้าต่างเกม)

    - อ่านจาก scan code -> ไม่สนภาษาคีย์บอร์ด (ไทย/อังกฤษ ก็กดได้)
    - จับเฉพาะ "กดลงครั้งแรก" ไม่เอา auto-repeat ตอนกดค้าง (กันบันทึกซ้ำ ๆ เอง)
    - เซฟทุกกรณี: กด Q, Ctrl+C, หรือจบเกม (หน้า Result) -> บันทึกอัตโนมัติ
    - auto-save ระหว่างทางทุก ~5 วินาที กันงานหาย
    """
    import keyboard
    try:
        from auto_lobby import is_result, is_relay_boost, RELAY_TAP
    except Exception:
        is_result = is_relay_boost = RELAY_TAP = None

    print("[record] เริ่มจับเวลา! (โหมด global — กดในเกมได้เลย ไม่ต้องคลิกกลับมาที่ Terminal)")
    print("  W/J/Space=กระโดด   K/S=สไลด์   (กดค้าง=ค้างจริง)   Q/Esc หรือ Ctrl+C=จบและบันทึก")
    print("  (Relay Boost ระบบแตะให้+จดเป็นจุด sync, จบเกมหยุด+เซฟอัตโนมัติ)")

    t0 = time.time()
    events: list[dict] = []
    held: dict[int, tuple] = {}   # scan code -> (t_down, action, point) ที่กดค้างอยู่
    stop = {"v": False, "reason": ""}
    last_jump_t = -1.0

    def on_event(e):
        nonlocal last_jump_t
        action = _SCAN_ACTION.get(e.scan_code)
        if action is None:
            return

        if e.event_type == keyboard.KEY_DOWN:
            if e.scan_code in held:
                return  # auto-repeat ตอนกดค้าง -> ข้าม
            if action == "quit":
                stop["v"] = True
                stop["reason"] = "กด Q/Esc"
                return
            t = round(time.time() - t0, 3)
            pt = _point(action)
            if action == "slide":
                held[e.scan_code] = (t, action, pt)
                adb.touch_down(*pt)  # มุด = กดค้างจริง (ปล่อยตอน key up)
            else:  # jump = แตะครั้งเดียว (อยากดับเบิลก็กดอีกที)
                if t - last_jump_t < _JUMP_DEBOUNCE_S:
                    return
                last_jump_t = t
                held[e.scan_code] = (t, action, pt)
                adb.single_tap(*pt)
                events.append({"t": t, "a": "jump"})
                print(f"  {t:6.2f}s  jump")
        else:  # KEY_UP
            info = held.pop(e.scan_code, None)
            if info is None:
                return
            t_down, action, pt = info
            if action == "slide":
                adb.touch_up(*pt)    # ยกนิ้ว = เลิกมุด
                dur = max(int(round((time.time() - t0 - t_down) * 1000)), 1)
                events.append({"t": t_down, "a": "slide", "dur": dur})
                print(f"  {t_down:6.2f}s  slide  (ค้าง {dur}ms)")

    # suppress=True กันคีย์ W/S ส่งเข้า LDPlayer ซ้ำ (ADB แตะให้แล้ว)
    keyboard.hook(on_event, suppress=True)

    last_save = 0.0
    last_check = 0.0
    relay_at = 0.0
    try:
        while not stop["v"]:
            time.sleep(0.05)
            now = time.time()
            if now - last_save >= 5.0 and events:
                last_save = now
                _save_pattern(name, t0, events, quiet=True)  # auto-save กันหาย
            if is_result is not None and now - last_check >= 0.3:
                last_check = now
                try:
                    img = adb.screencap()
                except Exception:
                    img = None
                if img is not None:
                    if is_result(img):
                        stop["v"] = True
                        stop["reason"] = "จบเกม (Result)"
                    elif is_relay_boost(img) and now - relay_at > 2.0:
                        # Relay Boost หยุดเกมรอแตะ -> แตะให้ + จดเป็นจุด re-sync
                        relay_at = now
                        t = round(now - t0, 3)
                        adb.tap(*RELAY_TAP)
                        events.append({"t": t, "a": "relay"})
                        print(f"  {t:6.2f}s  relay boost -> แตะกลางจอ (จุด sync)")
    except KeyboardInterrupt:
        stop["reason"] = "Ctrl+C"
    finally:
        keyboard.unhook_all()
        # ปล่อยปุ่มสไลด์ที่ยังกดค้างอยู่ตอนหยุด (กันนิ้วค้าง + บันทึกให้ครบ)
        for t_down, action, pt in list(held.values()):
            if action == "slide":
                adb.touch_up(*pt)
                dur = max(int(round((time.time() - t0 - t_down) * 1000)), 1)
                events.append({"t": t_down, "a": "slide", "dur": dur})
        held.clear()

    events.sort(key=lambda ev: ev["t"])
    print(f"[record] หยุด ({stop['reason'] or 'ไม่ทราบสาเหตุ'})")
    return _save_pattern(name, t0, events)


def _record_console(adb, name: str) -> dict:
    """โหมดสำรอง (msvcrt): อ่านปุ่มได้เฉพาะตอนโฟกัสที่หน้าต่าง Terminal นี้"""
    if msvcrt is None:
        raise RuntimeError("โหมดสำรองรองรับเฉพาะ Windows -- ติดตั้ง 'keyboard' แทน")

    print("[record] เริ่มจับเวลา! (คลิกที่หน้าต่าง Terminal นี้ก่อน แล้วค่อยกดปุ่ม)")
    print("  W/J/Space=กระโดด   D=double jump   K/S=สไลด์   Q/Esc หรือ Ctrl+C=จบและบันทึก")

    t0 = time.time()
    events: list[dict] = []
    try:
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getch().lower()
                t = round(time.time() - t0, 3)
                if ch in (b"q", b"\x1b"):
                    break
                if ch in (b"w", b"j", b" "):
                    adb.jump()
                    events.append({"t": t, "a": "jump"})
                    print(f"  {t:6.2f}s  jump")
                elif ch == b"d":
                    adb.double_jump()
                    events.append({"t": t, "a": "double"})
                    print(f"  {t:6.2f}s  double")
                elif ch in (b"k", b"s"):
                    adb.slide()
                    events.append({"t": t, "a": "slide"})
                    print(f"  {t:6.2f}s  slide")
            time.sleep(0.004)
    except KeyboardInterrupt:
        print("[record] หยุด (Ctrl+C)")

    return _save_pattern(name, t0, events)


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------
def _build_timeline(events: list[dict], base: float = 0.0) -> list[tuple]:
    """แปลง action events -> ลำดับคำสั่ง touch (เวลาเทียบ base, ชนิด, จุด, action, dur)

    แต่ละจังหวะ = นิ้วลง (down) ที่เวลา t แล้วยกขึ้น (up) ที่ t + dur
    (ไม่รวม event ชนิด 'relay' ซึ่งจัดการแยกเป็นจุด re-sync)
    """
    tl: list[tuple] = []
    for ev in events:
        a = ev["a"]
        if a == "relay":
            continue
        t = ev["t"] - base
        if a == "slide":
            pt = _point("slide")
            dur = ev.get("dur") or config.SLIDE_HOLD_MS
            tl.append((t, "down", pt, "slide", dur))
            tl.append((t + dur / 1000.0, "up", pt, "slide", dur))
        elif a == "double":  # รองรับ pattern เก่า: double = แตะสองที
            pt = _point("jump")
            tl.append((t, "jump", pt, "double", 0))
            tl.append((t + 0.08, "jump", pt, "double", 0))
        else:  # jump = แตะครั้งเดียว
            tl.append((t, "jump", _point("jump"), "jump", 0))
    tl.sort(key=lambda x: x[0])
    return tl


def _split_segments(events: list[dict]) -> list[tuple]:
    """แบ่ง events เป็นช่วง ๆ คั่นด้วย event 'relay'

    คืน list ของ (base_time, action_events, ends_with_relay)
    - base_time = เวลาเริ่มของช่วง (relative กับ t0 เดิม)
    - ends_with_relay = True ถ้าช่วงนี้จบด้วย Relay Boost (ต้องรอจอ relay แล้วแตะ)
    """
    segments: list[tuple] = []
    cur: list[dict] = []
    base = 0.0
    for ev in events:
        if ev["a"] == "relay":
            segments.append((base, cur, True))
            cur = []
            base = ev["t"]
        else:
            cur.append(ev)
    segments.append((base, cur, False))
    return segments


def _sleep_until(adb, target_t, t0, lead, watch_relay: bool, verbose: bool) -> None:
    """รอจนถึงเวลา target แต่เช็ค Relay Boost / หน้า Result ระหว่างทาง"""
    from auto_lobby import is_relay_boost, is_result, RELAY_TAP

    relay_at = 0.0
    while True:
        now = time.time()
        delay = (t0 + target_t - lead) - now
        if delay <= 0:
            break
        if now - relay_at > 0.8:
            try:
                img = adb.screencap()
                if is_result(img):
                    if verbose:
                        print("  -> หน้า Result (จบเกม) -> หยุด pattern")
                    raise GameOver()
                if watch_relay and is_relay_boost(img):
                    adb.tap(*RELAY_TAP)
                    relay_at = now
                    if verbose:
                        print("  -> Relay Boost (ระหว่างเล่น pattern)")
                    time.sleep(0.5)
                    continue
            except GameOver:
                raise
            except Exception:
                pass
        time.sleep(min(delay, 0.12))


def _play_timeline(adb, timeline, t0, lead, verbose, watch_relay: bool = True) -> None:
    for tt, typ, pt, a, dur in timeline:
        _sleep_until(adb, tt, t0, lead, watch_relay, verbose)
        if typ == "jump":
            adb.single_tap(*pt)
            if verbose:
                print(f"  {tt:6.2f}s -> {a}")
        elif typ == "down":
            adb.touch_down(*pt)
            if verbose:
                print(f"  {tt:6.2f}s -> {a} (ค้าง {dur}ms)")
        else:  # up
            adb.touch_up(*pt)
        # เช็คจบเกมหลัง action ด้วย (ตอบสนองเร็วขึ้น)
        try:
            from auto_lobby import is_result
            if is_result(adb.screencap()):
                if verbose:
                    print("  -> หน้า Result (จบเกม) -> หยุด pattern")
                raise GameOver()
        except GameOver:
            raise
        except Exception:
            pass


def play_pattern(adb, name, lead_ms: int = 0, wait_anchor: bool = True,
                 verbose: bool = True, watch_relay: bool = True) -> str | bool:
    """เล่น pattern คืน 'done' | 'game_over' | False (ล้มเหลว)"""
    from auto_lobby import is_relay_boost, RELAY_TAP

    data = load_pattern(name)
    events = sorted(data.get("events", []), key=lambda e: e["t"])
    if not events:
        print(f"[play] pattern '{data.get('name', name)}' ว่างเปล่า")
        return False

    if wait_anchor:
        if verbose:
            print("[play] รอเข้าด่าน...")
        if not _wait_in_game(adb):
            print("[play] ไม่พบว่าเข้าด่าน ยกเลิกการเล่น pattern")
            return False

    segments = _split_segments(events)
    lead = lead_ms / 1000.0
    if verbose:
        n_relay = sum(1 for e in events if e["a"] == "relay")
        print(f"[play] เล่นตาม pattern '{data.get('name', name)}' "
              f"({len(events) - n_relay} จังหวะ, {n_relay} จุด sync, lead={lead_ms}ms)")

    status = "done"
    try:
        for base, evs, ends_with_relay in segments:
            timeline = _build_timeline(evs, base=base)
            t0 = time.time()
            try:
                _play_timeline(adb, timeline, t0, lead, verbose, watch_relay)
            except GameOver:
                status = "game_over"
                break
            if ends_with_relay and status == "done":
                if verbose:
                    print("  ...รอ Relay Boost เพื่อ re-sync")
                got = _wait_for(adb, is_relay_boost, timeout=10.0)
                adb.tap(*RELAY_TAP)
                if verbose:
                    print(f"  -> แตะ Relay Boost ({'เจอจอ' if got else 'timeout เดาแตะ'})")
                time.sleep(0.6)
    finally:
        # ปล่อยเฉพาะสไลด์ที่อาจค้าง — อย่า touch_up จุดกระโดด (ทำให้กระโดดซ้ำ)
        adb.touch_up(*_point("slide"))

    if verbose:
        if status == "game_over":
            print("[play] หยุด pattern กลางคัน (จบเกม)")
        else:
            print("[play] จบ pattern")
    return status


def _wait_for(adb, pred, timeout=10.0, interval=0.2) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred(adb.screencap()):
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="อัด/เล่นซ้ำ pattern การเล่น Cookie Run")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="อัด pattern ใหม่ (คุมด้วยคีย์บอร์ด)")
    p_rec.add_argument("name", help="ชื่อ pattern เช่น ชื่อด่าน/episode")
    p_rec.add_argument("--no-wait", action="store_true", help="ไม่ต้องรอ anchor เริ่มจับเวลาทันที")

    p_play = sub.add_parser("play", help="เล่นซ้ำ pattern")
    p_play.add_argument("name", help="ชื่อ pattern")
    p_play.add_argument("--lead", type=int, default=0, help="ยิง action เร็วขึ้นกี่ ms (ชดเชย lag)")
    p_play.add_argument("--no-wait", action="store_true", help="ไม่ต้องรอ anchor เริ่มเล่นทันที")
    p_play.add_argument("--no-prep", action="store_true", help="ไม่เตรียม lobby/Play ก่อนเล่น")

    sub.add_parser("list", help="ดูรายการ pattern")

    args = parser.parse_args()

    if args.cmd == "list":
        names = list_patterns()
        if names:
            print("pattern ที่มี:")
            for n in names:
                d = load_pattern(n)
                print(f"  - {n}  ({len(d.get('events', []))} จังหวะ, {d.get('duration', '?')}s)")
        else:
            print("ยังไม่มี pattern (อัดด้วย: python pattern.py record <ชื่อ>)")
        return

    adb = ADBController()
    if not adb.connect():
        return

    if args.cmd == "record":
        record_pattern(adb, args.name, wait_anchor=not args.no_wait)
    elif args.cmd == "play":
        if not getattr(args, "no_prep", False):
            from auto_lobby import is_in_game, prepare_double_coins
            try:
                if not is_in_game(adb.screencap()):
                    print("[play] ยังไม่อยู่ในด่าน -> เตรียม Double Coins + กด Play")
                    prepare_double_coins(adb, want_play=True)
                    time.sleep(2.5)
            except Exception as e:
                print(f"[play] เตรียม lobby ล้มเหลว: {e}")
        play_pattern(adb, args.name, lead_ms=args.lead, wait_anchor=not args.no_wait)


if __name__ == "__main__":
    main()
