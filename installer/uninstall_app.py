"""Delta Harmonica Helper 卸载器（Task 28）。

由安装器放进安装目录，并注册为 Windows 卸载入口。

职责（只做"安装器层"，不碰业务逻辑）：
    - 删除桌面 / 开始菜单快捷方式
    - 删除 HKLM 卸载注册表项
    - 删除安装目录主体（EXE、_internal、config.json、uninstall.exe）
    - **保留用户数据**：如果安装目录里存在含文件的 Scores 谱库目录，
      会先把它搬到用户数据目录（%LOCALAPPDATA%\\Delta Harmonica Helper\\Scores）再删除程序主体

自删除：uninstaller 不能删除正在运行的自己，因此会先把自身复制到 %TEMP% 再在临时副本里执行清理。

用法：
    uninstall.exe          图形界面卸载（带确认）
    uninstall.exe /S       静默卸载
    uninstall.exe /S /DIR=<安装目录>
"""

import os
import shutil
import subprocess
import sys
import time
import winreg

APP_NAME = "Delta Harmonica Helper"
APP_EXE = "DeltaHarmonicaHelper.exe"
UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DeltaHarmonicaHelper"
LOG_PATH = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "DeltaHarmonicaHelper_uninstall.log")

CREATE_NO_WINDOW = 0x08000000
_FROM_TEMP_FLAG = "/FROMTEMP"


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def parse_args(argv):
    silent = False
    target = None
    from_temp = False
    for a in argv:
        u = a.upper()
        if u in ("/S", "/SILENT", "-S", "--SILENT"):
            silent = True
        elif u == _FROM_TEMP_FLAG:
            from_temp = True
        elif u.startswith("/D="):
            target = a[3:]
        elif u.startswith("/DIR="):
            target = a[5:]
    return silent, target, from_temp


def install_dir_from_registry():
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, 0,
                                winreg.KEY_READ | view) as k:
                return winreg.QueryValueEx(k, "InstallLocation")[0]
        except OSError:
            continue
    return None


def public_desktop():
    return os.path.join(os.environ.get("PUBLIC") or r"C:\Users\Public", "Desktop")


def common_start_menu():
    pd = os.environ.get("ProgramData") or r"C:\ProgramData"
    return os.path.join(pd, "Microsoft", "Windows", "Start Menu", "Programs")


def remove_shortcuts():
    removed = []
    for p in (os.path.join(public_desktop(), APP_NAME + ".lnk"),
              os.path.join(common_start_menu(), APP_NAME + ".lnk")):
        try:
            if os.path.isfile(p):
                os.remove(p)
                removed.append(p)
        except OSError as exc:
            log("shortcut remove failed %s: %r" % (p, exc))
    log("shortcuts removed: %r" % (removed,))
    return removed


def remove_registry():
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            winreg.DeleteKeyEx(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, view, 0)
            log("registry key deleted (view=%d)" % view)
        except OSError:
            pass


def find_user_scores(root):
    """在安装目录里找"含文件的 Scores 目录"（用户谱库）。"""
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath) == "Scores" and filenames:
            hits.append(dirpath)
    return hits


def preserve_user_scores(root):
    """把用户谱库搬到用户数据目录，返回 (旧路径, 新路径) 列表。"""
    moved = []
    hits = find_user_scores(root)
    if not hits:
        return moved
    dest_base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                             APP_NAME)
    for i, src in enumerate(hits):
        dest = os.path.join(dest_base, "Scores" if i == 0 else "Scores_%d" % i)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.isdir(dest):
                shutil.rmtree(dest, ignore_errors=True)
            shutil.move(src, dest)
            moved.append((src, dest))
            log("user scores preserved: %s -> %s" % (src, dest))
        except OSError as exc:
            log("user scores preserve FAILED %s: %r" % (src, exc))
    return moved


def kill_running_app():
    """卸载前先关掉正在运行的程序本体（否则文件被占用，装不干净）。"""
    try:
        r = subprocess.run(["taskkill", "/F", "/IM", APP_EXE],
                           capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        log("taskkill %s rc=%s out=%s" % (APP_EXE, r.returncode,
                                          (r.stdout or "").strip()[:200]))
    except Exception as exc:  # noqa: BLE001
        log("taskkill failed: %r" % (exc,))
    time.sleep(0.5)


def remove_install_dir(root):
    if not os.path.isdir(root):
        log("install dir not found: " + root)
        return
    preserve_user_scores(root)
    for name in os.listdir(root):
        p = os.path.join(root, name)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
        except OSError as exc:
            log("remove failed %s: %r" % (p, exc))
    # 清空后再删目录本身（uninstall.exe 可能仍在运行，删不掉也无妨，稍后临时副本会再试）
    try:
        os.rmdir(root)
    except OSError as exc:
        log("rmdir root failed: %r" % (exc,))


def spawn_self_from_temp(root):
    """把自身复制到 %TEMP% 再从那里执行清理（这样才能删掉原 uninstall.exe）。"""
    me = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    temp_exe = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"),
                            "dh_uninstall_%d.exe" % os.getpid())
    shutil.copy2(me, temp_exe)
    args = [temp_exe, "/S", _FROM_TEMP_FLAG, "/DIR=" + root]
    subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)
    log("spawned temp uninstaller: " + temp_exe)
    return temp_exe


