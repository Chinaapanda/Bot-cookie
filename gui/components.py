"""คอมโพเนนต์ UI ที่ใช้ซ้ำได้"""
from __future__ import annotations

import customtkinter as ctk

from gui.theme import COLORS, FONT_BODY, FONT_HEAD, FONT_SMALL, PAD


class StatusCard(ctk.CTkFrame):
    """การ์ดแสดงสถานะ (Dashboard)"""

    def __init__(self, master, title: str, icon: str = ""):
        super().__init__(master, fg_color=COLORS["card"], corner_radius=12,
                         border_width=1, border_color=COLORS["border"])
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ctk.CTkLabel(top, text=f"{icon} {title}", font=FONT_SMALL,
                     text_color=COLORS["text_dim"]).pack(side="left")

        self._value = ctk.CTkLabel(self, text="—", font=FONT_HEAD, text_color=COLORS["text"])
        self._value.pack(anchor="w", padx=PAD, pady=(0, 4))

        self._sub = ctk.CTkLabel(self, text="", font=FONT_SMALL, text_color=COLORS["muted"])
        self._sub.pack(anchor="w", padx=PAD, pady=(0, PAD))

    def set(self, value: str, sub: str = "", color: str | None = None):
        self._value.configure(text=value, text_color=color or COLORS["text"])
        self._sub.configure(text=sub)


class SectionTitle(ctk.CTkLabel):
    def __init__(self, master, text: str):
        super().__init__(master, text=text, font=FONT_HEAD, text_color=COLORS["text"],
                         anchor="w")


class LogPanel(ctk.CTkFrame):
    """แผง log แบบ monospace"""

    def __init__(self, master, height: int = 200):
        super().__init__(master, fg_color=COLORS["card"], corner_radius=10,
                         border_width=1, border_color=COLORS["border"])
        self._box = ctk.CTkTextbox(
            self, font=("Consolas", 11), fg_color="#12121a",
            text_color=COLORS["text"], corner_radius=8, height=height,
            activate_scrollbars=True,
        )
        self._box.pack(fill="both", expand=True, padx=8, pady=8)
        self._box.configure(state="disabled")

    def append(self, line: str):
        self._box.configure(state="normal")
        self._box.insert("end", line + "\n")
        self._box.see("end")
        self._box.configure(state="disabled")

    def clear(self):
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        self._box.configure(state="disabled")


class NavButton(ctk.CTkButton):
    def __init__(self, master, text: str, command, active: bool = False):
        fg = COLORS["accent"] if active else "transparent"
        tc = COLORS["bg_dark"] if active else COLORS["text"]
        hover = COLORS["accent_hover"] if active else COLORS["card_hover"]
        super().__init__(
            master, text=text, command=command, anchor="w",
            font=FONT_BODY, height=40, corner_radius=8,
            fg_color=fg, text_color=tc, hover_color=hover,
            border_width=0,
        )
