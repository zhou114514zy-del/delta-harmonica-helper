"""Task 19 测试：谱库编辑 / 保存 / Save As / 新建 / 取消 / 安全 / Playing / 格式。

安全设计：
    - 所有文件操作都在 _verify/task19_tmp 下的临时 Scores 里，不污染真实 Scores
    - input 用记录器替身注入，不产生真实键鼠输入，不注入 Enter/音符
    - UI 对话框走可测试接口（new_score_by_name / save_as_by_path）或 monkeypatch，
      不弹真实对话框
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
from score import ScoreParseError, parse_score_notes  # noqa: E402

TMP = os.path.join(PROJECT_DIR, "_verify", "task19_tmp")
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  " + str(detail)) if detail else ""))


class FakeInput:
    def __init__(self):
        self.calls = []
        self._listening = False
        self._held = set()
        self._mouse = set()
        self.enter_cb = {}
        self.escape_cb = None
        self.reset_cb = None

    def press_key(self, k):
        self.calls.append("press_key(%s)" % k)
        self._held.add(k)

    def release_key(self, k):
        self.calls.append("release_key(%s)" % k)
        self._held.discard(k)

    def press_mouse(self, b):
        self.calls.append("press_mouse(%s)" % b)
        self._mouse.add(b)

    def release_mouse(self, b):
        self.calls.append("release_mouse(%s)" % b)
        self._mouse.discard(b)

    def held_keys(self):
        return set(self._held)

    def held_mouse_buttons(self):
        return set(self._mouse)

    def release_all(self):
        self.calls.append("release_all()")
        for k in list(self._held):
            self.release_key(k)
        for b in list(self._mouse):
            self.release_mouse(b)

    def set_enter_callbacks(self, on_down=None, on_up=None):
        self.enter_cb = {"down": on_down, "up": on_up}

    def set_escape_callback(self, cb=None):
        self.escape_cb = cb

    def set_reset_callback(self, cb=None):
        self.reset_cb = cb

    def start_enter_listener(self):
        self._listening = True

    def stop_enter_listener(self):
        self._listening = False

    def is_listening(self):
        return self._listening

    def fire_enter_down(self):
        if self.enter_cb.get("down"):
            self.enter_cb["down"]()

    def held_nothing(self):
        return not self._held and not self._mouse


def new_app(score_text="1 2 3"):
    fake = FakeInput()
    ctrl = app_controller.AppController(input_module=fake, score_text=score_text,
                                        library_project_dir=TMP)
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    app = ui_module.HarmonicaUI(root, controller=ctrl)
    return fake, ctrl, root, app


SROOT = score_library.ensure_scores_dir(TMP)
with open(os.path.join(SROOT, "Existing.txt"), "w", encoding="utf-8") as f:
    f.write("1 2 3")

print("=" * 70)
print("Task 19 - 谱库编辑/保存/新建 测试")
print("=" * 70)

# ---------------- A. 已有谱编辑 ----------------
print("--- A. 已有谱编辑 ---")
fake, ctrl, root, app = new_app(score_text="old")
r = ctrl.library_load_score("Existing.txt")
app._set_score_text(ctrl.score_text)
app._update_current_path()
root.update_idletasks()
check("1 加载已有 .txt", r.startswith("已加载:") and app.score_content() == "1 2 3", r)
check("1b 加载后 modified=False", ctrl.modified is False)
check("1c 加载后不自动播放", ctrl.state != "Playing", ctrl.state)
app.score_text.delete("1.0", "end")
app.score_text.insert("1.0", "1 2 3 4 5")
app._on_score_modified()
root.update_idletasks()
check("2 修改内容", ctrl.score_text_value == "1 2 3 4 5")
check("3 modified 正确", ctrl.modified is True)
check("3b UI 显示 *", app.current_path_label.cget("text").endswith("*"),
      app.current_path_label.cget("text"))
r = ctrl.save_file()
root.update_idletasks()
check("4 Save 成功", r.startswith("已保存"), r)
with open(os.path.join(SROOT, "Existing.txt"), "r", encoding="utf-8") as f:
    reread = f.read()
check("5 重新读取验证", reread == "1 2 3 4 5", reread)
check("6 文件内容与编辑框一致", reread == app.score_content())
check("7 modified 清除", ctrl.modified is False)
app._update_current_path()
check("7b UI 不再显示 *", not app.current_path_label.cget("text").endswith("*"))
check("7c 保存后 current_path 保持",
      ctrl.current_path == os.path.abspath(os.path.join(SROOT, "Existing.txt")))

# ---------------- B. Save As ----------------
print("--- B. Save As ---")
app.score_text.delete("1.0", "end")
app.score_text.insert("1.0", "6 6 6 [\u2191 7]")
app._on_score_modified()
root.update_idletasks()
r = ctrl.library_save_as("Copy.txt")
root.update_idletasks()
check("8 修改已有谱后 Save As", r.startswith("已另存为:"), r)
check("9 Save As 新文件", os.path.isfile(os.path.join(SROOT, "Copy.txt")))
with open(os.path.join(SROOT, "Copy.txt"), "r", encoding="utf-8") as f:
    copy = f.read()
check("10 新文件真实存在且有内容", copy == "6 6 6 [\u2191 7]")
check("11 UTF-8 正确", copy == "6 6 6 [\u2191 7]")
check("12 current_path 正确",
      ctrl.current_path == os.path.abspath(os.path.join(SROOT, "Copy.txt")))
with open(os.path.join(SROOT, "Existing.txt"), "r", encoding="utf-8") as f:
    orig = f.read()
check("13 原文件没有错误覆盖", orig == "1 2 3 4 5", orig)
check("13b Save As 后 modified 清除", ctrl.modified is False)
r = ctrl.library_save_as("Copy")
check("13c 自动补 .txt", r.startswith("已另存为:")
      and os.path.isfile(os.path.join(SROOT, "Copy.txt")), r)
check("13d 已是 .txt 不变成 .txt.txt",
      score_library.normalize_score_name("Song.txt") == "Song.txt")

# ---------------- C. 新建 ----------------
print("--- C. 新建 ---")
r = ctrl.library_new_score("Song")
root.update_idletasks()
check("14 新建 .txt", r.startswith("已新建琴谱:")
      and os.path.isfile(os.path.join(SROOT, "Song.txt")), r)
check("15 current_path 正确",
      ctrl.current_path == os.path.abspath(os.path.join(SROOT, "Song.txt")))
check("15b 新建后进入编辑状态(空内容)", ctrl.score_text_value == "" and ctrl.state == "Ready")
app._set_score_text(ctrl.score_text)
app.score_text.insert("1.0", "5 6 7")
app._on_score_modified()
root.update_idletasks()
check("16 编辑新谱", ctrl.score_text_value == "5 6 7")
r = ctrl.save_file()
root.update_idletasks()
check("17 Save", r.startswith("已保存"), r)
with open(os.path.join(SROOT, "Song.txt"), "r", encoding="utf-8") as f:
    song = f.read()
check("18 文件内容正确", song == "5 6 7", song)
r = ctrl.library_new_score("Song2.txt")
check("18b 输入 .txt 只生成一个", r.startswith("已新建琴谱:")
      and os.path.isfile(os.path.join(SROOT, "Song2.txt")))

# ---------------- D. 取消 ----------------
print("--- D. 取消 ---")
fake2, ctrl2, root2, app2 = new_app(score_text="1 2 3")
ctrl2.current_path = os.path.join(SROOT, "Existing.txt")
before_path = ctrl2.current_path
before_state = ctrl2.state
before_text = ctrl2.score_text_value
before_mod = ctrl2.modified
app2._ask_new_score_name = lambda: ""
app2.new_score_button.invoke()
root2.update_idletasks()
check("19 新建取消", app2.status_text() == "新建琴谱已取消", app2.status_text())
check("19b 取消后 current_path 不变", ctrl2.current_path == before_path)
check("19c 取消后状态不变",
      ctrl2.state == before_state and ctrl2.score_text_value == before_text)
app2._ask_save_as_name = lambda: ""
app2.save_as_button.invoke()
root2.update_idletasks()
check("20 Save As 取消", app2.status_text() == "另存为已取消", app2.status_text())
check("21 状态不被破坏",
      ctrl2.state == before_state and ctrl2.score_text_value == before_text)
check("22 current_path 不被错误修改",
      ctrl2.current_path == before_path and ctrl2.modified == before_mod)
app2.on_close()

# ---------------- E. 安全 ----------------
print("--- E. 安全 ---")
check("23 ../ 拒绝(save)", score_library.save_score("../x", "t", TMP)[0] == "error")
check("23b ../ 拒绝(new)", score_library.new_score("../x", TMP)[0] == "error")
check("24 ..\\ 拒绝(save)", score_library.save_score("..\\x", "t", TMP)[0] == "error")
check("24b ..\\ 拒绝(new)", score_library.new_score("..\\x", TMP)[0] == "error")
check("25 绝对路径拒绝(save)", score_library.save_score("C:\\x.txt", "t", TMP)[0] == "error")
check("25b 绝对路径拒绝(new)", score_library.new_score("C:\\x", TMP)[0] == "error")
check("26 Scores 外路径拒绝", score_library.save_score("a/../../x", "t", TMP)[0] == "error")
outside = os.path.join(TMP, "outside.txt")
with open(outside, "w", encoding="utf-8") as f:
    f.write("secret")
link = os.path.join(SROOT, "link.txt")
try:
    os.symlink(outside, link)
    sym_ok = True
except OSError:
    sym_ok = False
if sym_ok:
    check("27 symlink 逃逸拒绝(load)",
          score_library.load_score("link.txt", TMP)[0] == "error")
    check("27b symlink 逃逸拒绝(save)",
          score_library.save_score("link.txt", "x", TMP)[0] == "error")
    os.remove(link)
else:
    check("27 symlink 逃逸(realpath 语义)",
          score_library._is_within(SROOT,
                                   os.path.join(SROOT, "..", "outside.txt")) is False,
          "环境无法创建真实 symlink，改用 realpath 语义直接验证")
check("28 非法文件名拒绝(new)", score_library.new_score("bad<name", TMP)[0] == "error")
check("28b 非法文件名拒绝(save)", score_library.save_score("bad|name", "t", TMP)[0] == "error")
check("28c 保留名拒绝", score_library.new_score("CON", TMP)[0] == "error")

# ---------------- F. 覆盖保护 ----------------
print("--- F. 覆盖保护 ---")
r = score_library.new_score("Existing", TMP)
check("29 新建时目标已存在拒绝", r[0] == "error", repr(r))
with open(os.path.join(SROOT, "Existing.txt"), "r", encoding="utf-8") as f:
    after = f.read()
check("30 原文件内容保持不变", after == "1 2 3 4 5", after)

# ---------------- G. Playing 安全 ----------------
print("--- G. Playing 安全 ---")
fake3, ctrl3, root3, app3 = new_app(score_text="1 2 3")
app3.start_button.invoke()
root3.update_idletasks()
fake3.fire_enter_down()
check("31a 前置 Playing 且有输入",
      ctrl3.state == "Playing" and not fake3.held_nothing())
r = ctrl3.open_file(os.path.join(SROOT, "Existing.txt"))
app3._set_score_text(ctrl3.score_text)
app3._apply_result(r)
root3.update_idletasks()
check("31 Playing -> Open", r.startswith("已打开") and ctrl3.state != "Playing",
      ctrl3.state)
check("34a 所有输入释放", fake3.held_nothing())
check("34b Hook 已卸载", fake3.is_listening() is False)
check("35a 不自动恢复 Playing", ctrl3.state != "Playing")
app3.start_button.invoke()
root3.update_idletasks()
fake3.fire_enter_down()
state_before_save = ctrl3.state
r = ctrl3.save_file()
root3.update_idletasks()
check("32 Playing -> Save 成功", r.startswith("已保存"), r)
check("32b Save 不打断播放（Task 16 语义）", ctrl3.state == state_before_save)
ctrl3.stop()
root3.update_idletasks()
check("32c Stop 后输入释放", fake3.held_nothing())
app3.start_button.invoke()
root3.update_idletasks()
fake3.fire_enter_down()
r = ctrl3.library_new_score("Gnew")
root3.update_idletasks()
check("33 Playing -> 新建", r.startswith("已新建琴谱:"), r)
check("34c 新建后所有输入释放", fake3.held_nothing())
check("34d 新建后 Hook 卸载", fake3.is_listening() is False)
check("35b 新建后不自动恢复 Playing", ctrl3.state != "Playing")
check("33b 新建文件真实存在", os.path.isfile(os.path.join(SROOT, "Gnew.txt")))
app3.on_close()

# ---------------- H. 格式兼容 ----------------
print("--- H. 格式兼容 ---")
multi = parse_score_notes("1 2 3\n4 5 6\n7")
single = parse_score_notes("1 2 3 4 5 6 7")
check("36 普通音符跨行可解析", len(multi) == 7)
same = [(n.note, n.key, n.modifier) for n in multi] \
    == [(n.note, n.key, n.modifier) for n in single]
check("37 单行/多行解析一致", same)
group = parse_score_notes("[\u2191 3 4 5]")
check("38 同一行调音组正常", [n.modifier for n in group] == ["sharp"] * 3,
      [n.modifier for n in group])
try:
    parse_score_notes("[\u2191 3 4\n5]")
    check("39 调音组跨行被拒绝", False, "未抛错")
except ScoreParseError as e:
    check("39 调音组跨行被拒绝", True, str(e))

# ---------------- 汇总 ----------------
npass = sum(1 for (_n, ok) in results if ok)
nfail = len(results) - npass
print("TOTAL PASS=%d FAIL=%d" % (npass, nfail))
sys.exit(0 if nfail == 0 else 1)