def cleanup_temp_copies():
    """清理 %TEMP% 里历史遗留的 dh_uninstall_*.exe（不含正在运行的自己）。"""
    t = os.environ.get("TEMP") or r"C:\Windows\Temp"
    me = os.path.abspath(sys.executable).lower() if getattr(sys, "frozen", False) else ""
    try:
        names = os.listdir(t)
    except OSError:
        return
    for name in names:
        if name.startswith("dh_uninstall_") and name.endswith(".exe"):
            p = os.path.join(t, name)
            if os.path.abspath(p).lower() == me:
                continue
            try:
                os.remove(p)
                log("removed stale temp copy: " + p)
            except OSError:
                pass


def schedule_self_delete(path):
    """让 %TEMP% 里的自副本在退出后删除自己。

    用外置 .cmd + 有界重试循环，避免"内联 cmd 字符串引号被二次转义"导致 del 失败；
    另外用 MoveFileEx(DELAY_UNTIL_REBOOT) 做重启兜底。
    """
    temp_dir = os.environ.get("TEMP") or r"C:\Windows\Temp"
    bat = os.path.join(temp_dir, "dh_cleanup_%d.cmd" % os.getpid())
    try:
        with open(bat, "w", encoding="ascii", newline="\r\n") as fh:
            fh.write("@echo off\n")
            fh.write("ping -n 4 127.0.0.1 >nul\n")
            fh.write("for /l %%i in (1,1,20) do (\n")
            fh.write('  if exist "%s" (\n' % path)
            fh.write('    del /f /q "%s" >nul 2>&1\n' % path)
            fh.write("    ping -n 2 127.0.0.1 >nul\n")
            fh.write("  )\n")
            fh.write(")\n")
            fh.write('del /f /q "%~f0" >nul 2>&1\n')
        subprocess.Popen(["cmd.exe", "/c", bat], creationflags=CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("self-delete scheduled via " + bat)
    except OSError as exc:
        log("self-delete scheduling failed: %r" % (exc,))
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        k32.MoveFileExW(path, None, 0x4)   # MOVEFILE_DELAY_UNTIL_REBOOT
        log("reboot-time delete scheduled as fallback")
    except Exception as exc:  # noqa: BLE001
        log("MoveFileEx fallback failed: %r" % (exc,))


def run_gui(root):
    import tkinter as tk
    from tkinter import messagebox
    w = tk.Tk()
    w.title(APP_NAME + " 卸载程序")
    w.geometry("460x180")
    w.resizable(False, False)
    tk.Label(w, text="卸载 " + APP_NAME, font=("Microsoft YaHei UI", 12, "bold")).pack(pady=(16, 6))
    tk.Label(w, text="安装目录：\n" + root, anchor="w", justify="left",
             wraplength=420, fg="#555555").pack(fill="x", padx=16)
    tk.Label(w, text="用户谱库（Scores）如存在会被保留。", anchor="w",
             fg="#555555").pack(fill="x", padx=16, pady=(8, 0))

    def go():
        if not messagebox.askyesno(APP_NAME, "确定要卸载 " + APP_NAME + " 吗？", parent=w):
            return
        w.destroy()

    tk.Button(w, text="卸载", width=12, command=go).pack(pady=10)
    w.mainloop()
    if os.path.isfile(os.path.join(root, APP_EXE)) or os.path.isdir(root):
        spawn_self_from_temp(root)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    silent, target, from_temp = parse_args(argv)
    root = target or install_dir_from_registry()
    if root is None:
        me_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                                 else os.path.abspath(__file__))
        root = me_dir
    log("=== uninstall start (silent=%s, from_temp=%s, dir=%s) ===" % (silent, from_temp, root))

    if not silent:
        return run_gui(root)

    if not from_temp:
        # 第一步：从安装目录里的实例把自己搬到 %TEMP% 再执行真正的清理
        spawn_self_from_temp(root)
        return 0

    # 第二步（%TEMP% 里的临时副本）：真正执行清理
    kill_running_app()
    cleanup_temp_copies()
    remove_shortcuts()
    remove_registry()
    remove_install_dir(root)
    log("=== uninstall done ===")
    schedule_self_delete(os.path.abspath(sys.executable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
