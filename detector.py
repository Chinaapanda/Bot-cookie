"""
ตัวตรวจจับอุปสรรคในเกม Cookie Run Classic
รองรับ 2 วิธี:
  - "motion"   : ดูการเปลี่ยนแปลงของภาพในโซน (ใช้ได้ทันที ไม่ต้องเตรียมรูป)
  - "template" : จับคู่รูปอุปสรรคที่เซฟไว้ในโฟลเดอร์ templates/{jump,slide}/
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

import config


def roi_to_pixels(roi: tuple[float, float, float, float], w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = roi
    return int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)


def crop(img: np.ndarray, roi: tuple[float, float, float, float]) -> np.ndarray:
    h, w = img.shape[:2]
    x1, y1, x2, y2 = roi_to_pixels(roi, w, h)
    return img[y1:y2, x1:x2]


@dataclass
class DetectResult:
    jump: bool = False
    slide: bool = False
    jump_score: float = 0.0
    slide_score: float = 0.0


class MotionDetector:
    """ตรวจอุปสรรคจากการเปลี่ยนแปลงของภาพในโซนตรวจจับ"""

    def __init__(self):
        self._prev_jump: np.ndarray | None = None
        self._prev_slide: np.ndarray | None = None

    @staticmethod
    def _gray(region: np.ndarray) -> np.ndarray:
        g = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(g, (5, 5), 0)

    def _motion_ratio(self, region: np.ndarray, prev: np.ndarray | None) -> tuple[float, np.ndarray]:
        cur = self._gray(region)
        if prev is None or prev.shape != cur.shape:
            return 0.0, cur
        diff = cv2.absdiff(cur, prev)
        changed = np.count_nonzero(diff > config.MOTION_PIXEL_DELTA)
        ratio = changed / diff.size
        return ratio, cur

    def detect(self, img: np.ndarray) -> DetectResult:
        jr, self._prev_jump = self._motion_ratio(crop(img, config.ROI_JUMP), self._prev_jump)
        sr, self._prev_slide = self._motion_ratio(crop(img, config.ROI_SLIDE), self._prev_slide)
        return DetectResult(
            jump=jr > config.MOTION_THRESHOLD,
            slide=sr > config.MOTION_THRESHOLD,
            jump_score=jr,
            slide_score=sr,
        )


class TemplateDetector:
    """ตรวจอุปสรรคจากการจับคู่รูปภาพ (template matching)"""

    def __init__(self):
        self.jump_templates = self._load("jump")
        self.slide_templates = self._load("slide")
        if not self.jump_templates and not self.slide_templates:
            print("[detector] ไม่พบ template ในโฟลเดอร์ templates/ -- "
                  "เซฟรูปอุปสรรคก่อน หรือใช้ DETECT_METHOD='motion'")

    @staticmethod
    def _load(kind: str) -> list[np.ndarray]:
        folder = config.TEMPLATE_DIR / kind
        folder.mkdir(parents=True, exist_ok=True)
        templates = []
        for p in folder.glob("*.png"):
            t = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if t is not None:
                templates.append(t)
        return templates

    @staticmethod
    def _best_match(region: np.ndarray, templates: list[np.ndarray]) -> float:
        best = 0.0
        for t in templates:
            if t.shape[0] > region.shape[0] or t.shape[1] > region.shape[1]:
                continue
            res = cv2.matchTemplate(region, t, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            best = max(best, float(max_val))
        return best

    def detect(self, img: np.ndarray) -> DetectResult:
        jr = self._best_match(crop(img, config.ROI_JUMP), self.jump_templates)
        sr = self._best_match(crop(img, config.ROI_SLIDE), self.slide_templates)
        th = config.TEMPLATE_MATCH_THRESHOLD
        return DetectResult(jump=jr >= th, slide=sr >= th, jump_score=jr, slide_score=sr)


def build_detector():
    if config.DETECT_METHOD == "template":
        return TemplateDetector()
    return MotionDetector()
