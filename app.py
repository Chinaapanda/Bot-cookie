"""
Cookie Run Bot — แอปหลัก (GUI)

ดับเบิลคลิกหรือรัน:
    python app.py

ตรวจอัปเดตอัตโนมัติจาก GitHub เมื่อเปิดแอป (ปิดได้ใน settings)
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from paths import app_dir, is_frozen
from settings import load, save, to_dict
from version import GITHUB_URL, VERSION


class CookieRunApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Cookie Run Bot v{VERSION}")
        self.geometry("720x560")
        self.minsize(600, 480)

        self._proc: subprocess.Popen | None = None
        self._log_q: queue.Queue[str] = queue.Queue()
        self._cfg = to_dict()

        self._build_ui()
        self._load_fields()
        self.after(200, self._drain_log)
        if self._cfg.get("auto_check_update", True):
            self.after(800, self._check_update_silent)

    # ---- UI ----------------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text=f"Cookie Run Bot  v{VERSION}", font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(top, text="ตรวจอัปเดต", command=self._check_update).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="GitHub", command=lambda: self._open_url(GITHUB_URL)).pack(side=tk.RIGHT)

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # --- แท็บเล่น ---
        play_tab = ttk.Frame(nb, padding=8)
        nb.add(play_tab, text="เล่น")

        row = 0
        ttk.Label(play_tab, text="Pattern:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.var_pattern = tk.StringVar(value="EP1")
        ttk.Entry(play_tab, textvariable=self.var_pattern, width=20).grid(row=row, column=1, sticky=tk.W)
        row += 1

        ttk.Label(play_tab, text="Lead (ms):").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.var_lead = tk.StringVar(value="0")
        ttk.Entry(play_tab, textvariable=self.var_lead, width=10).grid(row=row, column=1, sticky=tk.W)
        ttk.Label(play_tab, text="(ลบ = ช้าลง, บวก = เร็วขึ้น)").grid(row=row, column=2, sticky=tk.W, padx=8)
        row += 1

        btn_frame = ttk.Frame(play_tab)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=12, sticky=tk.W)
        ttk.Button(btn_frame, text="▶ เล่นวน (Loop+Pattern)", command=self._start_loop).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="▶ เล่น 1 รอบ", command=self._start_once).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="⏺ อัด Pattern", command=self._start_record).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="■ หยุด", command=self._stop_bot).pack(side=tk.LEFT, padx=4)
        row += 1

        ttk.Separator(play_tab, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        row += 1
        ttk.Button(play_tab, text="ทดสอบเชื่อมต่อ ADB", command=self._test_adb).grid(row=row, column=0, sticky=tk.W)

        # --- แท็บตั้งค่า ---
        cfg_tab = ttk.Frame(nb, padding=8)
        nb.add(cfg_tab, text="ตั้งค่า")

        fields = [
            ("ADB Path", "ADB_PATH", 50),
            ("ADB Serial", "ADB_SERIAL", 30),
            ("Jump X", "TAP_X", 8),
            ("Jump Y", "TAP_Y", 8),
            ("Slide X", "SLIDE_X", 8),
            ("Slide Y", "SLIDE_Y", 8),
        ]
        self._vars: dict[str, tk.StringVar] = {}
        for i, (label, key, w) in enumerate(fields):
            ttk.Label(cfg_tab, text=label + ":").grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            self._vars[key] = var
            ttk.Entry(cfg_tab, textvariable=var, width=w).grid(row=i, column=1, sticky=tk.W)

        self.var_auto_update = tk.BooleanVar(value=True)
        ttk.Checkbutton(cfg_tab, text="ตรวจอัปเดตอัตโนมัติเมื่อเปิดแอป",
                        variable=self.var_auto_update).grid(row=len(fields), column=0, columnspan=2, sticky=tk.W, pady=8)
        ttk.Button(cfg_tab, text="บันทึกการตั้งค่า", command=self._save_settings).grid(
            row=len(fields) + 1, column=0, sticky=tk.W, pady=4)

        # --- log ---
        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.log_box = scrolledtext.ScrolledText(log_frame, height=12, state=tk.DISABLED, font=("Consolas", 9))
        self.log_box.pack(fill=tk.BOTH, expand=True)

    def _load_fields(self):
        self._cfg = to_dict()
        self.var_pattern.set(self._cfg.get("default_pattern", "EP1"))
        self.var_lead.set(str(self._cfg.get("default_lead", 0)))
        for key, var in self._vars.items():
            var.set(str(self._cfg.get(key, "")))
        self.var_auto_update.set(self._cfg.get("auto_check_update", True))

    def _save_settings(self):
        data = load()
        for key, var in self._vars.items():
            val = var.get().strip()
            if key in ("TAP_X", "TAP_Y", "SLIDE_X", "SLIDE_Y"):
                data[key] = int(val) if val.lstrip("-").isdigit() else 0
            else:
                data[key] = val
        data["default_pattern"] = self.var_pattern.get().strip()
        try:
            data["default_lead"] = int(self.var_lead.get().strip())
        except ValueError:
            data["default_lead"] = 0
        data["auto_check_update"] = self.var_auto_update.get()
        save(data)
        self._log("[settings] บันทึกแล้ว")
        messagebox.showinfo("บันทึก", "บันทึกการตั้งค่าแล้ว")

    # ---- bot subprocess ----------------------------------------------------
    def _bot_cmd(self, *extra: str) -> list[str]:
        if is_frozen():
            return [sys.executable, "--bot", *extra]
        return [sys.executable, str(app_dir() / "bot.py"), *extra]

    def _start_bot(self, args: list[str]):
        if self._proc and self._proc.poll() is None:
            messagebox.showwarning("กำลังรัน", "บอทกำลังทำงานอยู่ กดหยุดก่อน")
            return
        self._save_settings_quiet()
        cmd = self._bot_cmd(*args)
        self._log(f">>> {' '.join(cmd)}")
        self._proc = subprocess.Popen(
            cmd, cwd=app_dir(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def _save_settings_quiet(self):
        data = load()
        for key, var in self._vars.items():
            val = var.get().strip()
            if key in ("TAP_X", "TAP_Y", "SLIDE_X", "SLIDE_Y"):
                try:
                    data[key] = int(val)
                except ValueError:
                    pass
            else:
                data[key] = val
        data["default_pattern"] = self.var_pattern.get().strip()
        try:
            data["default_lead"] = int(self.var_lead.get().strip())
        except ValueError:
            data["default_lead"] = 0
        save(data)

    def _read_stdout(self):
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            self._log_q.put(line.rstrip())
        self._log_q.put("[bot] จบการทำงาน")

    def _start_loop(self):
        p = self.var_pattern.get().strip() or "EP1"
        lead = self.var_lead.get().strip() or "0"
        self._start_bot(["--loop", "--pattern", p, "--lead", lead])

    def _start_once(self):
        p = self.var_pattern.get().strip() or "EP1"
        lead = self.var_lead.get().strip() or "0"
        self._start_bot(["--play-pattern", p, "--lead", lead])

    def _start_record(self):
        p = self.var_pattern.get().strip() or "EP1"
        self._start_bot(["--record", p])

    def _stop_bot(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._log("[app] ส่งคำสั่งหยุดบอท")

    def _test_adb(self):
        def run():
            try:
                from settings import apply_user_settings
                apply_user_settings()
                from adb_controller import ADBController
                adb = ADBController()
                ok = adb.connect()
                if ok:
                    w, h = adb.screen_size()
                    self._log_q.put(f"[ADB] OK  จอ {w}x{h}")
                else:
                    self._log_q.put("[ADB] เชื่อมต่อไม่สำเร็จ")
            except Exception as e:
                self._log_q.put(f"[ADB] error: {e}")
        threading.Thread(target=run, daemon=True).start()

    # ---- update ------------------------------------------------------------
    def _check_update_silent(self):
        threading.Thread(target=self._check_update_worker, args=(False,), daemon=True).start()

    def _check_update(self):
        threading.Thread(target=self._check_update_worker, args=(True,), daemon=True).start()

    def _check_update_worker(self, show_no_update: bool):
        from updater import apply_update, check_for_update, restart_app

        self._log_q.put("[update] กำลังตรวจสอบ...")
        try:
            info = check_for_update()
        except Exception as e:
            self._log_q.put(f"[update] ตรวจไม่ได้: {e}")
            if show_no_update:
                self.after(0, lambda: messagebox.showerror("อัปเดต", str(e)))
            return
        if info is None:
            self._log_q.put(f"[update] เป็นเวอร์ชันล่าสุดแล้ว (v{VERSION})")
            if show_no_update:
                self.after(0, lambda: messagebox.showinfo("อัปเดต", f"เป็นเวอร์ชันล่าสุดแล้ว v{VERSION}"))
            return
        self._log_q.put(f"[update] พบเวอร์ชันใหม่ v{info.latest}")

        def ask():
            msg = f"มีเวอร์ชันใหม่ v{info.latest}\n(ปัจจุบัน v{info.current})\n\nอัปเดตเลยไหม?"
            if info.notes:
                msg += f"\n\n{info.notes[:300]}"
            if messagebox.askyesno("อัปเดต", msg):
                self._log("[update] กำลังอัปเดต...")
                ok = apply_update(info, log=self._log)
                if ok:
                    messagebox.showinfo("อัปเดต", "อัปเดตสำเร็จ! แอปจะรีสตาร์ท")
                    restart_app()
                else:
                    messagebox.showerror("อัปเดต", "อัปเดตล้มเหลว ดู Log")
        self.after(0, ask)

    # ---- helpers -----------------------------------------------------------
    def _log(self, msg: str):
        self._log_q.put(msg)

    def _drain_log(self):
        while True:
            try:
                line = self._log_q.get_nowait()
            except queue.Empty:
                break
            self.log_box.configure(state=tk.NORMAL)
            self.log_box.insert(tk.END, line + "\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state=tk.DISABLED)
        self.after(200, self._drain_log)

    @staticmethod
    def _open_url(url: str):
        import webbrowser
        webbrowser.open(url)

    def on_close(self):
        self._stop_bot()
        self.destroy()


def run_gui():
    app = CookieRunApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


def main():
    # โหมด subprocess จาก .exe: CookieRunBot.exe --bot --loop ...
    if "--bot" in sys.argv:
        sys.argv = [a for a in sys.argv if a != "--bot"]
        from bot import main as bot_main
        bot_main()
        return
    run_gui()


if __name__ == "__main__":
    main()
