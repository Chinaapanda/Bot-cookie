"""สคริปต์วินิจฉัย: จับภาพ วัด motion ในแต่ละโซน และเซฟภาพไว้ดู"""
import time
import cv2
import config
from adb_controller import ADBController
from detector import MotionDetector, crop, roi_to_pixels

adb = ADBController()
if not adb.connect():
    raise SystemExit(1)

w, h = adb.screen_size()
print(f"ขนาดจอ: {w}x{h}")
print(f"TAP=({config.TAP_X},{config.TAP_Y})  SLIDE=({config.SLIDE_X},{config.SLIDE_Y})")
for name, roi in (("JUMP", config.ROI_JUMP), ("SLIDE", config.ROI_SLIDE)):
    px = roi_to_pixels(roi, w, h)
    print(f"ROI_{name} pixels = {px}")

det = MotionDetector()
print("\nวัด motion ratio 15 เฟรม (เล่นเกมอยู่ให้คุกกี้วิ่ง):")
img = None
for i in range(15):
    img = adb.screencap()
    r = det.detect(img)
    print(f"  เฟรม {i:02d}: jump={r.jump_score:.4f}  slide={r.slide_score:.4f}  "
          f"-> jump={r.jump} slide={r.slide}  (threshold={config.MOTION_THRESHOLD})")
    time.sleep(0.08)

if img is not None:
    out = config.SHOTS_DIR / "diagnose.png"
    cv2.imwrite(str(out), img)
    # วาดโซนทับด้วย
    vis = img.copy()
    for roi, color in ((config.ROI_JUMP,(0,165,255)),(config.ROI_SLIDE,(255,100,0)),(config.ROI_PLAYER,(0,255,0))):
        x1,y1,x2,y2 = roi_to_pixels(roi,w,h)
        cv2.rectangle(vis,(x1,y1),(x2,y2),color,3)
    cv2.circle(vis,(config.TAP_X,config.TAP_Y),16,(0,0,255),3)
    cv2.imwrite(str(config.SHOTS_DIR / "diagnose_roi.png"), vis)
    print(f"\nเซฟภาพ: {out} และ diagnose_roi.png (มีกรอบโซน)")
