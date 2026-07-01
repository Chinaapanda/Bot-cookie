"""หน้า Calibrate — preview จอ + คลิกหาพิกัด + ตั้ง ROI"""
from __future__ import annotations

import subprocess
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image

import config
from detector import roi_to_pixels
from gui.theme import COLORS, FONT_BODY, FONT_SMALL, PAD
from paths import app_dir, is_frozen


class CalibratePage(ctk.CTkScrollableFrame):
    def __init__(self, master, on_coords_changed=None):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self._on_coords_changed = on_coords_changed
        self._img: np.ndarray | None = None
        self._disp_scale = 1.0
        self._disp_size = (800, 450)
        self._last_click = (0, 0)
        self._ctk_image: ctk.CTkImage | None = None

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, PAD))
        ctk.CTkLabel(hdr, text="Calibrate หน้าจอ", font=("Segoe UI", 15, "bold"),
                     text_color=COLORS["text"]).pack(side="left")
        ctk.CTkButton(hdr, text="รีเฟรชภาพ", width=100, command=self._capture,
                      fg_color=COLORS["card_hover"]).pack(side="right", padx=4)
        ctk.CTkButton(hdr, text="OpenCV เต็ม", width=110, command=self._open_opencv,
                      fg_color=COLORS["accent"], text_color=COLORS["bg_dark"]).pack(side="right")

        ctk.CTkLabel(self, text="คลิกบนภาพเพื่ออ่านพิกัด → กดปุ่มด้านล่างเพื่อตั้ง Jump / Slide",
                     font=FONT_SMALL, text_color=COLORS["text_dim"]).grid(row=1, column=0, sticky="w", pady=(0, 6))

        # Preview
        self._canvas = ctk.CTkLabel(self, text="กด รีเฟรชภาพ เพื่อจับหน้าจอ LDPlayer",
                                    fg_color=COLORS["card"], corner_radius=10,
                                    width=800, height=450)
        self._canvas.grid(row=2, column=0, sticky="ew", pady=(0, PAD))
        self._canvas.bind("<Button-1>", self._on_click)

        # Last click + assign buttons
        act = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=10,
                           border_width=1, border_color=COLORS["border"])
        act.grid(row=3, column=0, sticky="ew", pady=(0, PAD))
        self._coord_lbl = ctk.CTkLabel(act, text="พิกัด: —", font=FONT_BODY, text_color=COLORS["text"])
        self._coord_lbl.pack(side="left", padx=PAD, pady=PAD)
        ctk.CTkButton(act, text="ใช้เป็น Jump", command=lambda: self._assign("jump"),
                      fg_color=COLORS["accent"], text_color=COLORS["bg_dark"]).pack(side="left", padx=4)
        ctk.CTkButton(act, text="ใช้เป็น Slide", command=lambda: self._assign("slide"),
                      fg_color=COLORS["card_hover"]).pack(side="left", padx=4)

        # Current coords
        cur = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=10,
                           border_width=1, border_color=COLORS["border"])
        cur.grid(row=4, column=0, sticky="ew", pady=(0, PAD))
        cur.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(cur, text="Jump (X,Y)", font=FONT_SMALL, text_color=COLORS["text_dim"]).grid(
            row=0, column=0, padx=PAD, pady=8, sticky="w")
        self._jump_xy = ctk.CTkEntry(cur, width=120, font=FONT_BODY)
        self._jump_xy.grid(row=0, column=1, padx=4, pady=8, sticky="w")
        ctk.CTkLabel(cur, text="Slide (X,Y)", font=FONT_SMALL, text_color=COLORS["text_dim"]).grid(
            row=0, column=2, padx=PAD, pady=8, sticky="w")
        self._slide_xy = ctk.CTkEntry(cur, width=120, font=FONT_BODY)
        self._slide_xy.grid(row=0, column=3, padx=4, pady=8, sticky="w")

        # ROI
        roi_box = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=10,
                               border_width=1, border_color=COLORS["border"])
        roi_box.grid(row=5, column=0, sticky="ew", pady=(0, PAD))
        ctk.CTkLabel(roi_box, text="โซนตรวจจับ (สัดส่วน 0–1: x1,y1,x2,y2)",
                     font=FONT_SMALL, text_color=COLORS["accent"]).grid(
            row=0, column=0, columnspan=2, padx=PAD, pady=(PAD, 4), sticky="w")
        self._roi_jump = ctk.CTkEntry(roi_box, width=320, font=FONT_BODY,
                                      placeholder_text="ROI_JUMP")
        self._roi_jump.grid(row=1, column=0, padx=PAD, pady=4, sticky="w")
        ctk.CTkLabel(roi_box, text="ROI_JUMP", font=FONT_SMALL,
                     text_color=COLORS["muted"]).grid(row=1, column=1, sticky="w")
        self._roi_slide = ctk.CTkEntry(roi_box, width=320, font=FONT_BODY,
                                       placeholder_text="ROI_SLIDE")
        self._roi_slide.grid(row=2, column=0, padx=PAD, pady=4, sticky="w")
        ctk.CTkLabel(roi_box, text="ROI_SLIDE", font=FONT_SMALL,
                     text_color=COLORS["muted"]).grid(row=2, column=1, sticky="w")

        ctk.CTkButton(self, text="บันทึก Calibrate", height=40, font=FONT_BODY,
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color=COLORS["bg_dark"], command=self._save).grid(row=6, column=0, sticky="w")

        self.load_from_config()

    def load_from_config(self):
        self._jump_xy.delete(0, "end")
        self._jump_xy.insert(0, f"{config.TAP_X},{config.TAP_Y}")
        self._slide_xy.delete(0, "end")
        self._slide_xy.insert(0, f"{config.SLIDE_X},{config.SLIDE_Y}")
        self._roi_jump.delete(0, "end")
        self._roi_jump.insert(0, ",".join(str(round(v, 3)) for v in config.ROI_JUMP))
        self._roi_slide.delete(0, "end")
        self._roi_slide.insert(0, ",".join(str(round(v, 3)) for v in config.ROI_SLIDE))

    def _capture(self):
        def run():
            try:
                from settings import apply_user_settings
                apply_user_settings()
                from adb_controller import ADBController
                adb = ADBController()
                if not adb.connect():
                    self.after(0, lambda: messagebox.showerror("ADB", "เชื่อมต่อไม่สำเร็จ"))
                    return
                img = adb.screencap()
                self.after(0, lambda: self._show_image(img))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Calibrate", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _render_overlay(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        vis = img.copy()
        for roi, color, label in (
            (config.ROI_JUMP, (0, 165, 255), "JUMP"),
            (config.ROI_SLIDE, (255, 100, 0), "SLIDE"),
            (config.ROI_PLAYER, (0, 255, 0), "PLAYER"),
        ):
            x1, y1, x2, y2 = roi_to_pixels(roi, w, h)
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            cv2.putText(vis, label, (x1, max(20, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        cv2.circle(vis, (config.TAP_X, config.TAP_Y), 12, (0, 0, 255), 2)
        cv2.putText(vis, "JUMP", (config.TAP_X + 14, config.TAP_Y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        cv2.circle(vis, (config.SLIDE_X, config.SLIDE_Y), 12, (255, 0, 255), 2)
        cv2.putText(vis, "SLIDE", (config.SLIDE_X + 14, config.SLIDE_Y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)
        return vis

    def _show_image(self, img: np.ndarray):
        self._img = img
        vis = self._render_overlay(img)
        h, w = vis.shape[:2]
        max_w, max_h = 900, 500
        scale = min(max_w / w, max_h / h, 1.0)
        self._disp_scale = scale
        dw, dh = int(w * scale), int(h * scale)
        self._disp_size = (dw, dh)
        resized = cv2.resize(vis, (dw, dh))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        self._ctk_image = ctk.CTkImage(light_image=pil, dark_image=pil, size=(dw, dh))
        self._canvas.configure(image=self._ctk_image, text="")

    def _on_click(self, event):
        if self._img is None:
            return
        x = int(event.x / self._disp_scale)
        y = int(event.y / self._disp_scale)
        self._last_click = (x, y)
        self._coord_lbl.configure(text=f"พิกัด: x={x}, y={y}")

    def _assign(self, kind: str):
        x, y = self._last_click
        if kind == "jump":
            self._jump_xy.delete(0, "end")
            self._jump_xy.insert(0, f"{x},{y}")
        else:
            self._slide_xy.delete(0, "end")
            self._slide_xy.insert(0, f"{x},{y}")
        if self._img is not None:
            self._apply_preview_coords()
            self._show_image(self._img)

    def _apply_preview_coords(self):
        try:
            jx, jy = self._jump_xy.get().replace(" ", "").split(",")
            config.TAP_X, config.TAP_Y = int(jx), int(jy)
        except ValueError:
            pass
        try:
            sx, sy = self._slide_xy.get().replace(" ", "").split(",")
            config.SLIDE_X, config.SLIDE_Y = int(sx), int(sy)
        except ValueError:
            pass

    def _parse_roi(self, text: str) -> tuple[float, float, float, float] | None:
        try:
            parts = [float(p.strip()) for p in text.split(",")]
            if len(parts) == 4:
                return tuple(parts)  # type: ignore[return-value]
        except ValueError:
            pass
        return None

    def _save(self):
        from settings import load, save
        data = load()
        try:
            jx, jy = self._jump_xy.get().replace(" ", "").split(",")
            data["TAP_X"], data["TAP_Y"] = int(jx), int(jy)
            config.TAP_X, config.TAP_Y = int(jx), int(jy)
        except ValueError:
            messagebox.showerror("Calibrate", "รูปแบบ Jump X,Y ไม่ถูกต้อง")
            return
        try:
            sx, sy = self._slide_xy.get().replace(" ", "").split(",")
            data["SLIDE_X"], data["SLIDE_Y"] = int(sx), int(sy)
            config.SLIDE_X, config.SLIDE_Y = int(sx), int(sy)
        except ValueError:
            messagebox.showerror("Calibrate", "รูปแบบ Slide X,Y ไม่ถูกต้อง")
            return
        rj = self._parse_roi(self._roi_jump.get())
        rs = self._parse_roi(self._roi_slide.get())
        if rj:
            data["ROI_JUMP"] = list(rj)
            config.ROI_JUMP = rj
        if rs:
            data["ROI_SLIDE"] = list(rs)
            config.ROI_SLIDE = rs
        save(data)
        messagebox.showinfo("Calibrate", "บันทึกพิกัดและโซนแล้ว")
        if self._on_coords_changed:
            self._on_coords_changed()
        if self._img is not None:
            self._show_image(self._img)

    def _open_opencv(self):
        if is_frozen():
            cmd = [sys.executable, "--calibrate"]
        else:
            cmd = [sys.executable, str(app_dir() / "calibrate.py")]
        subprocess.Popen(cmd, cwd=app_dir())
        messagebox.showinfo(
            "OpenCV Calibrate",
            "เปิดหน้าต่าง Calibrate แยกแล้ว\n\n"
            "คลิก=พิกัด | j/k=template | s=เซฟภาพ | r=รีเฟรช | q=ออก",
        )
