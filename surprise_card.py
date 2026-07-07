"""
มินิเกม Surprise Card — หากลุ่มการ์ดที่น้อยกว่าแล้วกดอัตโนมัติ

ไม่ใช้ template ท่าทางตัวละคร (เปลี่ยนทุกรอบ) แต่ crop การ์ด 6 ใบจากจอ
แล้วจัดกลุ่มจากความเหมือนคู่กัน (connected components)

การ์ด 1 ใช้เป็นตัวอย่างเทียบเท่านั้น — ไม่เคยอยู่ในรายการกด

ใช้งาน:
    python surprise_card.py                  # แก้จากจอจริงผ่าน ADB
    python surprise_card.py --image shot.png # ทดสอบจากภาพ
    python surprise_card.py --debug          # แสดงคะแนนความเหมือน
"""
from __future__ import annotations

import argparse
import time

import cv2
import numpy as np

import config
from adb_controller import ADBController
from detector import roi_to_pixels
from runtime import set_surprise_cooldown, surprise_on_cooldown

STATE_DIR = config.TEMPLATE_DIR / "states"

# layout fallback อ้างอิงจอแนวนอน 1920x1080 (ใช้เมื่อ auto-detect ไม่เจอ)
REF_W, REF_H = 1024, 589
_CARD_PAD = 18

_CARD_OUTER_REF = [
    (259, 184, 397, 365),
    (407, 184, 544, 365),
    (554, 184, 692, 365),
    (259, 377, 397, 558),
    (407, 377, 544, 558),
    (554, 377, 692, 558),
]

CARD_INNER = tuple(
    ((x1 + _CARD_PAD) / REF_W, (y1 + _CARD_PAD) / REF_H,
     (x2 - _CARD_PAD) / REF_W, (y2 - _CARD_PAD) / REF_H)
    for x1, y1, x2, y2 in _CARD_OUTER_REF
)
CARD_TAP = tuple(
    ((x1 + x2) / 2 / REF_W, (y1 + y2) / 2 / REF_H)
    for x1, y1, x2, y2 in _CARD_OUTER_REF
)

THR_DETECT = 0.55          # ใช้เมื่อเจอ grid การ์ด 6 ใบแล้ว
THR_DETECT_FALLBACK = 0.92  # ไม่เจอ grid ต้อง match banner สูงมาก
TAP_DELAY_S = 2.0

_DETECT_TEMPLATES: list[np.ndarray] | None = None


def _detect_templates() -> list[np.ndarray]:
    global _DETECT_TEMPLATES
    if _DETECT_TEMPLATES is None:
        names = ("surprise_banner", "surprise_card", "surprise_card_jumping")
        loaded = []
        for name in names:
            p = STATE_DIR / f"{name}.png"
            if p.is_file():
                t = cv2.imread(str(p), cv2.IMREAD_COLOR)
                if t is not None:
                    loaded.append(t)
        _DETECT_TEMPLATES = loaded
    return _DETECT_TEMPLATES


def _banner_score(img: np.ndarray) -> float:
    best = 0.0
    for tpl in _detect_templates():
        if tpl.shape[0] > img.shape[0] or tpl.shape[1] > img.shape[1]:
            continue
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        best = max(best, float(cv2.minMaxLoc(res)[1]))
    return best


def _looks_like_card(crop: np.ndarray) -> bool:
    """การ์ดจริงมีพื้นครีมสว่าง + ขอบน้ำตาล — กรอง UI lobby"""
    if crop is None or crop.size == 0:
        return False
    h, w = crop.shape[:2]
    if h < 20 or w < 20:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    inner = hsv[h // 4:3 * h // 4, w // 4:3 * w // 4]
    v = float(inner[:, :, 2].mean())
    edge = np.vstack([
        hsv[0:4, :, :].reshape(-1, 3),
        hsv[-4:, :, :].reshape(-1, 3),
        hsv[:, 0:4, :].reshape(-1, 3),
        hsv[:, -4:, :].reshape(-1, 3),
    ])
    eh, es = float(edge[:, 0].mean()), float(edge[:, 1].mean())
    return v > 120 and 5 < eh < 35 and es > 28


def _has_tries_bar(img: np.ndarray) -> bool:
    """แถบน้ำตาล 'Tries left' ใต้หัวมินิเกม"""
    h, w = img.shape[:2]
    band = img[int(h * 0.20):int(h * 0.32), int(w * 0.35):int(w * 0.65)]
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    brown = ((hsv[:, :, 0] > 5) & (hsv[:, :, 0] < 25)
             & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 60) & (hsv[:, :, 2] < 180))
    return float(brown.mean()) > 0.06


