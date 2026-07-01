#!/usr/bin/env bash
# สำหรับ Git Bash / WSL
set -e
cd "$(dirname "$0")"

echo "========================================"
echo " Cookie Run Bot - ติดตั้ง"
echo "========================================"

if ! command -v python &>/dev/null; then
    echo "[ERROR] ไม่พบ Python - ติดตั้งจาก https://python.org"
    exit 1
fi

if [ ! -d venv ]; then
    echo "สร้าง virtual environment..."
    python -m venv venv
fi

# shellcheck disable=SC1091
source venv/Scripts/activate

echo "ติดตั้ง dependencies..."
pip install -r requirements.txt -q

echo ""
echo "========================================"
echo " ติดตั้งเสร็จ!"
echo " เปิดแอป:  bash run.sh  หรือ  python app.py"
echo "========================================"
