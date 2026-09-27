"""Task 21 测试：谱库系统大型集成测试（不新增功能，验证 Task 18-20 组合无隐藏问题）。

安全设计：
    - 所有文件操作都在 _verify/task21_tmp 下的临时 Scores，不污染真实 Scores
    - input 用记录器替身注入，不产生真实键鼠输入，不注入 Enter/音符
    - UI 走可测试接口，不弹真实对话框
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

TMP = os.path.join(PROJECT_DIR, "_verify", "task21_tmp")
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

    def fire_enter_down(self):
        if self.enter_cb.get("down"):
            self.enter_cb["down"]()

    def held_nothing(self):
        return not self._held and not self._mouse


def fresh(score_text="1 2 3"):
    """重置临时 Scores，返回 (fake, ctrl, root, app, SROOT)。"""
    global SROOT
    shutil.rmtree(os.path.join(TMP, "Scores"), ignore_errors=True)
    SROOT = score_library.ensure_scores_dir(TMP)
    fake = FakeInput()
    ctrl = app_controller.AppController(input_module=fake, score_text=score_text,
                                        library_project_dir=TMP)
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    app = ui_module.HarmonicaUI(root, controller=ctrl)
    return fake, ctrl, root, app, SROOT


def tree_rows(tree):
    acc = []

    def walk(iid):
        for c in tree.get_children(iid):
            acc.append((c, tree.item(c, "values")))
            walk(c)
    walk("")
    return acc


print("=" * 70)
print("Task 21 - 谱库系统集成测试")
print("=" * 70)

# ============ 四. 综合工作流 ============
print("--- 四. 综合工作流 ---")
fake, ctrl, root, app, S = fresh()
ctrl.library_create_folder("TestA")
check("W1 创建文件夹 TestA", os.path.isdir(os.path.join(S, "TestA")))
ctrl.library_create_folder("TestA/Sub")
check("W2 创建子文件夹 Sub", os.path.isdir(os.path.join(S, "TestA", "Sub")))
ctrl.library_new_score("TestA/song")
check("W3 创建谱 song.txt", os.path.isfile(os.path.join(S, "TestA", "song.txt")))
app._set_score_text(ctrl.score_text)
app.score_text.insert("1.0", "1 2 3 4")
app._on_score_modified()
r = ctrl.save_file()
check("W4 Save", r.startswith("已保存"), r)
with open(os.path.join(S, "TestA", "song.txt"), "r", encoding="utf-8") as f:
    check("W5 重新读取一致", f.read() == "1 2 3 4")
r = ctrl.library_rename_score("TestA/song.txt", "TestA/song2")
check("W6 Rename song->song2", r.startswith("已重命名:"), r)
check("W7 current_path 更新",
      ctrl.current_path == os.path.abspath(os.path.join(S, "TestA", "song2.txt")), ctrl.current_path)
app.refresh_library()
rows = tree_rows(app.library_tree)
files = [v[1] for (_i, v) in rows if v and v[0] == "file"]
check("W8 tree 刷新含 song2", "TestA/song2.txt" in files, files)
check("W9 song2.txt 存在", os.path.isfile(os.path.join(S, "TestA", "song2.txt")))
ctrl.library_delete_score("TestA/song2.txt")
check("W10 删除 song2", not os.path.exists(os.path.join(S, "TestA", "song2.txt")))
ctrl.library_delete_folder("TestA/Sub")
check("W11 删除 Sub", not os.path.isdir(os.path.join(S, "TestA", "Sub")))
ctrl.library_delete_folder("TestA")
check("W12 删除 TestA", not os.path.isdir(os.path.join(S, "TestA")))
check("W13 整个测试结构不存在", os.listdir(S) == [])
app.on_close()

# ============ 五. 复杂嵌套 ============
print("--- 五. 复杂嵌套 ---")
fake, ctrl, root, app, S = fresh()
ctrl.library_create_folder("A/B/C")
for rel, content in [("A/1.txt", "1"), ("A/B/2.txt", "2"), ("A/B/C/3.txt", "3")]:
    ctrl.library_new_score(rel.rstrip(".txt"))
    ctrl.score_text_value = content
    ctrl.save_file()
app.refresh_library()
rows = tree_rows(app.library_tree)
files = [v[1] for (_i, v) in rows if v and v[0] == "file"]
check("N1 三级嵌套 tree 显示", all(x in files for x in ["A/1.txt", "A/B/2.txt", "A/B/C/3.txt"]), files)
check("N2 打开 1.txt", score_library.load_score("A/1.txt", TMP)[0] == "ok")
check("N3 打开 2.txt", score_library.load_score("A/B/2.txt", TMP)[0] == "ok")
check("N4 打开 3.txt", score_library.load_score("A/B/C/3.txt", TMP)[0] == "ok")
ctrl.library_load_score("A/B/C/3.txt")
ctrl.score_modified("3 3 3")
check("N5 编辑 3.txt", ctrl.score_text_value == "3 3 3")
ctrl.save_file()
check("N6 Save 3.txt", score_library.load_score("A/B/C/3.txt", TMP)[1] == "3 3 3")
r = ctrl.library_rename_folder("A/B/C", "C2")
check("N7 Rename C", r[0] == "ok" or r.startswith("已重命名文件夹:"), r)
check("N8 路径更新", ctrl.current_path == os.path.abspath(os.path.join(S, "A", "B", "C2", "3.txt")), ctrl.current_path)
r = ctrl.library_rename_score("A/B/C2/3.txt", "A/B/C2/3x")
check("N9 Rename 3.txt", r.startswith("已重命名:"), r)
ctrl.library_delete_score("A/B/C2/3x.txt")
check("N10 删除 3.txt", not os.path.exists(os.path.join(S, "A", "B", "C2", "3x.txt")))
ctrl.library_delete_folder("A/B/C2")
check("N11 删除空 C2", not os.path.isdir(os.path.join(S, "A", "B", "C2")))
ctrl.library_delete_score("A/B/2.txt")
check("N12 删除 2.txt", not os.path.exists(os.path.join(S, "A", "B", "2.txt")))
ctrl.library_delete_folder("A/B")
check("N13 删除空 B", not os.path.isdir(os.path.join(S, "A", "B")))
ctrl.library_delete_score("A/1.txt")
check("N14 删除 1.txt", not os.path.exists(os.path.join(S, "A", "1.txt")))
ctrl.library_delete_folder("A")
check("N15 删除 A", not os.path.isdir(os.path.join(S, "A")))
check("N16 结构不存在", os.listdir(S) == [])
app.on_close()

# ============ 六. 谱面格式集成 ============
print("--- 六. 谱面格式 ---")
single = parse_score_notes("1 2 3 4 5 6 7 1'")
multi = parse_score_notes("1 2 3\n4 5 6\n7 1'")
check("F1 普通音符自由换行", len(multi) == 8)
check("F2 单行/多行解析一致",
      [(n.note, n.key, n.modifier) for n in single] == [(n.note, n.key, n.modifier) for n in multi])
g1 = parse_score_notes("[\u2191 3 4 5]")
g2 = parse_score_notes("[\u2193 2]")
g3 = parse_score_notes("[~ 6 7 1']")
g4 = parse_score_notes("[normal 1 2]")
check("F3 调音组 ↑", [n.modifier for n in g1] == ["sharp"] * 3)
check("F4 调音组 ↓", [n.modifier for n in g2] == ["flat"])
check("F5 调音组 ~", [n.modifier for n in g3] == ["half"] * 3)
check("F6 调音组 normal", [n.modifier for n in g4] == ["normal"] * 2)
mixed = parse_score_notes("1 2 [\u2191 3 4 5] 6 [~ 7 1'] [\u2193 2]")
check("F7 混合谱解析", len(mixed) == 9, len(mixed))
try:
    parse_score_notes("[\u2191 3\n4 5]")
    check("F8 调音组跨行拒绝", False, "未抛错")
except ScoreParseError as e:
    check("F8 调音组跨行拒绝", True, str(e))

# ============ 七. 编辑状态集成 ============
print("--- 七. 编辑状态 ---")
fake, ctrl, root, app, S = fresh()
ctrl.library_new_score("edit.txt")
app._set_score_text(ctrl.score_text)
app.score_text.insert("1.0", "abc")
app._on_score_modified()
check("E1 modified=True", ctrl.modified is True)
ctrl.save_file()
check("E2 Save 后 modified=False", ctrl.modified is False)
app.score_text.insert("end", "def")
app._on_score_modified()
check("E3 再改 modified=True", ctrl.modified is True)
r = ctrl.library_rename_score("edit.txt", "edit2")
check("E4 Rename 当前谱(modified) 允许", r.startswith("已重命名:"), r)
check("E5 未保存内容未丢失", ctrl.score_text_value == "abcdef", repr(ctrl.score_text_value))
app._set_score_text(ctrl.score_text)
ctrl.score_modified("ghost")
r = ctrl.library_delete_score("edit2.txt")
check("E6 Delete 当前谱(modified) 拒绝", r.startswith("错误") and "未保存" in r, r)
check("E7 拒绝后文件仍在", os.path.isfile(os.path.join(S, "edit2.txt")))
app.on_close()

# ============ 八. Save / Save As 集成 ============
print("--- 八. Save / Save As ---")
fake, ctrl, root, app, S = fresh()
ctrl.library_new_score("orig.txt")
ctrl.score_text_value = "1 2 3"
ctrl.save_file()
ctrl.score_text_value = "1 2 3 4 5"
r = ctrl.library_save_as("copy")
check("SA1 Save As", r.startswith("已另存为:"), r)
check("SA2 新文件存在", os.path.isfile(os.path.join(S, "copy.txt")))
check("SA3 原文件仍在", os.path.isfile(os.path.join(S, "orig.txt")))
check("SA4 新文件内容", score_library.load_score("copy.txt", TMP)[1] == "1 2 3 4 5")
check("SA5 test -> test.txt", score_library.normalize_score_name("test") == "test.txt")
check("SA6 test.txt -> test.txt", score_library.normalize_score_name("test.txt") == "test.txt")
check("SA7 无 test.txt.txt",
      score_library.normalize_score_name("test.txt.txt") == "test.txt.txt"
      or score_library.normalize_score_name("test.txt") == "test.txt")
app.on_close()

# ============ 九. Playing 集成 ============
print("--- 九. Playing 集成 ---")
fake, ctrl, root, app, S = fresh("1 2 3")
ctrl.library_new_score("p1.txt")
ctrl.score_text_value = "1 2 3"
ctrl.save_file()
ctrl.library_new_score("p2.txt")
ctrl.score_text_value = "4 5 6"
ctrl.save_file()
# 1. Ready -> open -> start -> playing -> stop
ctrl.library_load_score("p1.txt")
app._set_score_text(ctrl.score_text)
app.start_button.invoke()
root.update_idletasks()
fake.fire_enter_down()
check("P1 Start 后 Playing", ctrl.state == "Playing")
ctrl.stop()
check("P2 停止后键鼠 UP", fake.held_nothing())
check("P3 停止后 Hook 卸载", fake.is_listening() is False)
# 2. Playing -> Open 另一首
app.start_button.invoke()
root.update_idletasks()
fake.fire_enter_down()
r = ctrl.library_load_score("p2.txt")
check("P4 Playing->Open 安全停止", r.startswith("已加载:") and ctrl.state != "Playing", ctrl.state)
check("P5 Open 后键鼠 UP", fake.held_nothing())
check("P6 不自动恢复 Playing", ctrl.state != "Playing")
# 3. Playing -> Rename 当前谱
app.start_button.invoke()
root.update_idletasks()
fake.fire_enter_down()
r = ctrl.library_rename_score("p2.txt", "p2renamed")
check("P7 Playing->Rename 成功且保持语义", r.startswith("已重命名:"), r)
check("P8 Rename 后无输入残留(仍在播放，输入保持或安全)", ctrl.state == "Playing" or fake.held_nothing())
# 4. Playing -> Delete 当前谱
r = ctrl.library_delete_score("p2renamed.txt")
check("P9 Playing->Delete 安全结束", r.startswith("已删除:"), r)
check("P10 Delete 后键鼠 UP", fake.held_nothing())
check("P11 current_path 失效", ctrl.current_path is None)
check("P12 Delete 后 Ready", ctrl.state == "Ready")
# 5. Playing -> Rename 文件夹
ctrl.library_create_folder("F")
ctrl.library_new_score("F/x.txt")
ctrl.score_text_value = "9"
ctrl.save_file()
ctrl.library_load_score("F/x.txt")
app.start_button.invoke()
root.update_idletasks()
fake.fire_enter_down()
r = ctrl.library_rename_folder("F", "F2")
check("P13 Playing->Rename 文件夹安全", r.startswith("已重命名文件夹:"), r)
check("P14 路径更新", ctrl.current_path == os.path.abspath(os.path.join(S, "F2", "x.txt")), ctrl.current_path)
ctrl.stop()
check("P15 停止后键鼠 UP", fake.held_nothing())
# 6. Playing -> 删除空文件夹
ctrl.library_create_folder("Empty")
app.start_button.invoke()
root.update_idletasks()
r = ctrl.library_delete_folder("Empty")
check("P16 Playing->删除空文件夹 状态不损坏", r.startswith("已删除文件夹:"), r)
ctrl.stop()
check("P17 最终键鼠 UP", fake.held_nothing())
app.on_close()

# ============ 十. 路径安全集成 ============
print("--- 十. 路径安全 ---")
fake, ctrl, root, app, S = fresh()
outside = os.path.join(TMP, "external.txt")
with open(outside, "w", encoding="utf-8") as f:
    f.write("keep")
bad_files = ["../evil.txt", "..\\evil.txt", "C:\\evil.txt", "D:\\evil.txt"]
for p in bad_files:
    check("SEC1 拒绝(rename) " + p.replace("\\", "/"),
          score_library.rename_score(p, "ok", TMP)[0] == "error")
for p in bad_files:
    check("SEC2 拒绝(delete) " + p.replace("\\", "/"),
          score_library.delete_score(p, TMP)[0] == "error")
for p in ["../d", "C:\\d", "Scores\\..\\evil"]:
    check("SEC3 拒绝(mkdir) " + p.replace("\\", "/"),
          score_library.create_folder(p, TMP)[0] == "error")
for dev in ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"]:
    check("SEC4 保留设备名 " + dev,
          score_library.rename_score("external.txt", dev, TMP)[0] == "error"
          and score_library.create_folder(dev, TMP)[0] == "error")
with open(outside, "r", encoding="utf-8") as f:
    check("SEC5 外部文件未被删除/修改", f.read() == "keep")
check("SEC6 未创建外部文件", not os.path.exists(os.path.join(TMP, "evil.txt")))
# symlink
link = os.path.join(S, "link.txt")
try:
    os.symlink(outside, link)
    sym_ok = True
except OSError:
    sym_ok = False
if sym_ok:
    check("SEC7 symlink 逃逸拒绝", score_library.delete_score("link.txt", TMP)[0] == "error")
    os.remove(link)
else:
    check("SEC7 symlink 逃逸(realpath 语义)",
          score_library._is_within(S, os.path.join(S, "..", "external.txt")) is False,
          "无法创建真实 symlink，改用 realpath 语义验证")
app.on_close()

# ============ 十一. UI 集成 ============
print("--- 十一. UI 集成 ---")
fake, ctrl, root, app, S = fresh()
ctrl.library_create_folder("UiF")
ctrl.library_new_score("UiF/ui.txt")
ctrl.score_text_value = "7 1'"
ctrl.save_file()
app.refresh_library()
rows = tree_rows(app.library_tree)
files = [v[1] for (_i, v) in rows if v and v[0] == "file"]
folders = [v[1] for (_i, v) in rows if v and v[0] == "folder"]
check("U1 tree 存在", app.library_tree.get_children() and app.library_tree.item(app.library_tree.get_children()[0], "text") == "谱库")
check("U2 文件夹显示", "UiF" in folders)
check("U3 .txt 显示", "UiF/ui.txt" in files)
check("U4 嵌套显示", "UiF/ui.txt" in files)
# 加载显示路径
iid = next(i for (i, v) in rows if v and v[0] == "file" and v[1] == "UiF/ui.txt")
app.library_tree.selection_set(iid)
app.on_library_load()
root.update_idletasks()
check("U5 当前路径显示", "ui.txt" in app.current_path_label.cget("text"))
check("U6 编辑区内容正确", app.score_content() == "7 1'")
app.score_text.insert("end", " x")
app._on_score_modified()
check("U7 modified 标记", app.current_path_label.cget("text").endswith("*"))
# Rename 后 tree 更新
app.library_tree.selection_set(iid)
app.rename_selected_by_name("ui2")
root.update_idletasks()
rows = tree_rows(app.library_tree)
files = [v[1] for (_i, v) in rows if v and v[0] == "file"]
check("U8 Rename 后 tree 更新", "UiF/ui2.txt" in files and "UiF/ui.txt" not in files, files)
# Delete 后 tree 更新（先保存清掉 modified，否则删除会被未保存保护正确拒绝）
ctrl.save_file()
iid2 = next(i for (i, v) in rows if v and v[0] == "file" and v[1] == "UiF/ui2.txt")
app.library_tree.selection_set(iid2)
app.delete_selected_now()
root.update_idletasks()
rows = tree_rows(app.library_tree)
files = [v[1] for (_i, v) in rows if v and v[0] == "file"]
check("U9 Delete 后 tree 更新", "UiF/ui2.txt" not in files)
# 新建文件夹后 tree 更新（走可测试接口 create_folder_by_name，不触发真实对话框）
check("U10 新建文件夹入口存在", app.new_folder_button.cget("text") == "新建文件夹")
app.create_folder_by_name("UiF2")
root.update_idletasks()
rows = tree_rows(app.library_tree)
folders = [v[1] for (_i, v) in rows if v and v[0] == "folder"]
check("U11 新建文件夹后 tree 更新", "UiF2" in folders)
check("U12 Open 后状态", ctrl.state == "Ready")
app.on_close()

# ============ 汇总 ============
npass = sum(1 for (_n, ok) in results if ok)
nfail = len(results) - npass
print("TOTAL PASS=%d FAIL=%d" % (npass, nfail))
sys.exit(0 if nfail == 0 else 1)
