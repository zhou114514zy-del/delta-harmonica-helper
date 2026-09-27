"""Task 20 测试：谱库管理（重命名/删除/新建/重命名文件夹/删除文件夹/嵌套/安全）。

安全设计：
    - 所有文件操作都在 _verify/task20_tmp 下的临时 Scores 里，不污染真实 Scores
    - input 用记录器替身注入，不产生真实键鼠输入，不注入 Enter/音符
    - UI 对话框走可测试接口或 monkeypatch，不弹真实对话框
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

TMP = os.path.join(PROJECT_DIR, "_verify", "task20_tmp")
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


def seed():
    # 嵌套结构：A/1.txt, A/B/2.txt, root.txt
    os.makedirs(os.path.join(SROOT, "A", "B"), exist_ok=True)
    for rel, content in [("root.txt", "1 2 3"), ("A/1.txt", "4 5"), ("A/B/2.txt", "6 7")]:
        with open(os.path.join(SROOT, rel), "w", encoding="utf-8") as f:
            f.write(content)


print("=" * 70)
print("Task 20 - 谱库管理 测试")
print("=" * 70)

# ================ A. Rename file（score_library） ================
print("--- A. Rename file ---")
seed()
r = score_library.rename_score("root.txt", "root2", TMP)
check("A1 Rename 成功", r[0] == "ok" and r[1] == "root2.txt", r)
check("A2 新文件存在", os.path.isfile(os.path.join(SROOT, "root2.txt")))
check("A3 原文件消失", not os.path.exists(os.path.join(SROOT, "root.txt")))
with open(os.path.join(SROOT, "root2.txt"), "r", encoding="utf-8") as f:
    check("A4 内容不变(UTF-8)", f.read() == "1 2 3")
r = score_library.rename_score("root2.txt", "root3", TMP)
check("A5 自动补 .txt", r[0] == "ok" and r[1] == "root3.txt", r)
check("A6 已是 .txt 不重复补", score_library.normalize_score_name("x.txt") == "x.txt")
r = score_library.rename_score("root3.txt", "A/1.txt", TMP)
check("A7 目标已存在拒绝", r[0] == "error", r)

# ================ B. Delete file ================
print("--- B. Delete file ---")
with open(os.path.join(SROOT, "del.txt"), "w", encoding="utf-8") as f:
    f.write("x")
r = score_library.delete_score("del.txt", TMP)
check("B1 删除成功", r[0] == "ok", r)
check("B2 文件已删除", not os.path.exists(os.path.join(SROOT, "del.txt")))
r = score_library.delete_score("del.txt", TMP)
check("B3 不存在时安全处理", r[0] == "error", r)
r = score_library.delete_score("A", TMP)  # 目录不能当 .txt 删
check("B4 目录不作为琴谱删除", r[0] == "error", r)

# ================ C. Create folder（含嵌套） ================
print("--- C. Create folder ---")
r = score_library.create_folder("NewFolder", TMP)
check("C1 创建文件夹", r[0] == "ok" and os.path.isdir(os.path.join(SROOT, "NewFolder")), r)
r = score_library.create_folder("A/C", TMP)
check("C2 嵌套创建", r[0] == "ok" and os.path.isdir(os.path.join(SROOT, "A", "C")), r)
r = score_library.create_folder("NewFolder", TMP)
check("C3 已存在拒绝", r[0] == "error", r)

# ================ D. Rename folder ================
print("--- D. Rename folder ---")
r = score_library.rename_folder("NewFolder", "RenamedFolder", TMP)
check("D1 Rename 文件夹", r[0] == "ok" and r[1] == "RenamedFolder", r)
check("D2 新文件夹存在", os.path.isdir(os.path.join(SROOT, "RenamedFolder")))
r = score_library.rename_folder("", "x", TMP)
check("D3 根目录不可重命名", r[0] == "error", r)
r = score_library.rename_folder("A", "a/b", TMP)
check("D4 新名称不能含分隔符", r[0] == "error", r)

# ================ E/F. Delete folder ================
print("--- E/F. Delete folder ---")
r = score_library.create_folder("EmptyFolder", TMP)
check("E1 创建空文件夹", r[0] == "ok")
r = score_library.delete_folder("EmptyFolder", TMP)
check("E2 删除空文件夹", r[0] == "ok" and not os.path.isdir(os.path.join(SROOT, "EmptyFolder")), r)
r = score_library.delete_folder("A", TMP)   # A 非空（有 1.txt, B, C）
check("F1 非空文件夹拒绝删除", r[0] == "error", r)
check("F2 非空文件夹仍在", os.path.isdir(os.path.join(SROOT, "A")))
check("F3 其中谱仍在", os.path.isfile(os.path.join(SROOT, "A", "1.txt")))
r = score_library.delete_folder("", TMP)
check("F4 根目录不可删除", r[0] == "error", r)

# ================ G. Nested folders ================
print("--- G. Nested ---")
entries = score_library.list_scores(TMP)
folders = set(e["relpath"] for e in entries if e["type"] == "folder")
files = set(e["relpath"] for e in entries if e["type"] == "file")
check("G1 显示 A", "A" in folders)
check("G2 显示 A/B", "A/B" in folders)
check("G3 加载 A/B/2.txt", score_library.load_score("A/B/2.txt", TMP)[0] == "ok")
r = score_library.rename_folder("A/B", "B2", TMP)
check("G4 Rename 嵌套文件夹 A/B", r[0] == "ok" and r[1] == "A/B2", r)
check("G5 内部文件跟随", os.path.isfile(os.path.join(SROOT, "A", "B2", "2.txt")))
r = score_library.rename_score("A/1.txt", "A/1x", TMP)
check("G6 Rename 嵌套琴谱", r[0] == "ok" and r[1] == "A/1x.txt", r)
r = score_library.delete_score("A/B2/2.txt", TMP)
check("G7 删除嵌套琴谱", r[0] == "ok" and not os.path.exists(os.path.join(SROOT, "A", "B2", "2.txt")))
check("G8 创建 A/C 后结构正确", os.path.isdir(os.path.join(SROOT, "A", "C")))

# ================ H/I/J/K/L. 安全 ================
print("--- H/I/J/K/L. 安全 ---")


def reject_all(fn, bad):
    return all(fn(p)[0] == "error" for p in bad)


bad_paths = ["../evil.txt", "..\\evil.txt", "C:\\evil.txt", "D:\\evil.txt",
             "A/../../evil.txt", "a/b/..", "..", "C:/evil.txt"]
check("H1 ../ ..\\ 拒绝(rename_score)",
      reject_all(lambda p: score_library.rename_score(p, "ok", TMP), bad_paths[:2]))
check("H2 绝对路径拒绝(rename_score)",
      reject_all(lambda p: score_library.rename_score(p, "ok", TMP), bad_paths[2:4] + [bad_paths[7]]))
check("H3 逃逸拒绝(rename_score)",
      score_library.rename_score("A/../../evil.txt", "ok", TMP)[0] == "error")
check("H4 逃逸拒绝(delete_score)", score_library.delete_score("../x.txt", TMP)[0] == "error")
check("H5 绝对路径拒绝(delete_score)", score_library.delete_score("C:\\x.txt", TMP)[0] == "error")
check("H6 逃逸拒绝(rename_folder)", score_library.rename_folder("..", "x", TMP)[0] == "error")
check("H7 绝对路径拒绝(rename_folder)", score_library.rename_folder("A", "C:\\x", TMP)[0] == "error")
check("H8 逃逸拒绝(delete_folder)", score_library.delete_folder("../x", TMP)[0] == "error")
check("H9 逃逸拒绝(create_folder)", score_library.create_folder("../x", TMP)[0] == "error")
check("H10 绝对路径拒绝(create_folder)", score_library.create_folder("C:\\x", TMP)[0] == "error")

# Scores 外部真实路径
outside_path = os.path.join(TMP, "outside.txt")
with open(outside_path, "w", encoding="utf-8") as f:
    f.write("s")
rel_outside = os.path.relpath(outside_path, SROOT)  # 形如 ..\outside.txt
check("J1 Scores 外真实路径拒绝(delete)",
      score_library.delete_score(rel_outside.replace("\\", "/"), TMP)[0] == "error")

# symlink 逃逸
link = os.path.join(SROOT, "link.txt")
try:
    os.symlink(outside_path, link)
    sym_ok = True
except OSError:
    sym_ok = False
if sym_ok:
    check("K1 symlink 逃逸拒绝(delete)", score_library.delete_score("link.txt", TMP)[0] == "error")
    check("K2 symlink 逃逸拒绝(rename)", score_library.rename_score("link.txt", "ok", TMP)[0] == "error")
    os.remove(link)
else:
    check("K1 symlink 逃逸(realpath 语义)",
          score_library._is_within(SROOT, os.path.join(SROOT, "..", "outside.txt")) is False,
          "环境无法创建真实 symlink，改用 realpath 语义验证")

# Windows 保留设备名
for dev in ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]:
    check("L1 保留设备名拒绝(rename) " + dev,
          score_library.rename_score("root3.txt", dev, TMP)[0] == "error")
check("L2 保留设备名拒绝(new) CON.txt", score_library.new_score("CON", TMP)[0] == "error")
check("L3 保留设备名拒绝(create_folder) CON",
      score_library.create_folder("CON", TMP)[0] == "error")

# ================ M. 覆盖保护 ================
print("--- M. 覆盖保护 ---")
with open(os.path.join(SROOT, "exist1.txt"), "w", encoding="utf-8") as f:
    f.write("keep1")
with open(os.path.join(SROOT, "exist2.txt"), "w", encoding="utf-8") as f:
    f.write("keep2")
r = score_library.rename_score("exist1.txt", "exist2", TMP)
check("M1 Rename 到已存在目标拒绝", r[0] == "error", r)
with open(os.path.join(SROOT, "exist2.txt"), "r", encoding="utf-8") as f:
    check("M2 原目标内容不变", f.read() == "keep2")
with open(os.path.join(SROOT, "exist1.txt"), "r", encoding="utf-8") as f:
    check("M3 源文件不变", f.read() == "keep1")

# ================ N/O/P. 当前编辑状态安全 ================
print("--- N/O/P. 当前编辑状态 ---")
# 清理重来一个干净结构
shutil.rmtree(SROOT, ignore_errors=True)
os.makedirs(SROOT)
with open(os.path.join(SROOT, "root.txt"), "w", encoding="utf-8") as f:
    f.write("1 2 3")
os.makedirs(os.path.join(SROOT, "A"), exist_ok=True)
with open(os.path.join(SROOT, "A", "1.txt"), "w", encoding="utf-8") as f:
    f.write("4 5")

fake, ctrl, root, app = new_app(score_text="x")
ctrl.library_load_score("root.txt")
check("N1 前置 current_path=root.txt",
      ctrl.current_path == os.path.abspath(os.path.join(SROOT, "root.txt")))
r = ctrl.library_rename_score("root.txt", "root_renamed")
check("N2 Rename 当前谱 current_path 更新",
      r.startswith("已重命名:") and ctrl.current_path == os.path.abspath(os.path.join(SROOT, "root_renamed.txt")), ctrl.current_path)
# modified 保持
ctrl.score_modified("1 2 3 4")
check("N3 修改后 modified=True", ctrl.modified is True)
r = ctrl.library_rename_score("root_renamed.txt", "root_renamed2")
check("N4 Rename 当前谱(modified) 允许且 modified 保留",
      r.startswith("已重命名:") and ctrl.modified is True, ctrl.current_path)
# 文件夹重命名更新 current_path
ctrl.library_load_score("A/1.txt")
r = ctrl.library_rename_folder("A", "A2")
check("N5 Rename 文件夹后 current_path 更新",
      r.startswith("已重命名文件夹:") and ctrl.current_path == os.path.abspath(os.path.join(SROOT, "A2", "1.txt")), ctrl.current_path)
# 删除当前谱（未修改）-> current_path 失效
ctrl.library_load_score("A2/1.txt")
ctrl.modified = False
r = ctrl.library_delete_score("A2/1.txt")
check("O1 删除当前谱 current_path 失效",
      r.startswith("已删除:") and ctrl.current_path is None and ctrl.score_text_value == "", ctrl.current_path)
check("O2 删除后状态 Ready", ctrl.state == "Ready", ctrl.state)
# 删除当前谱（modified）-> 拒绝
ctrl.library_load_score("root_renamed2.txt")
ctrl.score_modified("changed unsaved")
r = ctrl.library_delete_score("root_renamed2.txt")
check("P1 删除当前谱(未保存) 拒绝", r.startswith("错误") and "未保存" in r, r)
check("P2 拒绝后文件仍在", os.path.isfile(os.path.join(SROOT, "root_renamed2.txt")))
check("P3 拒绝后 current_path 不变",
      ctrl.current_path == os.path.abspath(os.path.join(SROOT, "root_renamed2.txt")))
app.on_close()

# ================ Q. Playing 安全 ================
print("--- Q. Playing 安全 ---")
fake2, ctrl2, root2, app2 = new_app(score_text="1 2 3")
ctrl2.library_load_score("root_renamed2.txt")
app2._set_score_text(ctrl2.score_text)
app2.start_button.invoke()
root2.update_idletasks()
fake2.fire_enter_down()
check("Q1 前置 Playing 且有输入", ctrl2.state == "Playing" and not fake2.held_nothing())
r = ctrl2.library_rename_score("root_renamed2.txt", "playing_renamed")
check("Q2 Playing 中 Rename 成功", r.startswith("已重命名:"), r)
check("Q3 Rename 保持既有语义(仍在播放、输入保持)",
      ctrl2.state == "Playing" and not fake2.held_nothing())
r = ctrl2.library_delete_score("playing_renamed.txt")
check("Q4 Playing 中 Delete 当前谱安全结束", r.startswith("已删除:"), r)
check("Q5 Delete 后所有键鼠释放", fake2.held_nothing())
check("Q6 Delete 后 Hook 卸载", fake2.is_listening() is False)
check("Q7 Delete 后不自动恢复 Playing", ctrl2.state != "Playing", ctrl2.state)
app2.on_close()

# ================ S. tree 刷新 + UI 集成 ================
print("--- S. tree 刷新 + UI ---")
shutil.rmtree(SROOT, ignore_errors=True)
os.makedirs(SROOT)
with open(os.path.join(SROOT, "ui.txt"), "w", encoding="utf-8") as f:
    f.write("7 7")
os.makedirs(os.path.join(SROOT, "D"), exist_ok=True)
fake3, ctrl3, root3, app3 = new_app(score_text="1")
app3.refresh_library()


def all_rows(tree):
    acc = []

    def walk(iid):
        for c in tree.get_children(iid):
            acc.append((c, tree.item(c, "values")))
            walk(c)
    walk("")
    return acc


rows = all_rows(app3.library_tree)
files = [v[1] for (_i, v) in rows if v and v[0] == "file"]
check("S1 初始 tree 含 ui.txt", "ui.txt" in files)
# 选中 ui.txt 并重命名
target_iid = next(i for (i, v) in rows if v and v[0] == "file" and v[1] == "ui.txt")
app3.library_tree.selection_set(target_iid)
r = app3.rename_selected_by_name("ui_renamed")
root3.update_idletasks()
rows = all_rows(app3.library_tree)
files = [v[1] for (_i, v) in rows if v and v[0] == "file"]
check("S2 Rename 后 tree 刷新", "ui_renamed.txt" in files and "ui.txt" not in files, files)
check("S3 Rename 后真实文件变化", os.path.isfile(os.path.join(SROOT, "ui_renamed.txt")))
# 选中 D 文件夹删除（空文件夹）
target_iid = next(i for (i, v) in rows if v and v[0] == "folder" and v[1] == "D")
app3.library_tree.selection_set(target_iid)
r = app3.delete_selected_now()
root3.update_idletasks()
rows = all_rows(app3.library_tree)
folders = [v[1] for (_i, v) in rows if v and v[0] == "folder"]
check("S4 删除文件夹后 tree 刷新", "D" not in folders, folders)
check("S5 删除文件夹真实生效", not os.path.isdir(os.path.join(SROOT, "D")))
# 删除确认（on_delete 走 confirm）
app3.library_tree.selection_set(next(i for (i, v) in rows if v and v[0] == "file" and v[1] == "ui_renamed.txt"))
app3._confirm_delete = lambda name: False
app3.on_delete()
root3.update_idletasks()
check("S6 删除取消", app3.status_text() == "删除已取消", app3.status_text())
check("S7 取消后文件仍在", os.path.isfile(os.path.join(SROOT, "ui_renamed.txt")))
app3.on_close()

# ================ 汇总 ================
npass = sum(1 for (_n, ok) in results if ok)
nfail = len(results) - npass
print("TOTAL PASS=%d FAIL=%d" % (npass, nfail))
sys.exit(0 if nfail == 0 else 1)