def _confirm_minigame(img: np.ndarray,
                      boxes: list[tuple[int, int, int, int]]) -> bool:
    """ยืนยันว่า grid ที่เจอเป็นการ์ดจริง ไม่ใช่ UI lobby"""
    n = len(boxes)
    if n not in (5, 6):
        return False
    card_like = sum(_looks_like_card(_inner_crop(img, b)) for b in boxes)
    if card_like >= n:
        return True
    if card_like >= n - 1 and _has_tries_bar(img):
        return True
    return False


def is_surprise_card(img: np.ndarray) -> bool:
    """อยู่หน้ามินิเกม Surprise Card หรือไม่"""
    if surprise_on_cooldown():
        return False
    boxes = detect_card_boxes(img)
    if boxes is None:
        return False
    return _confirm_minigame(img, boxes)


def _box_centers(boxes: list[tuple[int, int, int, int]]) -> list[tuple[float, float, float, float]]:
    return [((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)
            for x1, y1, x2, y2 in boxes]


def _split_rows(boxes: list[tuple[int, int, int, int]]
                ) -> tuple[list[tuple[int, int, int, int]],
                           list[tuple[int, int, int, int]]]:
    """แบ่งกรอบเป็นแถวบน/ล่างจากช่องว่างแนวตั้งใหญ่สุด"""
    tagged = list(zip(_box_centers(boxes), boxes))
    ys = sorted(c[0][1] for c in tagged)
    gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
    mid = gaps.index(max(gaps))
    threshold = (ys[mid] + ys[mid + 1]) / 2
    top = sorted((b for c, b in tagged if c[1] < threshold), key=lambda b: (b[0] + b[2]) / 2)
    bot = sorted((b for c, b in tagged if c[1] >= threshold), key=lambda b: (b[0] + b[2]) / 2)
    return top, bot


def _sizes_ok(boxes: list[tuple[int, int, int, int]]) -> bool:
    centers = _box_centers(boxes)
    widths = [c[2] for c in centers]
    heights = [c[3] for c in centers]
    n = len(boxes)
    w_avg = sum(widths) / n
    h_avg = sum(heights) / n
    if w_avg < 40 or h_avg < 40:
        return False
    if max(widths) > w_avg * 1.4 or min(widths) < w_avg * 0.6:
        return False
    if max(heights) > h_avg * 1.4 or min(heights) < h_avg * 0.6:
        return False
    return True


def _valid_card_grid(boxes: list[tuple[int, int, int, int]]) -> bool:
    """ตรวจว่า 6 กรอบเรียงเป็น grid 2x3 (ไม่ใช่ UI อื่นที่ happen มีกล่องขาว)"""
    if len(boxes) != 6:
        return False
    top, bot = _split_rows(boxes)
    if len(top) != 3 or len(bot) != 3:
        return False
    return _sizes_ok(boxes)


def _valid_card_grid_5(boxes: list[tuple[int, int, int, int]]) -> bool:
    """ตรวจว่า 5 กรอบเรียง 2 บน + 3 ล่าง (layout มินิเกมบางรอบ)"""
    if len(boxes) != 5:
        return False
    top, bot = _split_rows(boxes)
    if len(top) != 2 or len(bot) != 3:
        return False
    return _sizes_ok(boxes)


def _valid_card_grid_5_alt(boxes: list[tuple[int, int, int, int]]) -> bool:
    """ตรวจว่า 5 กรอบเรียง 3 บน + 2 ล่าง"""
    if len(boxes) != 5:
        return False
    top, bot = _split_rows(boxes)
    if len(top) != 3 or len(bot) != 2:
        return False
    return _sizes_ok(boxes)


def _order_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """เรียงการ์ดซ้าย→ขวา บน→ล่าง (1..N)"""
    top, bot = _split_rows(boxes)
    return top + bot


def _card_size_limits(w: int, h: int) -> tuple[int, int, int, int]:
    """ขอบเขตกว้าง/สูงของกรอบการ์ดตามขนาดจอ (ADB 1080p การ์ดสูง ~325px)"""
    return (
        max(40, int(w * 0.035)),
        int(w * 0.22),
        max(40, int(h * 0.045)),
        int(h * 0.38),
    )


def _find_boxes_at_threshold(img: np.ndarray, thr: int) -> list[tuple[int, int, int, int]]:
    h, w = img.shape[:2]
    min_w, max_w, min_h, max_h = _card_size_limits(w, h)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = (gray > thr).astype(np.uint8) * 255
    ox, oy = int(w * 0.10), int(h * 0.15)
    roi = mask[oy:int(h * 0.92), ox:int(w * 0.90)]
    contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    row_step = max(60, int(h * 0.08))
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if min_w < bw < max_w and min_h < bh < max_h:
            boxes.append((x + ox, y + oy, x + ox + bw, y + oy + bh))
    boxes.sort(key=lambda b: (round((b[1] + b[3]) / 2 / row_step), (b[0] + b[2]) / 2))
    return boxes


def detect_card_boxes(img: np.ndarray) -> list[tuple[int, int, int, int]] | None:
    """หากรอบการ์ด 5 หรือ 6 ใบจากภาพ (x1,y1,x2,y2) หรือ None ถ้าหาไม่ครบ"""
    from itertools import combinations

    def _pick(boxes: list[tuple[int, int, int, int]], n: int,
              validator) -> list[tuple[int, int, int, int]] | None:
        if len(boxes) == n and validator(boxes):
            return _order_boxes(boxes)
        if len(boxes) > n:
            for pick in combinations(boxes, n):
                if validator(list(pick)):
                    return _order_boxes(list(pick))
        return None

    for thr in (205, 210, 215, 220, 225, 230, 235):
        boxes = _find_boxes_at_threshold(img, thr)
        found = _pick(boxes, 6, _valid_card_grid)
        if found:
            return found
        found = _pick(boxes, 5, _valid_card_grid_5)
        if found:
            return found
        found = _pick(boxes, 5, _valid_card_grid_5_alt)
        if found:
            return found
    return None


def _crop_roi(img: np.ndarray, roi: tuple[float, float, float, float]) -> np.ndarray:
    h, w = img.shape[:2]
    x1, y1, x2, y2 = roi_to_pixels(roi, w, h)
    return img[y1:y2, x1:x2]


def _inner_crop(img: np.ndarray, box: tuple[int, int, int, int],
                pad: int = _CARD_PAD) -> np.ndarray:
    x1, y1, x2, y2 = box
    return img[y1 + pad:y2 - pad, x1 + pad:x2 - pad]


def extract_cards(img: np.ndarray) -> tuple[list[np.ndarray],
                                           list[tuple[int, int, int, int]]]:
    """คืน (รูปการ์ด 6 ใบ, กรอบการ์ดสำหรับแตะ)"""
    boxes = detect_card_boxes(img)
    if boxes is not None:
        return [_inner_crop(img, b) for b in boxes], boxes

    h, w = img.shape[:2]
    fallback_boxes: list[tuple[int, int, int, int]] = []
    cards: list[np.ndarray] = []
    for inner, tap in zip(CARD_INNER, CARD_TAP):
        cards.append(_crop_roi(img, inner))
        tcx, tcy = int(tap[0] * w), int(tap[1] * h)
        fallback_boxes.append((tcx - 1, tcy - 1, tcx + 1, tcy + 1))
    return cards, fallback_boxes


def crop_cards(img: np.ndarray) -> list[np.ndarray]:
    return extract_cards(img)[0]


def card_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """คะแนนความเหมือน 0–1 (สูง = เหมือน)"""
    ah, aw = a.shape[:2]
    if ah < 4 or aw < 4:
        return 0.0
    b2 = cv2.resize(b, (aw, ah), interpolation=cv2.INTER_AREA)
    ha = cv2.calcHist([cv2.cvtColor(a, cv2.COLOR_BGR2HSV)], [0, 1], None,
                       [32, 32], [0, 180, 0, 256])
    hb = cv2.calcHist([cv2.cvtColor(b2, cv2.COLOR_BGR2HSV)], [0, 1], None,
                       [32, 32], [0, 180, 0, 256])
    cv2.normalize(ha, ha)
    cv2.normalize(hb, hb)
    hist = float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))
    tmpl = float(cv2.matchTemplate(a, b2, cv2.TM_CCOEFF_NORMED)[0, 0])
    return 0.4 * hist + 0.6 * tmpl


