"""ตัด template สำหรับตรวจสถานะหน้าจอ จากภาพสะอาดในโฟลเดอร์ shots/
รันครั้งเดียวเพื่อสร้างไฟล์ใน templates/states/
ภาพอ้างอิงความละเอียด 1920x1080
"""
import cv2
import config

STATE_DIR = config.TEMPLATE_DIR / "states"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# (ไฟล์ต้นทางใน shots/, ชื่อ template, กล่อง crop x1,y1,x2,y2 ใน 1920x1080)
JOBS = [
    ("lobby.png", "lobby_marker", (1120, 791, 1750, 858)),   # แถบ Pet|Cookie|Treasure (เฉพาะ lobby)
    ("state.png", "buy_title",    (277, 150, 565, 195)),     # ข้อความ "Buy Upgrades!"
    ("modal.png", "modal_multibuy", (778, 834, 1125, 934)),  # ปุ่ม Multi-Buy (เฉพาะ modal)
    ("state.png", "double_coins", (1125, 787, 1575, 853)),   # แบนเนอร์ Double Coins เหนือปุ่ม Play
    ("jump_test.png", "relay_boost", (572, 334, 1350, 384)), # ข้อความ "Tap to activate Cookie Relay Boost!"
    ("after_jump.png", "result_title", (800, 65, 1120, 180)),# หัวข้อ "Result" หน้าจบเกม
    ("state.png", "multi_btn", (1590, 300, 1705, 385)),      # ปุ่ม Multi (โผล่เฉพาะตอนเลือก Random Boost)
    ("loop_check.png", "in_game", (150, 905, 365, 970)),     # ปุ่ม "Jump" (มีเฉพาะตอนอยู่ในด่าน)
    ("rec/002.png", "mystery_box", (694, 71, 1219, 178)),    # หัวข้อ "Mystery Box" (หน้า Open all/Confirm)
    ("rec/004.png", "confirm_btn", (770, 910, 1150, 1025)),  # ปุ่ม "Confirm" (รางวัล/เลเวลอัพ)
    ("after_jump.png", "ok_btn", (600, 895, 785, 965)),     # ปุ่ม "OK" (Result / popup)
]

for src, name, (x1, y1, x2, y2) in JOBS:
    img = cv2.imread(str(config.SHOTS_DIR / src))
    if img is None:
        print(f"[ข้าม] ไม่พบภาพ {src}")
        continue
    crop = img[y1:y2, x1:x2]
    out = STATE_DIR / f"{name}.png"
    cv2.imwrite(str(out), crop)
    print(f"สร้าง {out}  ขนาด {crop.shape[1]}x{crop.shape[0]}")
print("เสร็จ - ตรวจไฟล์ใน templates/states/ ว่าตัดได้ตรงองค์ประกอบไหม")
