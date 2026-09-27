import sys

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

EXE = r"C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\dist\DeltaHarmonicaHelper\DeltaHarmonicaHelper.exe"

CORE = [
    "input", "score", "playback", "playback_executor",
    "harmonica_app", "app_controller", "ui", "main",
]

found = {}
pyz_names = []

car = CArchiveReader(EXE)
# Extract PYZ.pyz into memory
if "PYZ.pyz" not in car.toc:
    print("NO PYZ.pyz found; toc keys:", list(car.toc.keys())[:20])
    sys.exit(1)
pyz_data = car.extract("PYZ.pyz")

import io, os, tempfile
pyz_path = os.path.join(tempfile.gettempdir(), "dsh_pyz.pyz")
with open(pyz_path, "wb") as f:
    f.write(pyz_data)
zr = ZlibArchiveReader(pyz_path)
for name in zr.toc:
    # normalize module names
    key = name
    if key.endswith(".pyc"):
        key = key[:-4]
    pyz_names.append(key)
    base = key.split(".")[0]
    if base in CORE and base not in found:
        found[base] = key

print("PYZ total modules:", len(pyz_names))
print("--- core modules present ---")
for c in CORE:
    print("  %-20s %s" % (c, found.get(c, "MISSING")))
print("--- pynput present ---")
pn = [n for n in pyz_names if n.startswith("pynput")]
print("  pynput modules:", len(pn))
for n in sorted(pn):
    print("    " + n)
print("--- tkinter present ---")
tk = [n for n in pyz_names if n.startswith("tkinter")]
print("  tkinter modules:", len(tk))
