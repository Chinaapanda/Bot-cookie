"""หน้าต่างหลัก — CustomTkinter modern UI"""
from __future__ import annotations

import queue
import threading
import webbrowser
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gui.calibrate_page import CalibratePage
from gui.components import LogPanel, NavButton, SectionTitle, StatusCard
from gui.services import AdbService, BotService, PatternService, persist_settings, read_settings
from gui.theme import COLORS, FONT_BODY, FONT_SMALL, FONT_TITLE, PAD, SIDEBAR_W
from version import GITHUB_URL, VERSION


PAGES = ("dashboard", "control", "patterns", "calibrate", "settings", "logs")


class CookieRunApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Cookie Run Bot")
        self.geometry("1024x680")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg_dark"])

        self._bot = BotService()
        self._log_q: queue.Queue[str] = queue.Queue()
        self._cfg = read_settings()
        self._page = "dashboard"
        self._nav_btns: dict[str, NavButton] = {}
        self._selected_pattern = ""
        self._timing_preset = "faithful"

        self._build_shell()
        self._show_page("dashboard")
        self._load_cfg_to_ui()
        self.after(150, self._drain_log)
        self.after(500, self._refresh_status)
        if self._cfg.get("auto_check_update", True):
            self.after(1000, self._check_update_silent)

    # ------------------------------------------------------------------ shell
    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        side = ctk.CTkFrame(self, width=SIDEBAR_W, fg_color=COLORS["sidebar"], corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)

        ctk.CTkLabel(side, text="🍪 Cookie Run", font=FONT_TITLE,
                     text_color=COLORS["accent"]).pack(anchor="w", padx=PAD, pady=(20, 0))
        ctk.CTkLabel(side, text="Auto Play Bot", font=FONT_SMALL,
                     text_color=COLORS["text_dim"]).pack(anchor="w", padx=PAD, pady=(0, 20))

        nav_items = [
            ("dashboard", "  ภาพรวม"),
            ("control", "  ควบคุม"),
            ("patterns", "  Patterns"),
            ("calibrate", "  Calibrate"),
            ("settings", "  ตั้งค่า"),
            ("logs", "  Log"),
        ]
        for key, label in nav_items:
            btn = NavButton(side, label, lambda k=key: self._show_page(k))
            btn.pack(fill="x", padx=12, pady=3)
            self._nav_btns[key] = btn

        ctk.CTkFrame(side, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=PAD, pady=16)
        ctk.CTkButton(side, text="ตรวจอัปเดต", command=self._check_update,
                      fg_color=COLORS["card"], hover_color=COLORS["card_hover"],
                      height=34, font=FONT_SMALL).pack(fill="x", padx=12)
        ctk.CTkButton(side, text="GitHub", command=lambda: webbrowser.open(GITHUB_URL),
                      fg_color="transparent", hover_color=COLORS["card_hover"],
                      height=30, font=FONT_SMALL, text_color=COLORS["muted"]).pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(side, text=f"v{VERSION}", font=FONT_SMALL,
                     text_color=COLORS["muted"]).pack(side="bottom", pady=12)

        # Content
        self.content = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self._pages: dict[str, ctk.CTkFrame] = {}
        self._pages["dashboard"] = self._build_dashboard()
        self._pages["control"] = self._build_control()
        self._pages["patterns"] = self._build_patterns()
        self._pages["calibrate"] = self._build_calibrate()
        self._pages["settings"] = self._build_settings()
        self._pages["logs"] = self._build_logs()

        # Status bar
        bar = ctk.CTkFrame(self, height=32, fg_color=COLORS["sidebar"], corner_radius=0)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._st_adb = ctk.CTkLabel(bar, text="ADB: —", font=FONT_SMALL, text_color=COLORS["muted"])
        self._st_adb.pack(side="left", padx=PAD)
        self._st_bot = ctk.CTkLabel(bar, text="บอท: หยุด", font=FONT_SMALL, text_color=COLORS["muted"])
        self._st_bot.pack(side="left", padx=PAD)
        self._st_pat = ctk.CTkLabel(bar, text="Pattern: —", font=FONT_SMALL, text_color=COLORS["muted"])
        self._st_pat.pack(side="right", padx=PAD)

    def _show_page(self, name: str):
        self._page = name
        for k, f in self._pages.items():
            f.grid_remove()
        self._pages[name].grid(row=0, column=0, sticky="nsew", padx=PAD, pady=PAD)
        for k, btn in self._nav_btns.items():
            active = k == name
            btn.configure(
                fg_color=COLORS["accent"] if active else "transparent",
                text_color=COLORS["bg_dark"] if active else COLORS["text"],
                hover_color=COLORS["accent_hover"] if active else COLORS["card_hover"],
            )
        if name == "patterns":
            self._refresh_pattern_list()
        if name == "calibrate":
            self._calibrate_page.load_from_config()

    # ------------------------------------------------------------------ pages
    def _page_frame(self) -> ctk.CTkScrollableFrame:
        f = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        return f

    def _build_dashboard(self) -> ctk.CTkFrame:
        p = self._page_frame()
        SectionTitle(p, "ภาพรวม").grid(row=0, column=0, sticky="w", pady=(0, PAD))

        cards = ctk.CTkFrame(p, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", pady=(0, PAD))
        cards.grid_columnconfigure((0, 1, 2), weight=1)

        self._card_adb = StatusCard(cards, "ADB / LDPlayer", "📡")
        self._card_adb.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._card_bot = StatusCard(cards, "สถานะบอท", "🤖")
        self._card_bot.grid(row=0, column=1, sticky="nsew", padx=4)
        self._card_pat = StatusCard(cards, "Pattern", "📼")
        self._card_pat.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        quick = ctk.CTkFrame(p, fg_color=COLORS["card"], corner_radius=12,
                             border_width=1, border_color=COLORS["border"])
        quick.grid(row=2, column=0, sticky="ew", pady=(0, PAD))
        ctk.CTkLabel(quick, text="เริ่มเล่นเร็ว", font=FONT_BODY,
                     text_color=COLORS["text"]).pack(anchor="w", padx=PAD, pady=(PAD, 8))
        row = ctk.CTkFrame(quick, fg_color="transparent")
        row.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(row, text="▶  เล่นวนอัตโนมัติ", height=48, font=("Segoe UI", 14, "bold"),
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color=COLORS["bg_dark"], command=self._start_loop).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="ทดสอบ ADB", height=48, font=FONT_BODY,
                      fg_color=COLORS["card_hover"], hover_color=COLORS["border"],
                      command=self._test_adb).pack(side="left")

        ctk.CTkLabel(p, text="Log ล่าสุด", font=FONT_SMALL,
                     text_color=COLORS["text_dim"]).grid(row=3, column=0, sticky="w")
        self._dash_log = LogPanel(p, height=160)
        self._dash_log.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        return p

    def _build_control(self) -> ctk.CTkFrame:
        p = ctk.CTkFrame(self.content, fg_color="transparent")
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(p, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        SectionTitle(top, "ควบคุมการเล่น").grid(row=0, column=0, sticky="w", pady=(0, PAD))

        box = ctk.CTkFrame(top, fg_color=COLORS["card"], corner_radius=12,
                           border_width=1, border_color=COLORS["border"])
        box.grid(row=1, column=0, sticky="ew", pady=(0, PAD))
        box.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(box, text="Pattern", font=FONT_BODY).grid(row=0, column=0, padx=PAD, pady=12, sticky="w")
        self._ctl_pattern = ctk.CTkComboBox(box, values=["EP1"], width=200, font=FONT_BODY)
        self._ctl_pattern.grid(row=0, column=1, padx=PAD, pady=12, sticky="w")

        ctk.CTkLabel(box, text="Lead (ms)", font=FONT_BODY).grid(row=1, column=0, padx=PAD, pady=8, sticky="w")
        lead_row = ctk.CTkFrame(box, fg_color="transparent")
        lead_row.grid(row=1, column=1, sticky="w", padx=PAD, pady=8)
        self._ctl_lead = ctk.CTkEntry(lead_row, width=80, font=FONT_BODY)
        self._ctl_lead.pack(side="left")
        ctk.CTkLabel(lead_row, text="  ลบ=ช้าลง  บวก=เร็วขึ้น",
                     font=FONT_SMALL, text_color=COLORS["muted"]).pack(side="left", padx=8)

        ctk.CTkLabel(box, text="Jump gap (ms)", font=FONT_BODY).grid(row=2, column=0, padx=PAD, pady=8, sticky="w")
        gap_row = ctk.CTkFrame(box, fg_color="transparent")
        gap_row.grid(row=2, column=1, sticky="w", padx=PAD, pady=8)
        self._ctl_jump_gap = ctk.CTkEntry(gap_row, width=80, font=FONT_BODY)
        self._ctl_jump_gap.pack(side="left")
        ctk.CTkLabel(gap_row, text="  0=เล่นเป๊ะ  เพิ่มถ้า double jump",
                     font=FONT_SMALL, text_color=COLORS["muted"]).pack(side="left", padx=8)

        preset_row = ctk.CTkFrame(box, fg_color="transparent")
        preset_row.grid(row=3, column=0, columnspan=2, sticky="w", padx=PAD, pady=(0, 8))
        ctk.CTkLabel(preset_row, text="โหมดจังหวะ", font=FONT_BODY).pack(side="left", padx=(0, 8))
        ctk.CTkButton(preset_row, text="เป๊ะ", width=90,
                      command=lambda: self._apply_timing_preset("faithful"),
                      fg_color=COLORS["accent"], text_color=COLORS["bg_dark"]).pack(side="left", padx=4)
        ctk.CTkButton(preset_row, text="กัน double jump", width=140,
                      command=lambda: self._apply_timing_preset("safe"),
                      fg_color=COLORS["card_hover"]).pack(side="left", padx=4)

        btns = ctk.CTkFrame(box, fg_color="transparent")
        btns.grid(row=4, column=0, columnspan=2, padx=PAD, pady=PAD, sticky="ew")
        for text, cmd, color in (
            ("▶  เล่นวน (Loop)", self._start_loop, COLORS["accent"]),
            ("▶  เล่น 1 รอบ", self._start_once, COLORS["card_hover"]),
            ("⏺  อัด Pattern", self._start_record, COLORS["card_hover"]),
            ("■  หยุด", self._stop_bot, COLORS["danger"]),
        ):
            ctk.CTkButton(btns, text=text, command=cmd, height=42, font=FONT_BODY,
                          fg_color=color, hover_color=COLORS["accent_hover"] if color == COLORS["accent"] else COLORS["border"],
                          text_color=COLORS["bg_dark"] if color == COLORS["accent"] else COLORS["text"]
                          ).pack(side="left", padx=4)

        hint = ctk.CTkFrame(top, fg_color=COLORS["card"], corner_radius=10)
        hint.grid(row=2, column=0, sticky="ew")
        ctk.CTkLabel(hint, text="คีย์ตอนอัด:  W=กระโดด  |  S/K=สไลด์  |  Q=จบและบันทึก",
                     font=FONT_SMALL, text_color=COLORS["text_dim"]).pack(padx=PAD, pady=8)

        log_area = ctk.CTkFrame(p, fg_color="transparent")
        log_area.grid(row=1, column=0, sticky="nsew", pady=(PAD, 0))
        log_area.grid_columnconfigure(0, weight=1)
        log_area.grid_rowconfigure(1, weight=1)

        log_top = ctk.CTkFrame(log_area, fg_color="transparent")
        log_top.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(log_top, text="Log", font=FONT_SMALL,
                     text_color=COLORS["text_dim"]).pack(side="left")
        ctk.CTkButton(log_top, text="ล้าง", width=70, command=self._clear_logs,
                      fg_color=COLORS["card_hover"], height=28).pack(side="right")
        self._ctl_log = LogPanel(log_area, height=280)
        self._ctl_log.grid(row=1, column=0, sticky="nsew")
        return p

    def _build_patterns(self) -> ctk.CTkFrame:
        p = self._page_frame()
        SectionTitle(p, "จัดการ Patterns").grid(row=0, column=0, sticky="w", pady=(0, 8))

        edit = ctk.CTkFrame(p, fg_color=COLORS["card"], corner_radius=12,
                            border_width=1, border_color=COLORS["border"])
        edit.grid(row=1, column=0, sticky="ew", pady=(0, PAD))
        ctk.CTkLabel(edit, text="ชื่อ Pattern", font=FONT_BODY).pack(side="left", padx=(PAD, 8), pady=PAD)
        self._pat_name = ctk.CTkEntry(edit, width=220, font=FONT_BODY,
                                      placeholder_text="เช่น EP2, boss_run")
        self._pat_name.pack(side="left", padx=(0, 8), pady=PAD)
        ctk.CTkButton(edit, text="สร้างใหม่", width=100, command=self._create_pattern,
                      fg_color=COLORS["accent"], text_color=COLORS["bg_dark"]).pack(side="left", padx=4)
        ctk.CTkButton(edit, text="เปลี่ยนชื่อ", width=100, command=self._rename_pattern,
                      fg_color=COLORS["card_hover"]).pack(side="left", padx=4)
        ctk.CTkButton(edit, text="ลบ", width=70, command=self._delete_pattern,
                      fg_color=COLORS["danger"]).pack(side="left", padx=4)
        ctk.CTkLabel(edit, text="เลือกจากรายการด้านล่าง แล้วแก้ชื่อเพื่อเปลี่ยนชื่อ",
                     font=FONT_SMALL, text_color=COLORS["muted"]).pack(side="left", padx=12)

        top = ctk.CTkFrame(p, fg_color="transparent")
        top.grid(row=2, column=0, sticky="ew", pady=(0, PAD))
        ctk.CTkButton(top, text="รีเฟรช", width=100, command=self._refresh_pattern_list,
                      fg_color=COLORS["card_hover"]).pack(side="left")
        ctk.CTkButton(top, text="เปิดโฟลเดอร์", width=120,
                      command=self._open_patterns_dir,
                      fg_color=COLORS["card_hover"]).pack(side="left", padx=8)

        self._pat_list = ctk.CTkFrame(p, fg_color=COLORS["card"], corner_radius=12,
                                      border_width=1, border_color=COLORS["border"])
        self._pat_list.grid(row=3, column=0, sticky="nsew")
        return p

    def _build_calibrate(self) -> ctk.CTkFrame:
        p = ctk.CTkFrame(self.content, fg_color="transparent")
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(0, weight=1)
        self._calibrate_page = CalibratePage(p, on_coords_changed=self._on_calibrate_saved)
        self._calibrate_page.grid(row=0, column=0, sticky="nsew")
        return p

    def _on_calibrate_saved(self):
        self._load_cfg_to_ui()
        self._log("[calibrate] บันทึกพิกัด/โซนแล้ว")

    def _build_settings(self) -> ctk.CTkFrame:
        p = self._page_frame()
        SectionTitle(p, "ตั้งค่า").grid(row=0, column=0, sticky="w", pady=(0, PAD))

        self._set_vars: dict[str, ctk.StringVar] = {}

        def section(title: str, row: int, fields: list[tuple[str, str, int]]):
            fr = ctk.CTkFrame(p, fg_color=COLORS["card"], corner_radius=12,
                              border_width=1, border_color=COLORS["border"])
            fr.grid(row=row, column=0, sticky="ew", pady=(0, PAD))
            fr.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(fr, text=title, font=FONT_BODY,
                         text_color=COLORS["accent"]).grid(row=0, column=0, columnspan=2,
                                                           padx=PAD, pady=(PAD, 8), sticky="w")
            for i, (label, key, w) in enumerate(fields, start=1):
                ctk.CTkLabel(fr, text=label, font=FONT_SMALL,
                             text_color=COLORS["text_dim"]).grid(row=i, column=0, padx=PAD, pady=6, sticky="w")
                var = ctk.StringVar()
                self._set_vars[key] = var
                entry = ctk.CTkEntry(fr, textvariable=var, width=w, font=FONT_BODY)
                entry.grid(row=i, column=1, padx=PAD, pady=6, sticky="w")
                if key == "ADB_PATH":
                    ctk.CTkButton(fr, text="เลือกไฟล์", width=90,
                                  command=self._browse_adb,
                                  fg_color=COLORS["card_hover"]).grid(row=i, column=2, padx=8)

        section("การเชื่อมต่อ", 1, [
            ("ADB Path", "ADB_PATH", 360),
            ("ADB Serial", "ADB_SERIAL", 200),
        ])
        section("พิกัดปุ่ม (1920×1080)", 2, [
            ("Jump X / Y", "TAP_XY", 120),
            ("Slide X / Y", "SLIDE_XY", 120),
        ])

        adv = ctk.CTkFrame(p, fg_color=COLORS["card"], corner_radius=12,
                           border_width=1, border_color=COLORS["border"])
        adv.grid(row=3, column=0, sticky="ew", pady=(0, PAD))
        self._var_auto_up = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(adv, text="ตรวจอัปเดตอัตโนมัติเมื่อเปิดแอป",
                        variable=self._var_auto_up, font=FONT_BODY).pack(anchor="w", padx=PAD, pady=PAD)

        ctk.CTkButton(p, text="บันทึกการตั้งค่า", height=42, font=FONT_BODY,
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color=COLORS["bg_dark"], command=self._save_settings).grid(row=4, column=0, sticky="w")
        return p

    def _build_logs(self) -> ctk.CTkFrame:
        p = ctk.CTkFrame(self.content, fg_color="transparent")
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(p, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        SectionTitle(top, "Log").pack(side="left")
        ctk.CTkButton(top, text="ล้าง", width=80, command=self._clear_logs,
                      fg_color=COLORS["card_hover"]).pack(side="right")
        self._main_log = LogPanel(p, height=500)
        self._main_log.grid(row=1, column=0, sticky="nsew")
        return p

    # ------------------------------------------------------------------ data
    def _load_cfg_to_ui(self):
        self._cfg = read_settings()
        names = [m.name for m in PatternService.list_all()] or ["EP1"]
        self._sync_pattern_names(names)
        pat = self._cfg.get("default_pattern", names[0])
        self._ctl_pattern.set(pat)
        self._ctl_lead.delete(0, "end")
        self._ctl_lead.insert(0, str(self._cfg.get("default_lead", 0)))
        self._ctl_jump_gap.delete(0, "end")
        self._ctl_jump_gap.insert(0, str(self._cfg.get("jump_min_gap_ms", 0)))
        self._timing_preset = self._cfg.get("timing_preset", "faithful")

        tap = f"{self._cfg.get('TAP_X', 244)},{self._cfg.get('TAP_Y', 937)}"
        slide = f"{self._cfg.get('SLIDE_X', 1700)},{self._cfg.get('SLIDE_Y', 937)}"
        mapping = {
            "ADB_PATH": str(self._cfg.get("ADB_PATH", "")),
            "ADB_SERIAL": str(self._cfg.get("ADB_SERIAL", "")),
            "TAP_XY": tap,
            "SLIDE_XY": slide,
        }
        for k, v in mapping.items():
            if k in self._set_vars:
                self._set_vars[k].set(v)
        self._var_auto_up.set(self._cfg.get("auto_check_update", True))
        self._update_pattern_card(pat)

    def _gather_settings(self) -> dict:
        from settings import load
        data = load()
        data["ADB_PATH"] = self._set_vars["ADB_PATH"].get().strip()
        data["ADB_SERIAL"] = self._set_vars["ADB_SERIAL"].get().strip()
        try:
            tx, ty = self._set_vars["TAP_XY"].get().replace(" ", "").split(",")
            data["TAP_X"], data["TAP_Y"] = int(tx), int(ty)
        except (ValueError, AttributeError):
            pass
        try:
            sx, sy = self._set_vars["SLIDE_XY"].get().replace(" ", "").split(",")
            data["SLIDE_X"], data["SLIDE_Y"] = int(sx), int(sy)
        except (ValueError, AttributeError):
            pass
        data["default_pattern"] = self._ctl_pattern.get().strip()
        try:
            data["default_lead"] = int(self._ctl_lead.get().strip())
        except ValueError:
            data["default_lead"] = 0
        try:
            data["jump_min_gap_ms"] = int(self._ctl_jump_gap.get().strip())
        except ValueError:
            data["jump_min_gap_ms"] = 0
        data["timing_preset"] = getattr(self, "_timing_preset", "faithful")
        data["auto_check_update"] = self._var_auto_up.get()
        return data

    def _save_settings(self):
        persist_settings(self._gather_settings())
        self._log("[settings] บันทึกแล้ว")
        messagebox.showinfo("บันทึก", "บันทึกการตั้งค่าแล้ว")

    def _save_quiet(self):
        persist_settings(self._gather_settings())

    def _sync_pattern_names(self, names: list[str] | None = None):
        if names is None:
            names = [m.name for m in PatternService.list_all()] or ["EP1"]
        self._ctl_pattern.configure(values=names)
        cur = self._ctl_pattern.get().strip()
        if cur not in names and names:
            self._ctl_pattern.set(names[0])

    def _refresh_pattern_list(self):
        for w in self._pat_list.winfo_children():
            w.destroy()
        metas = PatternService.list_all()
        names = [m.name for m in metas] or ["EP1"]
        self._sync_pattern_names(names)

        if not metas:
            ctk.CTkLabel(self._pat_list, text="ยังไม่มี pattern — พิมพ์ชื่อด้านบนแล้วกด「สร้างใหม่」",
                         font=FONT_BODY, text_color=COLORS["muted"]).pack(padx=PAD, pady=PAD)
            return

        hdr = ctk.CTkFrame(self._pat_list, fg_color="transparent")
        hdr.pack(fill="x", padx=PAD, pady=(PAD, 4))
        for col, txt in enumerate(["ชื่อ", "จังหวะ", "Relay", "ระยะเวลา", ""]):
            ctk.CTkLabel(hdr, text=txt, font=("Segoe UI", 11, "bold"),
                         text_color=COLORS["text_dim"], width=100 if col < 4 else 80).pack(side="left", padx=4)

        for m in metas:
            bg = COLORS["accent"] if m.name == self._selected_pattern else COLORS["card_hover"]
            row = ctk.CTkFrame(self._pat_list, fg_color=bg, corner_radius=8)
            row.pack(fill="x", padx=PAD, pady=3)
            row.bind("<Button-1>", lambda _e, n=m.name: self._pick_pattern(n))
            dur = f"{m.duration:.0f}s" if m.duration else "—"
            for txt, w in [(m.name, 100), (str(m.events), 100), (str(m.relays), 100), (dur, 100)]:
                lbl = ctk.CTkLabel(row, text=txt, font=FONT_SMALL, width=w)
                lbl.pack(side="left", padx=4, pady=8)
                lbl.bind("<Button-1>", lambda _e, n=m.name: self._pick_pattern(n))
            ctk.CTkButton(row, text="ใช้เล่น", width=70, height=28,
                          command=lambda n=m.name: self._select_pattern(n),
                          fg_color=COLORS["accent"], text_color=COLORS["bg_dark"]).pack(side="right", padx=8, pady=4)

    def _pick_pattern(self, name: str):
        self._selected_pattern = name
        self._pat_name.delete(0, "end")
        self._pat_name.insert(0, name)
        self._refresh_pattern_list()

    def _create_pattern(self):
        from pattern import sanitize_name
        name = sanitize_name(self._pat_name.get())
        if not name:
            messagebox.showwarning("สร้าง Pattern", "กรุณาพิมพ์ชื่อ pattern")
            return
        try:
            PatternService.create(name)
        except FileExistsError:
            messagebox.showwarning("สร้าง Pattern", f"มี pattern '{name}' อยู่แล้ว")
            return
        except ValueError as e:
            messagebox.showwarning("สร้าง Pattern", str(e))
            return
        self._selected_pattern = name
        self._pat_name.delete(0, "end")
        self._pat_name.insert(0, name)
        self._ctl_pattern.set(name)
        self._update_pattern_card(name)
        self._refresh_pattern_list()
        self._log(f"[pattern] สร้าง '{name}' แล้ว — ไปหน้าควบคุมเพื่ออัด")
        messagebox.showinfo("สร้าง Pattern", f"สร้าง '{name}' แล้ว\nไปหน้า「ควบคุม」เพื่อกดอัด Pattern")

    def _rename_pattern(self):
        if not self._selected_pattern:
            messagebox.showwarning("เปลี่ยนชื่อ", "เลือก pattern จากรายการก่อน")
            return
        from pattern import sanitize_name
        new_name = sanitize_name(self._pat_name.get())
        if not new_name:
            messagebox.showwarning("เปลี่ยนชื่อ", "กรุณาพิมพ์ชื่อใหม่")
            return
        if new_name == self._selected_pattern:
            messagebox.showinfo("เปลี่ยนชื่อ", "ชื่อเดิมกับชื่อใหม่เหมือนกัน")
            return
        try:
            PatternService.rename(self._selected_pattern, new_name)
        except FileExistsError:
            messagebox.showwarning("เปลี่ยนชื่อ", f"มี pattern '{new_name}' อยู่แล้ว")
            return
        except (FileNotFoundError, ValueError) as e:
            messagebox.showwarning("เปลี่ยนชื่อ", str(e))
            return
        old = self._selected_pattern
        self._selected_pattern = new_name
        if self._ctl_pattern.get().strip() == old:
            self._ctl_pattern.set(new_name)
        self._update_pattern_card(new_name)
        self._refresh_pattern_list()
        self._log(f"[pattern] เปลี่ยนชื่อ {old} → {new_name}")
        messagebox.showinfo("เปลี่ยนชื่อ", f"เปลี่ยนชื่อเป็น '{new_name}' แล้ว")

    def _delete_pattern(self):
        name = self._selected_pattern or self._pat_name.get().strip()
        if not name:
            messagebox.showwarning("ลบ Pattern", "เลือก pattern ที่จะลบก่อน")
            return
        if not messagebox.askyesno("ลบ Pattern", f"ลบ pattern '{name}' ถาวร?"):
            return
        try:
            PatternService.delete(name)
        except FileNotFoundError as e:
            messagebox.showwarning("ลบ Pattern", str(e))
            return
        if self._selected_pattern == name:
            self._selected_pattern = ""
        self._pat_name.delete(0, "end")
        if self._ctl_pattern.get().strip() == name:
            names = [m.name for m in PatternService.list_all()]
            self._ctl_pattern.set(names[0] if names else "")
        self._refresh_pattern_list()
        self._log(f"[pattern] ลบ '{name}' แล้ว")

    def _select_pattern(self, name: str):
        self._selected_pattern = name
        self._pat_name.delete(0, "end")
        self._pat_name.insert(0, name)
        self._ctl_pattern.set(name)
        self._update_pattern_card(name)
        self._show_page("control")

    def _update_pattern_card(self, name: str):
        for m in PatternService.list_all():
            if m.name == name:
                self._card_pat.set(name, f"{m.events} จังหวะ · {m.duration:.0f}s")
                self._st_pat.configure(text=f"Pattern: {name}")
                return
        self._card_pat.set(name, "ไม่พบข้อมูล")

    def _open_patterns_dir(self):
        from paths import app_dir
        import os
        path = app_dir() / "patterns"
        path.mkdir(exist_ok=True)
        os.startfile(path)

    def _browse_adb(self):
        p = filedialog.askopenfilename(filetypes=[("adb.exe", "adb.exe"), ("All", "*.*")])
        if p:
            self._set_vars["ADB_PATH"].set(p)

    # ------------------------------------------------------------------ bot
    def _start_bot(self, args: list[str]):
        try:
            self._save_quiet()
            self._show_page("control")
            self._bot.start(args, log=self._log, on_done=self._on_bot_done)
            self._set_bot_status(True)
        except RuntimeError as e:
            messagebox.showwarning("กำลังรัน", str(e))

    def _on_bot_done(self):
        self.after(0, lambda: self._set_bot_status(False))

    def _set_bot_status(self, running: bool):
        if running:
            self._card_bot.set("กำลังเล่น", "บอททำงานอยู่", COLORS["success"])
            self._st_bot.configure(text="บอท: กำลังเล่น", text_color=COLORS["success"])
        else:
            self._card_bot.set("หยุด", "พร้อมเริ่มใหม่", COLORS["text_dim"])
            self._st_bot.configure(text="บอท: หยุด", text_color=COLORS["muted"])

    def _apply_timing_preset(self, preset: str, save: bool = True):
        presets = {
            "faithful": ("0", "0"),
            "safe": ("0", "280"),
        }
        lead, gap = presets.get(preset, presets["faithful"])
        self._timing_preset = preset
        self._ctl_lead.delete(0, "end")
        self._ctl_lead.insert(0, lead)
        self._ctl_jump_gap.delete(0, "end")
        self._ctl_jump_gap.insert(0, gap)
        if save:
            self._save_quiet()
            self._log(f"[timing] โหมด: {'เป๊ะ' if preset == 'faithful' else 'กัน double jump'}")

    def _start_loop(self):
        p = self._ctl_pattern.get().strip()
        lead = self._ctl_lead.get().strip() or "0"
        gap = self._ctl_jump_gap.get().strip() or "0"
        self._start_bot(["--loop", "--pattern", p, "--lead", lead, "--jump-gap", gap])

    def _start_once(self):
        p = self._ctl_pattern.get().strip()
        lead = self._ctl_lead.get().strip() or "0"
        gap = self._ctl_jump_gap.get().strip() or "0"
        self._start_bot(["--play-pattern", p, "--lead", lead, "--jump-gap", gap])

    def _start_record(self):
        self._start_bot(["--record", self._ctl_pattern.get().strip()])

    def _stop_bot(self):
        self._bot.stop(self._log)

    def _test_adb(self):
        def run():
            ok, msg = AdbService.test(self._log)
            color = COLORS["success"] if ok else COLORS["danger"]
            self.after(0, lambda: self._card_adb.set("เชื่อมต่อแล้ว" if ok else "ไม่เชื่อมต่อ",
                                                     msg, color))
            self.after(0, lambda: self._st_adb.configure(
                text=f"ADB: {'OK' if ok else 'FAIL'}",
                text_color=color))
        threading.Thread(target=run, daemon=True).start()

    def _refresh_status(self):
        self._set_bot_status(self._bot.running)
        pat = self._ctl_pattern.get()
        self._update_pattern_card(pat)
        self.after(3000, self._refresh_status)

    # ------------------------------------------------------------------ log
    def _log(self, msg: str):
        self._log_q.put(msg)

    def _drain_log(self):
        while True:
            try:
                line = self._log_q.get_nowait()
            except queue.Empty:
                break
            self._main_log.append(line)
            self._dash_log.append(line)
            self._ctl_log.append(line)
        self.after(150, self._drain_log)

    def _clear_logs(self):
        self._main_log.clear()
        self._dash_log.clear()
        self._ctl_log.clear()

    # ------------------------------------------------------------------ update
    def _check_update_silent(self):
        threading.Thread(target=self._check_update_worker, args=(False,), daemon=True).start()

    def _check_update(self):
        threading.Thread(target=self._check_update_worker, args=(True,), daemon=True).start()

    def _check_update_worker(self, show_no_update: bool):
        from updater import apply_update, check_for_update, fetch_release_info, restart_app
        self._log("[update] กำลังตรวจสอบ...")
        try:
            remote = fetch_release_info()
            info = check_for_update()
        except Exception as e:
            self._log(f"[update] ตรวจไม่ได้: {e}")
            if show_no_update:
                self.after(0, lambda: messagebox.showerror("อัปเดต", str(e)))
            return
        if remote is None:
            self._log("[update] เชื่อมต่อ GitHub ไม่ได้")
            if show_no_update:
                self.after(0, lambda: messagebox.showerror(
                    "อัปเดต", "เชื่อมต่อ GitHub ไม่ได้ — ตรวจอินเทอร์เน็ต"))
            return
        if info is None:
            self._log(f"[update] เป็นเวอร์ชันล่าสุด v{VERSION} (release v{remote.latest})")
            if show_no_update:
                self.after(0, lambda: messagebox.showinfo(
                    "อัปเดต",
                    f"เป็นเวอร์ชันล่าสุดแล้ว\n\nปัจจุบัน: v{VERSION}\nRelease: v{remote.latest}"))
            return
        self._log(f"[update] พบ v{info.latest} (ปัจจุบัน v{info.current})")

        def ask():
            msg = (f"มีเวอร์ชันใหม่ v{info.latest}\n"
                   f"(ปัจจุบัน v{info.current})\n\nอัปเดตเลยไหม?")
            if messagebox.askyesno("อัปเดต", msg):
                from paths import is_frozen
                self._log("[update] กำลังอัปเดต...")
                if is_frozen():
                    self._log("[update] แอปจะปิดแล้วติดตั้งอัตโนมัติ...")
                    messagebox.showinfo(
                        "อัปเดต",
                        "กำลังดาวน์โหลดและติดตั้ง...\n"
                        "แอปจะปิดเอง แล้วเปิดใหม่อัตโนมัติ")
                ok = apply_update(info, log=self._log)
                if ok and not is_frozen():
                    messagebox.showinfo("อัปเดต", "สำเร็จ! แอปจะรีสตาร์ท")
                    restart_app()
                elif not ok and not is_frozen():
                    messagebox.showerror("อัปเดต", "ล้มเหลว — ดู Log")
        self.after(0, ask)

    def on_close(self):
        self._stop_bot()
        self.destroy()


def run_gui():
    app = CookieRunApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
