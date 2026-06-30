"""อัดภาพหน้าจอช่วงจบเกม เพื่อเก็บหน้า Mystery Box / Confirm / Level up มาทำ template
บันทึกเฉพาะตอน "ไม่ได้อยู่ในด่าน" (ป๊อปอัพ/เมนู) เพื่อลดจำนวนภาพ
"""
import time
import cv2
import config
from adb_controller import ADBController
from auto_lobby import is_in_game

REC = config.SHOTS_DIR / "rec"
REC.mkdir(exist_ok=True)

a = ADBController()
a.connect()
n = 0
t_end = time.time() + 150
print("เริ่มอัด (เฉพาะตอนไม่ได้อยู่ในด่าน) 150 วิ...")
while time.time() < t_end:
    img = a.screencap()
    if not is_in_game(img):
        n += 1
        cv2.imwrite(str(REC / f"{n:03d}.png"), img)
    time.sleep(0.4)
print(f"เสร็จ บันทึก {n} ภาพใน {REC}")
