"""Task 23 测试：谱面格式说明（只增说明 UI，不改 parser）。

检查：
  1. UI 可以启动
  2. "谱面格式说明" 存在
  3-8. 普通音符 / 自由换行 / 调音组 / 调音组不能跨行 / 混合示例 / 注释 说明存在
  9-19. 键位与调音映射说明存在
  20+. 增加说明后 Open/Save/Save As/New Score/Rename/Delete/Playing/Stop/Reset 不受影响

不触发真实键鼠；文件操作走临时目录；不弹真实对话框（走可测试接口）。
"""

import os
import shutil
import sys
import tkinter as tk

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import app_controller  # noqa: E402
import score_library  # noqa: E402
import ui as ui_module  # noqa: E402

TMP = os.path.join(PROJECT_DIR, "_verify", "task23_tmp")
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP)

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

    def held_nothing(self):
        return not self._held and not self._mouse


print("=" * 70)
print("Task 23 - 谱面格式说明 测试")
print("=" * 70)

# ---------- 1. UI 启动 ----------
fake = FakeInput()
ctrl = app_controller.AppController(input_module=fake, score_text="1 2 3",
                                    library_project_dir=TMP)
root = tk.Tk()
root.withdraw()
app = ui_module.HarmonicaUI(root, controller=ctrl)
root.update_idletasks()
check("1 UI 可以启动", root.winfo_exists() == 1)
check("1d 窗口尺寸为当前默认 700x620", "700x620" in root.geometry(), root.geometry())

help_text = app.format_help_text.get("1.0", "end")
check("1b 说明控件存在", isinstance(app.format_help_text, tk.Text))
check("1c 说明为只读", str(app.format_help_text.cget("state")) == "disabled",
      app.format_help_text.cget("state"))

# ---------- 2. 标题 ----------
print("--- 2. 标题 ---")
check("2 标题 谱面格式说明 存在", "谱面格式说明" in help_text)

# ---------- 3-8. 内容 ----------
print("--- 3-8. 说明内容 ---")
check("3 普通音符说明", "普通音符" in help_text)
check("4 自由换行说明", "自由换行" in help_text and "不影响播放顺序" in help_text)
check("5 调音组说明", "调音组" in help_text and "[↑ 3 4 5]" in help_text
      and "[↓ 2]" in help_text and "[~ 6 7 1']" in help_text and "[normal 1 2]" in help_text)
check("6 调音组不能跨行说明", "不能跨行" in help_text)
check("7 混合示例", "1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]" in help_text)
check("8 注释说明", "#" in help_text and "注释" in help_text)

# ---------- 9-19. 映射 ----------
print("--- 9-19. 键位与调音映射 ---")
for want in ["1 → Z", "2 → X", "3 → C", "4 → V", "5 → B", "6 → N", "7 → M", "1' → ,",
             "↑ → 右键", "↓ → 左键", "~ → 中键"]:
    check("映射说明: " + want, want in help_text)

# ---------- 内容正确性（不得声称错误规则） ----------
print("--- 内容正确性 ---")
check("未声称 调音组可以跨行", "调音组可以跨行" not in help_text)
check("未声称 普通音符不能换行", "普通音符不能换行" not in help_text)
check("调音组跨行示例标注为错误", "错误：[↑ 3" in help_text)

# ---------- 20+. 功能不受影响 ----------
print("--- 20+. 功能不受影响 ---")
SROOT = score_library.ensure_scores_dir(TMP)

# New Score
r = ctrl.library_new_score("h1")
check("New Score 不受影响", r.startswith("已新建琴谱:"), r)
ctrl.score_text_value = "1 2 3"
ctrl.save_file()

# Save
r = ctrl.save_file()
check("Save 不受影响", r.startswith("已保存"), r)

# Save As
r = ctrl.library_save_as("h2")
check("Save As 不受影响", r.startswith("已另存为:") and os.path.isfile(os.path.join(SROOT, "h2.txt")), r)

# Open
r = ctrl.open_file(os.path.join(SROOT, "h2.txt"))
check("Open 不受影响", r.startswith("已打开") and ctrl.score_text_value == "1 2 3", r)

# Rename
r = ctrl.library_rename_score("h2.txt", "h3")
check("Rename 不受影响", r.startswith("已重命名:") and os.path.isfile(os.path.join(SROOT, "h3.txt")), r)

# Delete
r = ctrl.library_delete_score("h3.txt")
check("Delete 不受影响", r.startswith("已删除:") and not os.path.exists(os.path.join(SROOT, "h3.txt")), r)

# Playing / Stop / Reset
app.start_button.invoke()
root.update_idletasks()
check("Playing 不受影响", ctrl.state == "Playing", ctrl.state)
check("Playing 界面状态= 播放中", app.status_text() == "播放中", app.status_text())
app.stop_button.invoke()
root.update_idletasks()
check("Stop 不受影响", ctrl.state == "Stopped" and fake.held_nothing(), ctrl.state)
app.reset_button.invoke()
root.update_idletasks()
check("Reset 不受影响", ctrl.state == "Ready" and ctrl.player.index == 0, ctrl.state)

check("编辑框仍可编辑（说明控件不影响它）", app.score_text.cget("state") != "disabled",
      app.score_text.cget("state"))

app.on_close()

npass = sum(1 for (_n, ok) in results if ok)
nfail = len(results) - npass
print("TOTAL PASS=%d FAIL=%d" % (npass, nfail))
sys.exit(0 if nfail == 0 else 1)
