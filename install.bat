@echo off
chcp 65001 >nul
echo ========================================
echo  Cookie Run Bot - ติดตั้ง
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ไม่พบ Python - ติดตั้งจาก https://python.org ก่อน
    echo         ต้องติ๊ก "Add Python to PATH"
    pause
    exit /b 1
)

if not exist venv (
    echo สร้าง virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat
echo ติดตั้ง dependencies...
pip install -r requirements.txt -q

echo.
echo ========================================
echo  ติดตั้งเสร็จ!
echo  เปิดแอป:  run.bat  หรือ  python app.py
echo ========================================
pause
