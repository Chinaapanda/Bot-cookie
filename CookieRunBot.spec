# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — รัน: pyinstaller CookieRunBot.spec"""

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / 'app.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / 'templates'), 'templates'),
    ] if (root / 'templates').exists() else [],
    hiddenimports=[
        'cv2', 'numpy', 'PIL', 'keyboard', 'settings', 'updater', 'paths', 'version',
        'bot', 'pattern', 'auto_lobby', 'adb_controller', 'detector', 'config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CookieRunBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CookieRunBot',
)
