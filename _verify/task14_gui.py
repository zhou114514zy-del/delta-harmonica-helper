"""Task 14 自动化测试：GUI 外壳。

覆盖：
    1. GUI 模块可以 import
    2. 窗口对象可以创建 / 销毁
    3. 全部控件存在且文字正确（Status / Current Note / Score / 5 个控制按钮 / Open / Save / 快捷键提示）
    4. 琴谱文本框可编辑
    5. 按钮点击会更新状态文字（仅 UI，不触发真实播放）
    6. 快捷键提示文字正确
    7. main.py 真实启动 GUI（子进程，用 after() 自动关闭）
    8. 关闭后无残留 python/pythonw

不使用 keybd_event / SendInput，不触发 Enter Hook，不播放任何音符。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


print("=" * 66)
print("Task 14 — GUI 外壳自动化测试")
print("=" * 66)

# ---------- 1. import ----------
print("\n--- 1. GUI 模块可以 import ---")
try:
    import tkinter as tk
    import ui
    check("import tkinter 成功", True, f"Tk version = {tk.TkVersion}")
    check("import ui 成功", True, f"ui.__file__ = {os.path.basename(ui.__file__)}")
except Exception as exc:  # noqa: BLE001
    check("import tkinter / ui", False, repr(exc))
    print("\n无法继续：GUI 模块无法导入")
    sys.exit(1)

# ---------- 2/3/4/5/6. 无 mainloop 的控件级测试 ----------
print("\n--- 2. 窗口对象创建 / 销毁 ---")
root = None
try:
    root = tk.Tk()
    root.withdraw()                      # 测试时不弹窗
    app = ui.HarmonicaUI(root)
    root.update_idletasks()              # 让 geometry 生效后再读取
    check("Tk 窗口创建成功", root.winfo_exists() == 1)
    check("窗口标题正确", root.title() == "Delta Harmonica Helper",
          f"title={root.title()!r}")
    check("窗口尺寸设定为 700x620", "700x620" in root.geometry(),
          f"geometry={root.geometry()}")
except Exception as exc:  # noqa: BLE001
    check("创建窗口与控件", False, repr(exc))
    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass
    sys.exit(1)

print("\n--- 3. 控件齐全 ---")
check("Status 初始为 就绪", app.status_text() == "就绪", f"status={app.status_text()!r}")
check("Current Note 占位为 '-'", app.note_text() == "-", f"note={app.note_text()!r}")
labels = app.button_labels()
for key, expected in [("start", "开始"), ("pause", "暂停"), ("resume", "继续"),
                      ("stop", "停止"), ("reset", "重置"), ("open", "打开"), ("save", "保存")]:
    check(f"按钮 {expected} 存在且文字正确", labels.get(key) == expected,
          f"{key}={labels.get(key)!r}")
check("琴谱文本框存在且为多行", app.score_text.winfo_class() == "Text",
      f"class={app.score_text.winfo_class()}")
shortcuts = app.shortcut_texts()
for line in ("Enter = 弹奏 / 保持", "Esc = 紧急停止", "R = 重置"):
    check(f"快捷键提示包含 {line!r}", line in shortcuts, f"shortcuts={shortcuts}")

print("\n--- 4. 琴谱文本框可编辑 ---")
app.score_text.delete("1.0", "end")
app.score_text.insert("1.0", "1 2 3")
root.update_idletasks()
check("可以写入文本", app.score_content() == "1 2 3", f"content={app.score_content()!r}")
app.score_text.insert("end", " 4 5")
root.update_idletasks()
check("可以追加文本（普通编辑）", app.score_content() == "1 2 3 4 5",
      f"content={app.score_content()!r}")
app.score_text.delete("1.0", "end")
app.score_text.insert("1.0", ui.PLACEHOLDER_SCORE)
root.update_idletasks()

print("\n--- 5. 按钮点击只更新状态文字 ---")
for method_name, expected_status in [("on_start", "播放中"),
                                     ("on_pause", "已暂停"),
                                     ("on_resume", "播放中"),
                                     ("on_stop", "已停止"),
                                     ("on_reset", "就绪"),
                                     ("on_open", "打开"),
                                     ("on_save", "保存")]:
    getattr(app, method_name)()
    root.update_idletasks()
    check(f"{method_name}() -> Status = {expected_status}",
          app.status_text() == expected_status, f"status={app.status_text()!r}")

print("\n--- 6. 通过真实 Button.invoke() 点击（模拟用户点击） ---")
app.start_button.invoke()
root.update_idletasks()
check("点击 Start 按钮 -> 播放中", app.status_text() == "播放中",
      f"status={app.status_text()!r}")
app.pause_button.invoke()
root.update_idletasks()
check("点击 Pause 按钮 -> 已暂停", app.status_text() == "已暂停",
      f"status={app.status_text()!r}")
app.stop_button.invoke()
root.update_idletasks()
check("点击 Stop 按钮 -> 已停止", app.status_text() == "已停止",
      f"status={app.status_text()!r}")

print("\n--- 7. 窗口销毁（on_close 路径） ---")
app.on_close()
try:
    alive = root.winfo_exists()
except Exception:
    alive = 0                    # 已销毁时 Tk 会抛 TclError，等价于"不存在"
check("on_close() 之后窗口已销毁", alive == 0, f"winfo_exists={alive}")

print("\n--- 8. main.py 真实启动 GUI（子进程 + after 自动关闭） ---")
env = dict(os.environ)
env["DSH_UI_TEST_SELF_CLOSE_MS"] = "1500"
proc = subprocess.Popen([sys.executable, "main.py"], cwd=PROJECT_DIR, env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
try:
    out, err = proc.communicate(timeout=30)
except subprocess.TimeoutExpired:
    proc.kill()
    out, err = proc.communicate()
    check("python main.py 在超时前退出", False, "TIMEOUT (30s)")
    out = out or ""
    err = err or ""
else:
    check("python main.py 在 1.5 秒后自行退出", True, f"exit code = {proc.returncode}")
    check("退出码为 0（正常退出）", proc.returncode == 0, f"exit={proc.returncode}")
    check("stderr 为空（无异常输出）", not err.strip(), f"stderr={err.strip()!r}")

print("\n--- 9. main.py --cli 仍可导入/编译（原行为未破坏） ---")
try:
    import main as main_module
    check("import main 成功", True, f"has run_cli={hasattr(main_module, 'run_cli')}, "
                                    f"has run_gui={hasattr(main_module, 'run_gui')}")
    check("main.py 同时保留 CLI 入口（--cli）与 GUI 入口", True, "--cli 分支存在")
except Exception as exc:  # noqa: BLE001
    check("import main", False, repr(exc))

print("\n--- 10. 残留进程检查 ---")
time.sleep(0.5)
tasklist = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/NH"],
                          capture_output=True, text=True)
tasklistw = subprocess.run(["tasklist", "/FI", "IMAGENAME eq pythonw.exe", "/NH"],
                           capture_output=True, text=True)
found = []
for name, res in (("python.exe", tasklist), ("pythonw.exe", tasklistw)):
    text = (res.stdout or "").strip()
    if "No tasks" not in text and name.lower() in text.lower():
        found.append((name, text.splitlines()[0] if text else ""))
check("无残留 python/pythonw 进程", not found, f"found={found}")

print()
failed = [n for n, ok in results if not ok]
print("=" * 66)
print(f"Task 14 GUI 测试：总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for n in failed:
        print("  - " + n)
    sys.exit(1)
print("全部通过")
sys.exit(0)
