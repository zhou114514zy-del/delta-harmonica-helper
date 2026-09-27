"""Task 24：UI 默认尺寸溢出修复验证（不新增功能）。

验证默认窗口尺寸下：
  1. 窗口创建成功且尺寸为 700x620
  2. 所有主要控件 winfo_ismapped() == 1
  3. 谱库管理按钮行完整（各按钮高度正常，未被压缩）
  4. 快捷键提示完整可见
  5. 编辑器与右侧「谱面格式说明」均存在且可见
  6. 无控件被裁出窗口（bottom <= window height）
  7. 窗口可正常关闭
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


print("=" * 70)
print("Task 24 - UI 默认尺寸溢出修复验证")
print("=" * 70)

ctrl = app_controller.AppController(
    input_module=FakeInput(), score_text="1 2 3",
    library_project_dir=os.path.join(PROJECT_DIR, "_verify", "t24_tmp"))
root = tk.Tk()
app = ui_module.HarmonicaUI(root, controller=ctrl)
# 完整 realize（真实布局），再测量
root.after(600, root.quit)
root.mainloop()

W, H = root.winfo_width(), root.winfo_height()
top = root.winfo_rooty()
check("1 窗口创建成功", root.winfo_exists() == 1)
check("1b 默认尺寸为 700x620", W == 700 and H == 620, "%dx%d" % (W, H))

widgets = [
    ("开始按钮", app.start_button), ("暂停按钮", app.pause_button),
    ("继续按钮", app.resume_button), ("停止按钮", app.stop_button),
    ("重置按钮", app.reset_button), ("打开按钮", app.open_button),
    ("保存按钮", app.save_button), ("刷新谱库按钮", app.refresh_library_button),
    ("新建文件夹按钮", app.new_folder_button), ("新建琴谱按钮", app.new_score_button),
    ("另存为按钮", app.save_as_button), ("重命名按钮", app.rename_button),
    ("删除按钮", app.delete_button), ("谱库树", app.library_tree),
    ("编辑器", app.score_text), ("格式说明面板", app.format_help_text),
]

print("--- 2. 主要控件 mapped ---")
for name, w in widgets:
    check("2 " + name + " 可见", w.winfo_ismapped() == 1,
          "mapped=%d" % w.winfo_ismapped())

print("--- 3. 谱库按钮行完整 ---")
lib_btns = [app.refresh_library_button, app.new_folder_button, app.new_score_button,
            app.save_as_button, app.rename_button, app.delete_button]
for b in lib_btns:
    check("3 按钮 '%s' 高度正常" % b.cget("text"), b.winfo_height() >= 20,
          "h=%d" % b.winfo_height())
row_h = app.refresh_library_button.master.winfo_height()
check("3b 按钮行高度未压缩", row_h >= 25, "row_h=%d" % row_h)

print("--- 4. 快捷键提示完整 ---")
for i, l in enumerate(app.shortcut_labels):
    check("4 快捷键提示 %d 可见" % i, l.winfo_ismapped() == 1 and l.winfo_height() >= 15,
          "mapped=%d h=%d" % (l.winfo_ismapped(), l.winfo_height()))

print("--- 5. 编辑器与格式说明 ---")
check("5 编辑器可见且有宽度", app.score_text.winfo_ismapped() == 1
      and app.score_text.winfo_width() > 100, "w=%d" % app.score_text.winfo_width())
check("5b 格式说明可见且有宽度", app.format_help_text.winfo_ismapped() == 1
      and app.format_help_text.winfo_width() > 100, "w=%d" % app.format_help_text.winfo_width())
check("5c 格式说明内容完整", "谱面格式说明" in app.format_help_text.get("1.0", "end"))

print("--- 6. 无裁切 ---")
worst = 0
worst_name = ""
for name, w in widgets + [("快捷键%d" % i, l) for i, l in enumerate(app.shortcut_labels)]:
    if w.winfo_ismapped():
        bot = (w.winfo_rooty() - top) + w.winfo_height()
        if bot > worst:
            worst, worst_name = bot, name
check("6 无控件被裁出窗口", worst <= H, "max_bottom=%d(%s) H=%d" % (worst, worst_name, H))

print("--- 7. 窗口关闭 ---")
app.on_close()
try:
    alive = root.winfo_exists()
except Exception:
    alive = 0
check("7 窗口正常关闭", alive == 0, "winfo_exists=%d" % alive)

npass = sum(1 for (_n, ok) in results if ok)
nfail = len(results) - npass
print("TOTAL PASS=%d FAIL=%d" % (npass, nfail))
sys.exit(0 if nfail == 0 else 1)
