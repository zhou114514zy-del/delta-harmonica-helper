"""Task 18 谱库基础 — 自动化测试。

覆盖：
  1 Scores 自动创建      2 扫描根目录       3 扫描 .txt
  4 忽略非 .txt          5 扫描子文件夹     6 创建文件夹
  7 非法名称拒绝         8 ../ / ..\\ 穿越拒绝  9 绝对路径拒绝
  10 加载真实 .txt       11 UTF-8 正确      12 加载后不自动播放
  13 当前文件路径正确    14 UI/Controller 集成（谱库树 / 新建文件夹 / 加载）

安全设计：所有文件操作都用 _verify/task18_tmp 下的临时 Scores 目录，不污染真实 Scores；
演奏/输入用记录器替身注入，不碰真实键鼠，不注入 Enter/音符。
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

TMP = os.path.join(PROJECT_DIR, "_verify", "task18_tmp")
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  " + str(detail)) if detail else ""))


# ================= score_library 纯逻辑（临时目录） =================
print("--- score_library 纯逻辑 ---")

root = score_library.ensure_scores_dir(TMP)
check("1 Scores 自动创建", os.path.isdir(root) and os.path.basename(root) == "Scores", root)

# 准备真实文件
os.makedirs(os.path.join(root, "Sub"), exist_ok=True)
with open(os.path.join(root, "Test.txt"), "w", encoding="utf-8") as f:
    f.write("1 2 3")
with open(os.path.join(root, "note.md"), "w", encoding="utf-8") as f:
    f.write("not a score")
with open(os.path.join(root, "Sub", "Song1.txt"), "w", encoding="utf-8") as f:
    f.write("4 5 6")
with open(os.path.join(root, "Sub", "Song2.txt"), "w", encoding="utf-8") as f:
    f.write("\u4e2d\u6587 UTF-8 \u8c31\u5b50")  # 中文内容，只读不打印
with open(os.path.join(root, "Sub", "cover.png"), "wb") as f:
    f.write(b"\x89PNG\r\n")

entries = score_library.list_scores(TMP)
folders = [e for e in entries if e["type"] == "folder"]
files = [e for e in entries if e["type"] == "file"]
check("2 扫描根目录 .txt", any(e["relpath"] == "Test.txt" for e in files),
      sorted(e["relpath"] for e in files))
check("3 扫描 .txt", any(e["relpath"] == "Sub/Song1.txt" for e in files))
check("4 忽略非 .txt", not any(e["relpath"].endswith((".md", ".png")) for e in entries),
      sorted(e["relpath"] for e in entries))
check("5 扫描子文件夹",
      any(e["type"] == "folder" and e["relpath"] == "Sub" for e in folders)
      and any(e["relpath"] == "Sub/Song2.txt" for e in files))

r = score_library.create_folder("NewSong", TMP)
check("6 创建文件夹", r[0] == "ok" and os.path.isdir(os.path.join(root, "NewSong")), repr(r))

check("7a 非法字符拒绝", score_library.create_folder("bad<name", TMP)[0] == "error")
check("7b 保留名拒绝", score_library.create_folder("CON", TMP)[0] == "error")
check("7c 空名拒绝", score_library.create_folder("", TMP)[0] == "error")

check("8a ../ 穿越拒绝(create)", score_library.create_folder("..", TMP)[0] == "error")
check("8b ../ 穿越拒绝(load)", score_library.load_score("../secret.txt", TMP)[0] == "error")
check("8c ..\\ 穿越拒绝(load)", score_library.load_score("..\\secret.txt", TMP)[0] == "error")
check("8d 含 .. 段拒绝", score_library.load_score("Sub/../Test.txt", TMP)[0] == "error")

check("9a 绝对路径拒绝(load)", score_library.load_score("C:\\Windows\\x.txt", TMP)[0] == "error")
check("9b 绝对路径拒绝(create)", score_library.create_folder("C:\\evil", TMP)[0] == "error")
check("9c 非 .txt 拒绝(load)", score_library.load_score("note.md", TMP)[0] == "error")

r = score_library.load_score("Test.txt", TMP)
check("10 加载真实 .txt", r[0] == "ok" and r[1] == "1 2 3", repr(r))
r = score_library.load_score("Sub/Song2.txt", TMP)
check("11 UTF-8 内容正确", r[0] == "ok" and "\u4e2d\u6587" in r[1])

# ================= AppController 集成（注入记录器替身） =================
print("--- AppController 集成 ---")


class FakeInput:
    def __init__(self):
        self.calls = []
        self._listening = False

    def press_key(self, k):
        self.calls.append(("press_key", k))

    def release_key(self, k):
        self.calls.append(("release_key", k))

    def press_mouse(self, b):
        self.calls.append(("press_mouse", b))

    def release_mouse(self, b):
        self.calls.append(("release_mouse", b))

    def move_mouse(self, x, y):
        self.calls.append(("move_mouse", x, y))

    def release_all(self):
        self.calls.append(("release_all",))

    def set_enter_callbacks(self, on_down=None, on_up=None):
        pass

    def set_escape_callback(self, on_escape=None):
        pass

    def set_reset_callback(self, on_reset=None):
        pass

    def start_enter_listener(self):
        self._listening = True

    def stop_enter_listener(self):
        self._listening = False

    def is_listening(self):
        return self._listening


fake = FakeInput()
ctrl = app_controller.AppController(input_module=fake, score_text="1 2 3",
                                    library_project_dir=TMP)
ctrl.start()
check("12a 前置 Playing", ctrl.state == "Playing", ctrl.state)
res = ctrl.library_load_score("Test.txt")
check("12b 加载后不自动播放", ctrl.state != "Playing" and ctrl.state == "Ready", ctrl.state)
check("12c 播放中加载会安全释放", any(c[0] == "release_all" for c in fake.calls))
expected = os.path.abspath(os.path.join(root, "Test.txt"))
check("13 当前文件路径正确", ctrl.current_path == expected, ctrl.current_path)
check("13b 加载返回状态文字", str(res).startswith("已加载:"), res)

# ================= UI 集成（真实 Tk，withdraw） =================
print("--- UI 集成 ---")
root_w = tk.Tk()
root_w.withdraw()
app = ui_module.HarmonicaUI(root_w, controller=ctrl)

app.refresh_library()


def collect(iid, acc):
    for c in app.library_tree.get_children(iid):
        acc.append((c, app.library_tree.item(c, "values")))
        collect(c, acc)
    return acc


allrows = collect("", [])
top = app.library_tree.get_children()
root_text = app.library_tree.item(top[0], "text") if top else ""
check("UI 谱库根节点", root_text == "谱库" and len(top) == 1, root_text)
files_in_ui = [v for (_i, v) in allrows if v and v[0] == "file"]
check("UI 显示根目录 .txt", any(v[1] == "Test.txt" for v in files_in_ui))
check("UI 显示子文件夹 .txt", any(v[1] == "Sub/Song1.txt" for v in files_in_ui))
check("UI 不显示非 .txt", not any(v[1].endswith((".md", ".png")) for v in files_in_ui))

r = app.create_folder_by_name("UI_Folder")
check("UI 新建文件夹", os.path.isdir(os.path.join(root, "UI_Folder")), r)

file_iid = next((i for (i, v) in allrows if v and v[0] == "file" and v[1] == "Test.txt"), None)
app.library_tree.selection_set(file_iid)
app.on_library_load()
check("UI 加载后 Score 文本", app.score_content() == "1 2 3", repr(app.score_content()))
check("UI 加载后不自动播放", ctrl.state != "Playing", ctrl.state)
check("UI 当前路径标签更新", "Test.txt" in app.current_path_label.cget("text"),
      app.current_path_label.cget("text"))

app.on_close()

# ================= 汇总 =================
npass = sum(1 for (_n, ok) in results if ok)
nfail = len(results) - npass
print("TOTAL PASS=%d FAIL=%d" % (npass, nfail))
sys.exit(0 if nfail == 0 else 1)
