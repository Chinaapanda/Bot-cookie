@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo ติดตั้ง PyInstaller...
pip install pyinstaller -q

echo สร้าง .exe ...
pyinstaller --noconfirm CookieRunBot.spec

echo.
echo เสร็จ! ไฟล์อยู่ที่: dist\CookieRunBot\
echo แจกจ่ายทั้งโฟลเดอร์ dist\CookieRunBot\ (รวม CookieRunBot.exe)
pause
