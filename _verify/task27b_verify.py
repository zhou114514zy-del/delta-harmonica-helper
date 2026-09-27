"""Task 27B 验证：EXE manifest + 是否真的包含 Task 27A 修复。

1. 从 EXE 资源里读 RT_MANIFEST，检查 requestedExecutionLevel=requireAdministrator
2. 解包 EXE 内嵌 PYZ，取出 harmonica_app 的字节码，反汇编 _complete_note，
   统计 release_all / apply 调用次数，用来判断打包进去的到底是修复前还是修复后的版本。
3. 用当前源码现场编译一份 _complete_note，做同样的统计做对照。
"""
import ctypes
import dis
import io
import marshal
import os
import sys
import tempfile
import types
from ctypes import wintypes

EXE = r"C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\dist\DeltaHarmonicaHelper\DeltaHarmonicaHelper.exe"
SRC = r"C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\harmonica_app.py"

print("=" * 70)
print("1. RT_MANIFEST (from EXE resources)")
print("=" * 70)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.LoadLibraryExW.restype = wintypes.HMODULE
k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
k32.FindResourceW.restype = wintypes.HANDLE
k32.FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPCWSTR]
k32.SizeofResource.restype = wintypes.DWORD
k32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
k32.LoadResource.restype = wintypes.HANDLE
k32.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
k32.LockResource.restype = ctypes.c_void_p
k32.LockResource.argtypes = [wintypes.HANDLE]

LOAD_LIBRARY_AS_DATAFILE = 0x00000002
RT_MANIFEST = 24

manifest_text = ""
h = k32.LoadLibraryExW(EXE, None, LOAD_LIBRARY_AS_DATAFILE)
if not h:
    print("  LoadLibraryExW failed:", ctypes.get_last_error())
else:
    res = k32.FindResourceW(h, ctypes.cast(1, wintypes.LPCWSTR),
                            ctypes.cast(RT_MANIFEST, wintypes.LPCWSTR))
    if not res:
        # 兜底：枚举常见 (name, type) 组合
        for nm in (1, 2, 3):
            for ty in (RT_MANIFEST, 24):
                res = k32.FindResourceW(h, ctypes.cast(nm, wintypes.LPCWSTR),
                                        ctypes.cast(ty, wintypes.LPCWSTR))
                if res:
                    break
            if res:
                break
    if not res:
        print("  RT_MANIFEST not found, err=", ctypes.get_last_error())
    else:
        size = k32.SizeofResource(h, res)
        loaded = k32.LoadResource(h, res)
        ptr = k32.LockResource(loaded)
        manifest_text = ctypes.string_at(ptr, size).decode("utf-8", "replace")
        print("  manifest size =", size)
        print("  ---- manifest ----")
        for line in manifest_text.splitlines():
            print("  " + line)
        print("  ------------------")

print()
print("requireAdministrator in manifest:", "requireAdministrator" in manifest_text)

# 兜底：直接在 EXE 字节里找（manifest 以明文 XML 存在 .rsrc 中）
raw_exe = open(EXE, "rb").read()
print("EXE bytes contain 'requireAdministrator':", b"requireAdministrator" in raw_exe)
print("EXE bytes contain 'level=\"requireAdministrator\"':",
      b'level="requireAdministrator"' in raw_exe)
print("EXE bytes contain 'asInvoker':", b"asInvoker" in raw_exe)

print()
print("=" * 70)
print("2. Bundled bytecode: harmonica_app._complete_note")
print("=" * 70)

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader  # noqa: E402

car = CArchiveReader(EXE)
pyz_data = car.extract("PYZ.pyz")
tmp = os.path.join(tempfile.gettempdir(), "t27b_pyz.pyz")
with open(tmp, "wb") as fh:
    fh.write(pyz_data)
zr = ZlibArchiveReader(tmp)


def find_func(code, name):
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            if const.co_name == name:
                return const
            got = find_func(const, name)
            if got is not None:
                return got
    return None


def stats(code):
    insns = list(dis.get_instructions(code))
    rel = sum(1 for i in insns if getattr(i, "argval", None) == "release_all")
    app = sum(1 for i in insns if getattr(i, "argval", None) == "apply")
    return rel, app, len(insns)


bundled = zr.extract("harmonica_app")
print("  bundled module type:", type(bundled).__name__)
# ZlibArchive.extract for a .pyc returns a code object (PyInstaller unmarshals it)
if isinstance(bundled, types.CodeType):
    code = bundled
else:
    raw = zr.extract("harmonica_app")
    code = marshal.loads(raw[16:]) if isinstance(raw, (bytes, bytearray)) else raw
fn_b = find_func(code, "_complete_note")
print("  found _complete_note:", fn_b is not None)
rel_b, app_b, n_b = stats(fn_b)
print("  BUNDLED  release_all=%d  apply=%d  (instructions=%d)" % (rel_b, app_b, n_b))

src_text = open(SRC, "r", encoding="utf-8").read()
code_src = compile(src_text, "harmonica_app.py", "exec")
fn_s = find_func(code_src, "_complete_note")
rel_s, app_s, n_s = stats(fn_s)
print("  SOURCE   release_all=%d  apply=%d  (instructions=%d)" % (rel_s, app_s, n_s))

print()
print("  ---- bundled _complete_note disassembly ----")
for i in dis.get_instructions(fn_b):
    if getattr(i, "argval", None) in ("release_all", "apply", "start_current",
                                      "stop_current_and_advance", "current_state"):
        print("    %-28s %s" % (i.opname, i.argval))

print()
print("=" * 70)
print("3. VERDICT")
print("=" * 70)
print("  manifest requireAdministrator :", "PASS" if "requireAdministrator" in manifest_text else "FAIL")
fixed = (rel_b == 2 and app_b == 1)
print("  bundled == Task 27A fixed code:", "PASS" if fixed else "FAIL")
print("  bundled stats == source stats  :", "PASS" if (rel_b, app_b) == (rel_s, app_s) else "FAIL")
os.remove(tmp)
