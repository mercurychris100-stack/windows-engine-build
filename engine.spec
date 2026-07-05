# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# ==============================================================================
# FORCE BOOTLOADER UTF-8 ENVIRONMENT OVERRIDES
# ==============================================================================
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

block_cipher = None

# Collect ALL submodules and data from pocketoptionapi_async so PyInstaller
# registers them as importable modules, not just copies them as data files.
# Using datas alone causes "No module named" errors at runtime because the
# files are present but not on Python's import path inside the exe.
pocketoption_modules = collect_submodules('pocketoptionapi_async')
pocketoption_datas   = collect_data_files('pocketoptionapi_async')

a = Analysis(
    ['engine.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('pocketoptionapi_async', 'pocketoptionapi_async'),
        *pocketoption_datas,
    ],
    hiddenimports=[
        'loguru',
        'websockets',
        'websockets.legacy',
        'websockets.legacy.client',
        'aiohttp_cors',
        'pandas',
        'numpy',
        'statistics',
        'csv',
        *pocketoption_modules,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
