# Cookie Run Classic Auto-Play Bot (LDPlayer + ADB)

บอทเล่นเกม **Cookie Run Classic** อัตโนมัติบน **LDPlayer** โดยใช้ Python
เชื่อมต่อผ่าน **ADB**: จับภาพหน้าจอ -> ตรวจจับอุปสรรค -> สั่ง "กระโดด" หรือ "สไลด์"

> ⚠️ ใช้เพื่อการเรียนรู้/เล่นส่วนตัวเท่านั้น การใช้บอทอาจขัดกับ Terms of Service ของเกม
> และบัญชีอาจถูกแบนได้ โปรดรับความเสี่ยงเอง

---

## โครงสร้างไฟล์

| ไฟล์ | หน้าที่ |
|------|---------|
| `config.py` | ค่าตั้งทั้งหมด (path adb, พิกัดแตะ, โซนตรวจจับ, ความไว) |
| `adb_controller.py` | เชื่อมต่อ LDPlayer, จับภาพ, แตะ/ปัด |
| `detector.py` | ตรวจจับอุปสรรค (โหมด motion หรือ template) |
| `bot.py` | ลูปหลักของบอท (เล่นในด่าน: กระโดด/สไลด์) |
| `auto_lobby.py` | macro ก่อนเริ่มเล่น: Play → Multi → Multi-Buy จนได้ Double Coins |
| `make_templates.py` | สร้าง template ตรวจสถานะหน้าจอจากภาพใน `shots/` |
| `diagnose.py` | วัดค่า motion + เซฟภาพพร้อมกรอบโซนไว้ตรวจสอบ |
| `calibrate.py` | เครื่องมือช่วยหาพิกัด/โซน และเซฟ template |
| `requirements.txt` | ไลบรารีที่ต้องติดตั้ง |

---

## 1) ติดตั้ง

