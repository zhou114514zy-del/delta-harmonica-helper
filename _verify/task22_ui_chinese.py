"""Task 22 测试：最终 UI 中文化。

检查：
  1. UI 可以启动
  2. UI 标题存在
  3. 主要按钮存在且为中文
  4. 谱库区域存在
  5. 状态显示存在
  6. 中文文本存在（任务书清单）
  7. 原有主要英文 UI 文本已经消失

不触发真实键鼠/输入注入；不弹真实对话框（走可测试接口）。
"""

import os
import sys
import tkinter as tk

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import app_controller  # noqa: E402
import ui as ui_module  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  " + str(detail)) if detail else ""))


class FakeInput:
    def __init__(self):
        self._listening = False
        self._held = set()
        self._mouse = set()
        self.enter_cb = {}

    def press_key(self, k):
        self._held.add(k)

    def release_key(self, k):
        self._held.discard(k)

    def press_mouse(self, b):
        self._mouse.add(b)

    def release_mouse(self, b):
        self._mouse.discard(b)

    def release_all(self):
        for k in list(self._held):
            self.release_key(k)
        for b in list(self._mouse):
            self.release_mouse(b)

    def set_enter_callbacks(self, on_down=None, on_up=None):
        self.enter_cb = {"down": on_down, "up": on_up}

    def set_escape_callback(self, cb=None):
        pass

    def set_reset_callback(self, cb=None):
        pass

    def start_enter_listener(self):
        self._listening = True

    def stop_enter_listener(self):
        self._listening = False

    def is_listening(self):
        return self._listening


def all_texts(widget, acc=None):
    """递归收集界面上所有可见文字（Label/Button 的 text）。"""
    if acc is None:
        acc = []
    try:
        text = widget.cget("text")
        if text:
            acc.append(str(text))
    except Exception:  # noqa: BLE001
        pass
    for child in widget.winfo_children():
        all_texts(child, acc)
    return acc


print("=" * 70)
print("Task 22 - 最终 UI 中文化 测试")
print("=" * 70)

# ---------- 1/2. UI 启动 + 标题 ----------
print("--- 1/2. UI 启动与标题 ---")
root = tk.Tk()
root.withdraw()
ctrl = app_controller.AppController(input_module=FakeInput(), score_text="1 2 3",
                                    library_project_dir=os.path.join(PROJECT_DIR, "_verify", "task22_tmp"))
app = ui_module.HarmonicaUI(root, controller=ctrl)
root.update_idletasks()
check("1 UI 可以启动", root.winfo_exists() == 1)
check("2 UI 标题存在", bool(root.title()), "title=" + root.title())
check("2b 标题为产品名 Delta Harmonica Helper", root.title() == "Delta Harmonica Helper",
      root.title())

texts = all_texts(root)

# ---------- 3. 主要按钮（中文） ----------
print("--- 3. 主要按钮 ---")
btn = {
    "开始": app.start_button.cget("text"),
    "暂停": app.pause_button.cget("text"),
    "继续": app.resume_button.cget("text"),
    "停止": app.stop_button.cget("text"),
    "重置": app.reset_button.cget("text"),
    "打开": app.open_button.cget("text"),
    "保存": app.save_button.cget("text"),
    "另存为": app.save_as_button.cget("text"),
    "新建琴谱": app.new_score_button.cget("text"),
    "新建文件夹": app.new_folder_button.cget("text"),
    "重命名": app.rename_button.cget("text"),
    "删除": app.delete_button.cget("text"),
}
for want, got in btn.items():
    check("3 按钮中文: " + want, got == want, "got=" + repr(got))
check("3b 刷新按钮中文含'刷新'", "刷新" in app.refresh_library_button.cget("text"),
      app.refresh_library_button.cget("text"))

# ---------- 4. 谱库 ----------
print("--- 4. 谱库 ---")
check("4 谱库标签存在", "谱库:" in texts, [t for t in texts if "谱库" in t])
root_iid = app.library_tree.get_children()[0] if app.library_tree.get_children() else ""
check("4b 谱库树根节点为'谱库'",
      app.library_tree.item(root_iid, "text") == "谱库",
      app.library_tree.item(root_iid, "text") if root_iid else "(none)")

