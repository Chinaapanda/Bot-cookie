#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -f venv/Scripts/activate ]; then
    # shellcheck disable=SC1091
    source venv/Scripts/activate
fi
python app.py