```powershell
cd "c:\Users\ChinaPanda\OneDrive\Desktop\mobile"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) เปิด ADB ใน LDPlayer

1. เปิด LDPlayer แล้วไปที่ **Settings (ตั้งค่า) → Other settings (ตั้งค่าอื่น ๆ)**
2. เปิด **ADB debugging → Open local connection (เปิดการเชื่อมต่อภายในเครื่อง)**
3. รีสตาร์ท LDPlayer

> instance แรกของ LDPlayer9 ใช้พอร์ต `127.0.0.1:5555`
> instance ถัดไปจะเป็น `5557`, `5559`, ... (ตั้งใน `config.py` ที่ `ADB_SERIAL`)

ทดสอบการเชื่อมต่อ:

```powershell
python adb_controller.py
```
ถ้าได้ผลแบบ `เชื่อมต่อ ... สำเร็จ` + ขนาดจอ + ขนาดภาพ = พร้อมใช้งาน

## 3) Calibrate (สำคัญมาก)

พิกัดและโซนตรวจจับใน `config.py` เป็นค่าเริ่มต้น **ต้องปรับให้ตรงกับจอ/เกมของคุณ**

```powershell
python calibrate.py
```

ในหน้าต่างที่เปิดขึ้น:
- **คลิก** บนภาพ = พิมพ์พิกัดจริงออกมา ที่ terminal → เอาไปใส่ `TAP_X/TAP_Y` (จุดกระโดด) และ `SLIDE_X/SLIDE_Y` (จุดสไลด์) ใน `config.py`
- ดูกรอบสี `ROI_JUMP` / `ROI_SLIDE` ว่าครอบ "พื้นที่ข้างหน้าคุกกี้" ถูกไหม ถ้าไม่ตรงให้แก้ค่าใน `config.py` (เป็นสัดส่วน 0–1)
- กด `s` เซฟภาพหน้าจอ, `r` รีเฟรชภาพ, `q` ออก
- (โหมด template) กด `j`/`k` แล้ว **ลากกรอบ** รอบอุปสรรคเพื่อเซฟรูปไว้ใช้กับ `DETECT_METHOD="template"`

## 4) รันบอท

```powershell
python bot.py            # รันปกติ
python bot.py --debug    # เปิดหน้าต่าง debug เห็นโซน + คะแนนตรวจจับ (แนะนำตอนจูน)
```

เปิดเกม Cookie Run Classic ใน LDPlayer → เริ่มด่าน → แล้วให้บอททำงาน
หยุดด้วย **Ctrl+C** (หรือกด `q` ในหน้าต่าง debug)

ระหว่างเล่น บอทจัดการหน้าจอพิเศษให้อัตโนมัติ:
- ขึ้น **"Tap to activate Cookie Relay Boost!"** → แตะกลางจอ
- จบเกมเป็นหน้า **Result** → กด **OK**

เล่นวนยาวแบบไม่ต้องแตะเอง — **คำสั่งเดียวจบ ขับเองครบวงจรจากทุกหน้าจอ**:
```powershell
python bot.py --loop
```
`--loop` จะวนเอง: หน้าเมนู → เตรียม Double Coins → กด Play → เล่นในด่าน
(กระโดด/สไลด์ + Cookie Relay Boost) → จบเกมกด OK → กลับไปเริ่มใหม่
เริ่มจากหน้าไหนก็ได้ (lobby / buy / ในด่าน) ไม่ต้อง chain `auto_lobby.py` เอง

---

## Macro ก่อนเริ่มเล่น (เตรียม Double Coins อัตโนมัติ)

`auto_lobby.py` ทำขั้นตอนก่อนเข้าด่านให้อัตโนมัติ:
หน้าหลัก → กด **Play!** → กดปุ่ม **Multi** → กด **Multi-Buy**
(เกมจะวนซื้อบูสต์สุ่มเองจนได้บูสต์ที่เลือกไว้ = **Double Coins**) →
กลับมาหน้า Buy Upgrades พร้อมแบนเนอร์ Double Coins เหนือปุ่ม Play

```powershell
python make_templates.py     # สร้าง template ตรวจสถานะ (ทำครั้งเดียว)
python auto_lobby.py         # เตรียม Double Coins อย่างเดียว
python auto_lobby.py --play  # เตรียมเสร็จแล้วกด Play เริ่มด่านต่อ
python auto_lobby.py --debug # ดูคะแนน match ของแต่ละสถานะ (ไว้ debug)
```

ต่อยอด: เตรียมแล้วเข้าเล่นด้วยบอทต่อทันที
```powershell
python auto_lobby.py --play ; python bot.py
```

> หมายเหตุ: Multi-Buy ใช้เหรียญ (ครั้งแรก ~1,200 / ครั้งถัดไป ~600 ต่อการสุ่ม)
> ปรับเพดานจำนวนครั้งด้วย `--max-buys` (ค่าเริ่มต้น 5)
> พิกัดปุ่ม/template อ้างอิงจอ **1920x1080** ถ้าจอต่างต้องจับภาพใหม่แล้วรัน `make_templates.py` อีกครั้ง

---

## วิธีจูนให้แม่นขึ้น

เปิด `python bot.py --debug` แล้วดูตัวเลข `JUMP x.xxx` / `SLIDE x.xxx` มุมโซน:

- **กระโดดมั่ว / สไลด์มั่ว** → เพิ่ม `MOTION_THRESHOLD` (เช่น 0.04 → 0.07)
- **ไม่ค่อยตอบสนอง** → ลด `MOTION_THRESHOLD`
- **กดรัวเกินไป** → เพิ่ม `ACTION_COOLDOWN_S`
- **ช้า/กระตุก** → ลด `TARGET_FPS` หรือเปลี่ยนไปใช้ minicap (ดูด้านล่าง)
- **ตรวจผิดโซน** → ปรับ `ROI_JUMP` / `ROI_SLIDE` ให้ครอบเฉพาะ "ข้างหน้าคุกกี้ก่อนถึงตัว"

โหมด `motion` ใช้ได้ทันทีโดยไม่ต้องเตรียมรูป แต่ "ดู" แค่การเคลื่อนไหวในโซน
ถ้าต้องการแม่นยำกับอุปสรรคเฉพาะแบบ ให้เซฟ template (ผ่าน `calibrate.py`)
แล้วตั้ง `DETECT_METHOD = "template"` ใน `config.py`

---

## ข้อจำกัด & ก้าวต่อไป

- `adb screencap` ค่อนข้างช้า (~3–6 fps) เกมแนววิ่งเร็วอาจต้องการเฟรมเรตสูงกว่า
  ทางเลือกที่เร็วกว่า: **minicap** หรืออ่านวิดีโอจาก **scrcpy** (เพิ่ม backend ใน `CAPTURE_BACKEND` ได้ภายหลัง)
- การตัดสินใจตอนนี้เป็น rule-based (motion/template) เหมาะกับการเริ่มต้น
  ถ้าต้องการเก่งขึ้นมากสามารถต่อยอดเป็นโมเดล CV/ML ที่เทรนจากภาพเกมจริงได้
- เกม Cookie Run Classic แต่ละเวอร์ชัน/ภาษามี UI ต่างกัน ค่าโซนจึงต้อง calibrate เสมอ