def _pairwise_matrix(cards: list[np.ndarray]) -> list[list[float]]:
    n = len(cards)
    mat = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            s = card_similarity(cards[i], cards[j])
            mat[i][j] = mat[j][i] = s
    return mat


def _cluster_at_threshold(mat: list[list[float]], thr: float) -> list[list[int]]:
    n = len(mat)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if mat[i][j] >= thr:
                union(i, j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _group_cohesion(mat: list[list[float]], group: list[int]) -> float:
    if len(group) < 2:
        return 1.0
    total = 0.0
    count = 0
    for a in range(len(group)):
        for b in range(a + 1, len(group)):
            total += mat[group[a]][group[b]]
            count += 1
    return total / count


def solve(img: np.ndarray, ref_idx: int = 0, debug: bool = False) -> list[int]:
    """คืนเลขการ์ด 1–N ที่ต้องกด (กลุ่มน้อยกว่า, ไม่รวม sample)"""
    cards, _ = extract_cards(img)
    n = len(cards)
    if n < 5:
        return []

    mat = _pairwise_matrix(cards)
    ref_num = ref_idx + 1
    thresholds = sorted({mat[i][j] for i in range(n) for j in range(i + 1, n)})

    best_minor: list[int] | None = None
    best_score = -1e9
    for thr in thresholds:
        groups = _cluster_at_threshold(mat, thr)
        if len(groups) != 2:
            continue
        g1, g2 = groups
        if len(g1) > len(g2):
            g1, g2 = g2, g1
        minor, major = g1, g2
        if len(minor) not in (1, 2):
            continue
        score = _group_cohesion(mat, minor) + _group_cohesion(mat, major)
        if score > best_score:
            best_score = score
            best_minor = minor

    if best_minor is None:
        return []

    answer = sorted(i + 1 for i in best_minor if i + 1 != ref_num)

    if debug:
        print(f"  cards={n}")
        print("  pairwise (1-based):")
        for i in range(n):
            print(f"    card {i + 1}:",
                  [round(mat[i][j], 2) for j in range(n)])
        print(f"  กลุ่มน้อย (0-based)={best_minor} score={best_score:.3f}")
        print(f"  -> กดการ์ด (ไม่รวม sample {ref_num}): {answer}")

    return answer


def _tap_center(box: tuple[int, int, int, int]) -> tuple[int, int]:
    """จุดกดกลางการ์ด — bright-mask มักเยื้องขึ้น เลย bias ลงเล็กน้อย"""
    x1, y1, x2, y2 = box
    h = y2 - y1
    cx = (x1 + x2) // 2
    cy = y1 + int(h * 0.58)
    return cx, cy


def tap_points(img: np.ndarray, indices: list[int],
               boxes: list[tuple[int, int, int, int]] | None = None) -> list[tuple[int, int]]:
    if boxes is None:
        _, boxes = extract_cards(img)
    pts = []
    for idx in indices:
        if 1 <= idx <= len(boxes):
            pts.append(_tap_center(boxes[idx - 1]))
    return pts


def _still_in_minigame(img: np.ndarray) -> bool:
    """ตรวจแบบผ่อน — ใช้ระหว่างกดการ์ดหลายใบ (แอนิเมชันอาจทำให้ grid หายชั่วคราว)"""
    if surprise_on_cooldown():
        return False
    boxes = detect_card_boxes(img)
    if boxes is not None:
        return True
    if _has_tries_bar(img):
        return True
    return _banner_score(img) >= 0.68


def _tap_one_card(adb, idx: int, boxes: list[tuple[int, int, int, int]],
                  verbose: bool, *, verify: bool = True) -> bool:
    """กดการ์ดหนึ่งใบ — verify=False ใช้พิกัดเดิม (กดใบถัดไปหลังแอนิเมชัน)"""
    use = boxes
    if verify:
        for attempt in range(3):
            img = adb.screencap()
            if _still_in_minigame(img):
                fresh = detect_card_boxes(img)
                if fresh is not None and len(fresh) == len(boxes):
                    use = fresh
                break
            if attempt < 2:
                time.sleep(0.35)
        else:
            return False
    if idx > len(use):
        return False
    x, y = _tap_center(use[idx - 1])
    adb.single_tap(x, y)
    if verbose:
        print(f"[surprise]   กดการ์ด {idx} ที่ ({x}, {y})")
    return True


def handle_surprise_card(adb, img: np.ndarray | None = None,
                         verbose: bool = True, debug: bool = False) -> bool:
    """แก้มินิเกมถ้าเจอหน้าจอ — คืน True ถ้าจัดการแล้ว"""
    if img is None:
        img = adb.screencap()
    if not is_surprise_card(img):
        return False

    boxes = detect_card_boxes(img)
    if boxes is None or not _confirm_minigame(img, boxes):
        if verbose:
            print("[surprise] ข้าม — ไม่ใช่หน้าการ์ดจริง (อาจเป็น lobby/UI อื่น)")
        return False

    time.sleep(0.35)
    img = adb.screencap()
    boxes = detect_card_boxes(img)
    if boxes is None or not _confirm_minigame(img, boxes):
        return False

    cards = [_inner_crop(img, b) for b in boxes]
    indices = solve(img, debug=debug)
    if not indices:
        if verbose:
            print("[surprise] แก้ไม่ได้ — ไม่รู้ว่าต้องกดการ์ดไหน")
        return False

    pts = tap_points(img, indices, boxes)
    if verbose:
        print(f"[surprise] กดการ์ด {indices} (การ์ด 1 = sample ไม่กด)")
        for i, (x, y) in enumerate(pts, 1):
            print(f"[surprise]   #{i} การ์ด {indices[i - 1]} -> ({x}, {y})")
    for i, idx in enumerate(indices):
        ok = _tap_one_card(adb, idx, boxes, verbose=verbose,
                           verify=(i == 0))
        if not ok:
            if verbose:
                print(f"[surprise] หยุด — ออกจากหน้าการ์ดแล้ว (ไม่กดการ์ด {idx})")
            break
        if i + 1 < len(indices):
            time.sleep(TAP_DELAY_S)

    for _ in range(15):
        time.sleep(0.3)
        if not is_surprise_card(adb.screencap()):
            break
    set_surprise_cooldown(5.0)
    return True


def main():
    parser = argparse.ArgumentParser(description="Surprise Card minigame solver")
    parser.add_argument("--image", help="ทดสอบจากไฟล์ภาพแทน ADB")
    parser.add_argument("--debug", action="store_true", help="แสดงคะแนนความเหมือน")
    args = parser.parse_args()

    if args.image:
        img = cv2.imread(args.image)
        if img is None:
            print(f"อ่านภาพไม่ได้: {args.image}")
            return
        print("banner score:", round(_banner_score(img), 3))
        print("is_surprise:", is_surprise_card(img))
        print("detect boxes:", len(detect_card_boxes(img) or []))
        solve(img, debug=True)
        return

    adb = ADBController()
    if not adb.connect():
        return
    img = adb.screencap()
    if not is_surprise_card(img):
        print("ไม่เจอหน้า Surprise Card (banner score:",
              round(_banner_score(img), 3), ")")
        return
    handle_surprise_card(adb, img, debug=args.debug)


if __name__ == "__main__":
    main()
