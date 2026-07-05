import sys
import os

# Ensure the bundled pocketoptionapi_async folder is importable at runtime.
# PyInstaller extracts bundled files to sys._MEIPASS but doesn't always add
# it to sys.path, causing "No module named" errors even when the files exist.
if hasattr(sys, '_MEIPASS'):
    sys.path.insert(0, sys._MEIPASS)
    sys.path.insert(0, os.path.join(sys._MEIPASS, 'pocketoptionapi_async'))
