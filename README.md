# Cookie Run Classic Auto-Play Bot (LDPlayer + ADB)

บอทเล่นเกม **Cookie Run Classic** อัตโนมัติบน **LDPlayer** โดยใช้ Python
เชื่อมต่อผ่าน **ADB**: จับภาพหน้าจอ -> ตรวจจับอุปสรรค -> สั่ง "กระโดด" หรือ "สไลด์"

> ⚠️ ใช้เพื่อการเรียนรู้/เล่นส่วนตัวเท่านั้น การใช้บอทอาจขัดกับ Terms of Service ของเกม
> และบัญชีอาจถูกแบนได้ โปรดรับความเสี่ยงเอง

---

## ดาวน์โหลด & เปิดใช้ (ผู้ใช้ทั่วไป)

### วิธีที่ 1: แอป GUI (แนะนำ)

1. ดาวน์โหลดจาก [GitHub Releases](https://github.com/Chinaapanda/Bot-cookie/releases)  
   ไฟล์ `CookieRunBot-vX.X.X.zip` หรือ clone repo
2. แตก zip → ดับเบิลคลิก **`run.bat`** (หรือ `CookieRunBot.exe` ถ้าเป็นเวอร์ชัน build แล้ว)
3. ครั้งแรก (source): รัน **`install.bat`** ก่อน 1 ครั้ง
4. เปิดแอป → แท็บ **ตั้งค่า** → ใส่ path ADB ของ LDPlayer → บันทึก
5. แท็บ **เล่น** → กด **▶ เล่นวน (Loop+Pattern)**

### อัปเดตอัตโนมัติ

- เปิดแอปจะ**ตรวจอัปเดตจาก GitHub** อัตโนมัติ (ปิดได้ใน ตั้งค่า)
- กดปุ่ม **ตรวจอัปเดต** เพื่อเช็คเอง
- ถ้ามีเวอร์ชันใหม่ → กด Yes → แอปดาวน์โหลด + รีสตาร์ทเอง  
  (ไม่ทับ `patterns/`, `settings.json` ของคุณ)
- ถ้า clone ด้วย git → ใช้ `git pull` แทน

### สำหรับผู้พัฒนา (ปล่อยเวอร์ชันใหม่)

```powershell
# แก้ VERSION ใน version.py แล้ว:
git add .
git commit -m "release v1.0.1"
git tag v1.0.1
git push origin main --tags
```
GitHub Actions จะ build `.zip` และสร้าง Release ให้อัตโนมัติ

---

## โครงสร้างไฟล์

| ไฟล์ | หน้าที่ |
|------|---------|
| `config.py` | ค่าตั้งทั้งหมด (path adb, พิกัดแตะ, โซนตรวจจับ, ความไว) |
| `adb_controller.py` | เชื่อมต่อ LDPlayer, จับภาพ, แตะ/ปัด |
| `detector.py` | ตรวจจับอุปสรรค (โหมด motion หรือ template) |
| `bot.py` | ลูปหลักของบอท (เล่นในด่าน: react สด หรือเล่นตาม pattern) |
| `pattern.py` | อัด & เล่นซ้ำ "จังหวะการเล่น" (record/replay) — เก็บเหรียญสม่ำเสมอสุด |
| `auto_lobby.py` | macro ก่อนเริ่มเล่น: Play → Multi → Multi-Buy จนได้ Double Coins |
| `make_templates.py` | สร้าง template ตรวจสถานะหน้าจอจากภาพใน `shots/` |
| `diagnose.py` | วัดค่า motion + เซฟภาพพร้อมกรอบโซนไว้ตรวจสอบ |
| `calibrate.py` | เครื่องมือช่วยหาพิกัด/โซน และเซฟ template |
| `app.py` | **แอป GUI หลัก** (เปิดด้วย run.bat / CookieRunBot.exe) |
| `gui/` | หน้าต่าง CustomTkinter — ภาพรวม, ควบคุม, Patterns, ตั้งค่า, Log |
| `updater.py` | ตรวจและติดตั้งอัปเดตจาก GitHub |
| `settings.py` | การตั้งค่าผู้ใช้ (settings.json) |
| `version.py` | เลขเวอร์ชันแอป |

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

## ⭐ โหมด Pattern — อัดจังหวะที่ดีไว้แล้วเล่นซ้ำ (เก็บเหรียญเยอะสุด)

ด่านวิ่งใน Cookie Run Classic เป็น **fixed pattern** (อุปสรรควางตำแหน่งเดิม
ทุกรอบของแต่ละ episode) จุดนี้ทำให้วิธีที่ "ได้ตังเยอะสุด + เสถียรสุด" คือ
**อัดจังหวะกระโดด/สไลด์ที่เล่นได้ดี 1 รอบ แล้วเล่นซ้ำตาม timeline เดิม** —
ดีกว่าการ react สด ๆ เพราะไม่พลาดเหรียญและไม่กระโดดมั่ว

**1) อัด pattern** (เล่นเองผ่านคีย์บอร์ดของคอม บอทจะส่งคำสั่งไปเกม + จับเวลาให้):
```powershell
python bot.py --record EP1
# หรือ:  python pattern.py record EP1
```
รอจนบอทบอกว่า "เริ่มจับเวลา!" (ตรวจเจอว่าเข้าด่าน) แล้วคุมเกมด้วยคีย์:
| คีย์ | การกระทำ |
|------|----------|
| `W` / `J` / `Space` | กระโดด (แตะ 1 ที = กระโดด 1 ครั้ง) |
| `K` / `S` | สไลด์/มุด (กดค้าง = มุดต่อเนื่องตามที่กด) |
| `Q` / `Esc` หรือ `Ctrl+C` | จบและบันทึก → `patterns/EP1.json` |

