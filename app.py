"""
Cookie Run Bot — แอปหลัก (GUI)

ดับเบิลคลิกหรือรัน:
    python app.py
    run.bat
"""
from __future__ import annotations

import sys


def main():
    if "--bot" in sys.argv:
        sys.argv = [a for a in sys.argv if a != "--bot"]
        from bot import main as bot_main
        bot_main()
        return
    if "--calibrate" in sys.argv:
        from calibrate import run_calibrate
        run_calibrate()
        return
    from gui.main_window import run_gui
    run_gui()


if __name__ == "__main__":
    main()
