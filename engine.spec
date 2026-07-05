# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

# FIX: This automatically finds the correct folder on GitHub's Windows computer
site_packages = [p for p in sys.path if 'site-packages' in p]

pocketoption_modules = collect_submodules('pocketoptionapi_async')
pocketoption_datas   = collect_data_files('pocketoptionapi_async')

a = Analysis(
    ['dist/engine.py'],  # Points to PyArmor folder
    pathex=['.', *site_packages], # Automatically uses the Windows path on GitHub
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
        'pydantic',        # Explicitly tells Windows to include Pydantic
        'pydantic_core',   # Explicitly tells Windows to include Pydantic Core
        *pocketoption_modules,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'] if os.path.exists('runtime_hook.py') else [],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data)

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
    console=False,      # Hides the console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],  # Adds your logo
)
