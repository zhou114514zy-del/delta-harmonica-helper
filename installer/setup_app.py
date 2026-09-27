"""Delta Harmonica Helper 安装器（Task 28）。

本文件只负责"安装器层"，不触碰任何生产业务逻辑：
    - 把内嵌的 payload（已由 PyInstaller 打包好的 onedir 程序：EXE + _internal + config.json）
      复制到安装目录
    - 创建桌面快捷方式 + 开始菜单快捷方式（指向 DeltaHarmonicaHelper.exe）
    - 写入标准的 Windows 卸载入口（设置 → 应用 / 控制面板 → 程序和功能）
    - 把配套的 uninstall.exe 放进安装目录

用法：
    DeltaHarmonicaHelper_Setup.exe                 图形界面安装（可改安装目录）
    DeltaHarmonicaHelper_Setup.exe /S              静默安装（默认目录）
    DeltaHarmonicaHelper_Setup.exe /S /D=<目录>    静默安装到指定目录
"""

import os
import shutil
import subprocess
import sys
import time
import winreg

APP_NAME = "Delta Harmonica Helper"
APP_EXE = "DeltaHarmonicaHelper.exe"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "Delta Harmonica Helper"
UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DeltaHarmonicaHelper"
LOG_PATH = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "DeltaHarmonicaHelper_install.log")

CREATE_NO_WINDOW = 0x08000000


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def payload_root():
    """内嵌负载所在目录（PyInstaller onefile 解包目录或源码目录）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "payload")


def default_install_dir():
    pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
    return os.path.join(pf, APP_NAME)


def parse_args(argv):
    silent = False
    target = None
    for a in argv:
        u = a.upper()
        if u in ("/S", "/SILENT", "-S", "--SILENT"):
            silent = True
        elif u.startswith("/D="):
            target = a[3:]
        elif u.startswith("/DIR="):
            target = a[5:]
    return silent, target


def public_desktop():
    return os.path.join(os.environ.get("PUBLIC") or r"C:\Users\Public", "Desktop")


def common_start_menu():
    pd = os.environ.get("ProgramData") or r"C:\ProgramData"
    return os.path.join(pd, "Microsoft", "Windows", "Start Menu", "Programs")


def make_shortcut(lnk_path, target, workdir, icon, description):
    """通过 WScript.Shell COM 创建 .lnk（不依赖任何第三方 Python 包）。"""
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$s = $ws.CreateShortcut('%s'); "
        "$s.TargetPath = '%s'; "
        "$s.WorkingDirectory = '%s'; "
        "$s.IconLocation = '%s,0'; "
        "$s.Description = '%s'; "
        "$s.Save()"
    ) % (lnk_path.replace("'", "''"), target.replace("'", "''"),
         workdir.replace("'", "''"), icon.replace("'", "''"),
         description.replace("'", "''"))
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0 or not os.path.isfile(lnk_path):
        raise RuntimeError("快捷方式创建失败: %s | %s" % (lnk_path, (r.stderr or "").strip()))
    log("shortcut created: " + lnk_path)


def copy_payload(dest):
    src = os.path.join(payload_root(), "app")
    if not os.path.isdir(src):
        raise RuntimeError("内嵌负载缺失: " + src)
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest)
    log("payload copied to " + dest)


def install_uninstaller(dest):
    src = os.path.join(payload_root(), "uninstall.exe")
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(dest, "uninstall.exe"))
        log("uninstall.exe installed")
        return True
    log("WARNING: payload 中没有 uninstall.exe")
    return False


def write_uninstall_registry(dest, has_uninstaller):
    exe = os.path.join(dest, APP_EXE)
    size_kb = 0
    for root, _dirs, files in os.walk(dest):
        for f in files:
            try:
                size_kb += os.path.getsize(os.path.join(root, f)) // 1024
            except OSError:
                pass
    key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, 0,
                             winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY)
    with key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, dest)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, exe)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        if has_uninstaller:
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                              '"%s" /S' % os.path.join(dest, "uninstall.exe"))
        else:
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                              'cmd.exe /c rmdir /s /q "%s"' % dest)
    log("uninstall registry written: HKLM\\" + UNINSTALL_KEY)


def do_install(dest, shortcuts=True):
    os.makedirs(dest, exist_ok=True)
    copy_payload(dest)
    has_un = install_uninstaller(dest)
    target = os.path.join(dest, APP_EXE)
    icon = target
    if shortcuts:
        make_shortcut(os.path.join(public_desktop(), APP_NAME + ".lnk"),
                      target, dest, icon, APP_NAME)
        make_shortcut(os.path.join(common_start_menu(), APP_NAME + ".lnk"),
                      target, dest, icon, APP_NAME)
    write_uninstall_registry(dest, has_un)
    return target


# ---------------------------------------------------------------- 图形界面
def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title(APP_NAME + " 安装程序")
    root.geometry("520x230")
    root.resizable(False, False)

    tk.Label(root, text="安装 " + APP_NAME, font=("Microsoft YaHei UI", 12, "bold")).pack(pady=(14, 4))
    tk.Label(root, text="目标文件夹：", anchor="w").pack(fill="x", padx=16)
    var = tk.StringVar(value=default_install_dir())
    row = tk.Frame(root); row.pack(fill="x", padx=16)
    entry = tk.Entry(row, textvariable=var)
    entry.pack(side="left", fill="x", expand=True)

    def browse():
        d = filedialog.askdirectory(parent=root, title="选择安装目录", initialdir=var.get())
        if d:
            var.set(os.path.join(d, APP_NAME) if os.path.basename(d) != APP_NAME else d)

    tk.Button(row, text="浏览…", command=browse).pack(side="left", padx=(6, 0))
    status = tk.Label(root, text="将安装到 Program Files，并创建桌面与开始菜单快捷方式。",
                      fg="#555555", anchor="w", wraplength=480, justify="left")
    status.pack(fill="x", padx=16, pady=(10, 4))

    def run_install():
        dest = var.get().strip()
        if not dest:
            messagebox.showerror(APP_NAME, "请填写安装目录。", parent=root)
            return
        btn_install.config(state="disabled")
        status.config(text="正在安装…")
        root.update_idletasks()
        try:
            do_install(dest)
        except Exception as exc:  # noqa: BLE001
            log("INSTALL FAILED: %r" % (exc,))
            messagebox.showerror(APP_NAME, "安装失败：\n%s" % exc, parent=root)
            btn_install.config(state="normal")
            status.config(text="安装失败。")
            return
        status.config(text="安装完成。")
        messagebox.showinfo(APP_NAME, "安装完成！\n\n桌面快捷方式已创建。", parent=root)
        root.destroy()

    btn_install = tk.Button(root, text="安装", width=14, command=run_install)
    btn_install.pack(pady=6)
    root.mainloop()
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    silent, target = parse_args(argv)
    dest = target or default_install_dir()
    log("=== installer start (silent=%s, dest=%s) ===" % (silent, dest))
    if silent:
        try:
            do_install(dest)
        except Exception as exc:  # noqa: BLE001
            log("INSTALL FAILED: %r" % (exc,))
            return 1
        log("=== installer done OK ===")
        return 0
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