# ---------- 5. 状态显示 ----------
print("--- 5. 状态显示 ---")
check("5 状态标签存在", "状态:" in texts, [t for t in texts if t.startswith("状态")])
check("5b 当前音符标签存在", "当前音符:" in texts, [t for t in texts if t.startswith("当前音符")])
check("5c 琴谱标签存在", "琴谱:" in texts, [t for t in texts if t.startswith("琴谱")])
cpl = app.current_path_label.cget("text")
check("5d 当前琴谱/当前路径标签存在", "当前琴谱" in cpl and "当前路径" in cpl, cpl)

# ---------- 6. 中文文本（任务书清单） ----------
print("--- 6. 中文清单 ---")
for word in ["开始", "暂停", "继续", "停止", "重置", "打开", "保存", "另存为",
             "新建琴谱", "新建文件夹", "重命名", "删除", "刷新", "谱库",
             "当前琴谱", "当前路径"]:
    hay = texts + [cpl]
    hit = [t for t in hay if word in t]
    check("6 中文存在: " + word, bool(hit), hit[0] if hit else "not found")

# ---------- 状态显示中文（占位模式 + 真实 controller） ----------
print("--- 状态文字中文化 ---")
root_p = tk.Tk()
root_p.withdraw()
app_p = ui_module.HarmonicaUI(root_p, controller=None)
root_p.update_idletasks()
check("占位初始状态= 就绪", app_p.status_text() == "就绪", app_p.status_text())
for method, want in [("on_start", "播放中"), ("on_pause", "已暂停"),
                     ("on_resume", "播放中"), ("on_stop", "已停止"),
                     ("on_reset", "就绪"), ("on_open", "打开"), ("on_save", "保存")]:
    getattr(app_p, method)()
    root_p.update_idletasks()
    check("占位 " + method + " -> " + want, app_p.status_text() == want, app_p.status_text())
app_p.on_close()

check("真实 controller 初始状态= 就绪", app.status_text() == "就绪", app.status_text())
app.on_start()
root.update_idletasks()
check("Start -> 播放中", app.status_text() == "播放中", app.status_text())
app.on_pause()
root.update_idletasks()
check("Pause -> 已暂停", app.status_text() == "已暂停", app.status_text())
app.on_resume()
root.update_idletasks()
check("Resume -> 播放中", app.status_text() == "播放中", app.status_text())
app.on_stop()
root.update_idletasks()
check("Stop -> 已停止", app.status_text() == "已停止", app.status_text())
app.on_reset()
root.update_idletasks()
check("Reset -> 就绪", app.status_text() == "就绪", app.status_text())

# 错误显示中文化
tmp = os.path.join(PROJECT_DIR, "_verify", "task22_tmp")
os.makedirs(tmp, exist_ok=True)
res = ctrl.open_file(os.path.join(tmp, "does_not_exist.txt"))
app.refresh_from_controller()
check("错误提示中文化（无法打开）", res.startswith("错误") and "无法打开" in res, res)
check("错误状态显示= 错误", app.status_text() == "错误", app.status_text())
ctrl.last_error = None
ctrl.message = None

# ---------- 7. 英文 UI 文本消失 ----------
print("--- 7. 英文 UI 文本消失 ---")
app.refresh_library()
root.update_idletasks()
texts2 = all_texts(root) + [app.status_text(), app.note_text(), app.current_path_label.cget("text")]
english = ["Start", "Pause", "Resume", "Stop", "Reset", "Open", "Save", "Refresh",
           "Rename", "Delete", "Scores", "Status:", "Current Note:", "Score:",
           "New Score", "New Folder", "Save As", "Play / Hold", "Emergency Stop",
           "Ready", "Playing", "Paused", "Stopped", "Idle"]
for word in english:
    hit = [t for t in texts2 if word in t]
    check("7 英文已消失: " + word, not hit, "found in " + repr(hit[:2]))

# 快捷键仍为 Enter/Esc/R（行为不变，只中文化说明）
print("--- 快捷键说明 ---")
sc = app.shortcut_texts()
check("快捷键提示含 Enter", any("Enter" in s for s in sc), sc)
check("快捷键提示含 Esc", any("Esc" in s for s in sc), sc)
check("快捷键提示含 R", any(s.startswith("R ") or "= 重置" in s for s in sc), sc)

app.on_close()

npass = sum(1 for (_n, ok) in results if ok)
nfail = len(results) - npass
print("TOTAL PASS=%d FAIL=%d" % (npass, nfail))
sys.exit(0 if nfail == 0 else 1)