> **กระโดด = แตะ** (กลไกเกมเป็นแบบแตะ) กด W 1 ที = กระโดด 1 ครั้ง, double jump = กด W สองที
> **สไลด์ = กดค้างจริง** บันทึกระยะเวลากดค้าง แล้วตอนเล่นซ้ำมุดค้างตามนั้นเป๊ะ (touch down/up)
> จบเกมเองระบบหยุด+เซฟอัตโนมัติ และ auto-save ทุก 5 วิกันงานหาย

**Sync กับหน้าจอ (Relay Boost):** เกมมีจังหวะ **Cookie Relay Boost** ที่หยุดเกมรอแตะ
ระบบจัดการให้อัตโนมัติ:
- ตอน**อัด** — เจอ Relay Boost จะแตะกลางจอให้เอง + จดเป็น "จุด sync"
- ตอน**เล่นซ้ำ** — พอถึงจุดนั้นจะ **รอให้จอ Relay โผล่จริงแล้วค่อยแตะ + รีเซ็ตนาฬิกา**
  จังหวะหลัง Relay จึงไม่หลุด (ภูมิคุ้มกันการเพี้ยนเวลา)

เล่นวนครบวงจร (จบเกม → กล่อง/Confirm → กลับ lobby → Double Coins → เล่น pattern ใหม่):
```powershell
python bot.py --loop --pattern EP1 --lead 80
```

**2) เล่นซ้ำ:**
```powershell
python bot.py --play-pattern EP1            # เล่น 1 รอบ
python bot.py --play-pattern EP1 --lead 80  # ยิงเร็วขึ้น 80ms ชดเชย lag
python pattern.py list                      # ดู pattern ที่อัดไว้
```

**3) เล่นวนอัตโนมัติด้วย pattern** (เตรียม Double Coins → เล่นตาม pattern → จบ → วนใหม่):
```powershell
python bot.py --loop --pattern EP1 --lead 80
```

> เคล็ดลับ: ใช้ **ตัวละคร + บูสต์ชุดเดิมทุกรอบ** เพื่อให้ความเร็ววิ่งคงที่ จังหวะจะตรง
> ค่าเริ่มต้นเล่นแบบ **เป๊ะ** (`jump_gap=0`) — ตรงกับไฟล์ที่อัดมากที่สุด

### จูนจังหวะ (ถ้าเพี้ยน)

| อาการ | แก้ |
|--------|-----|
| กระโดดช้ากว่าตอนอัด | เพิ่ม `lead` (+20 ถึง +80ms) หรือใน GUI หน้าควบคุม |
| กระโดดเร็วกว่าตอนอัด | ลด `lead` (ใส่ค่าลบได้ เช่น `-30`) |
| double jump ตอนเล่น | เพิ่ม `jump_gap` (80–280ms) หรือกดปุ่ม **กัน double jump** ใน GUI |

```powershell
python bot.py --play-pattern EP1 --lead 40 --jump-gap 0   # เป๊ะ + ชดเชย lag เล็กน้อย
python bot.py --play-pattern EP1 --jump-gap 280           # กัน double jump
```

> ทดสอบด้วย pattern สั้น ๆ (5–10 จังหวะ) ก่อนใช้ไฟล์ยาว ๆ
> ถ้าจังหวะเริ่มเพี้ยน (กระโดดเร็ว/ช้าไป) ปรับ `--lead` (เพิ่ม = ยิงเร็วขึ้น)
> อัด pattern แยกไฟล์ต่อ episode ได้ไม่จำกัด

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

## ทำให้บอทเก่งขึ้น (สรุป)

ทำไปแล้ว:
- **จับภาพเร็วขึ้น** — `CAPTURE_RAW = True` ใน `config.py` ดึง pixel ดิบ (RGBA)
  ไม่ต้อง encode/decode PNG เร็วกว่าหลายเท่า (ถ้าจอเพี้ยนให้ตั้งเป็น `False`)
- **โหมด Pattern (record/replay)** — เก็บเหรียญสม่ำเสมอสุดสำหรับด่าน fixed pattern
- **react สดเลิกกระโดดรัว** — โหมด motion ตอนนี้ trigger เฉพาะ "ขอบขาขึ้น"
  (เพิ่งเริ่มเจออุปสรรค) ไม่กดซ้ำ ๆ ตลอดที่ฉากเลื่อน

ก้าวต่อไป (ถ้าอยากเก่งขึ้นอีก):
- เพิ่มความเร็วจับภาพด้วย **minicap/scrcpy** (สตรีมต่อเนื่อง ~30–60 fps)
- เทรนโมเดล **CV/ML (CNN)** ตัดสินใจ jump/slide/none จากภาพจริง (ต้องเก็บข้อมูล+เทรน)
- ทำ pattern ให้ทนต่อความเร็วที่เปลี่ยน โดย sync จาก landmark บนฉากแทน timer ล้วน
- เกม Cookie Run Classic แต่ละเวอร์ชัน/ภาษามี UI ต่างกัน ค่าโซนจึงต้อง calibrate เสมอ
