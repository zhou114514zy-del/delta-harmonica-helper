"""Task 16 测试：Open / Save 真实文件功能。

设计（不弹真实对话框、不触发真实输入）：
    - 文件读写用 controller 的 path 参数自动化（任务书允许）
    - UI 的 filedialog 调用路径用 monkeypatch 验证（能自动覆盖"用户选中文件"和"取消"两种情况），
      因此不会卡在真实的系统文件选择对话框上
    - input.py 用记录器替身注入，score.py / harmonica_app.py 用真实核心
"""
import io
import os
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_controller  # noqa: E402
import ui as ui_module  # noqa: E402

results = []
# 注意：DSH 沙箱只允许在工作区内写入，所以临时目录建在 _verify 下（测试结束后可删）
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "task16_tmp")
os.makedirs(TMP, exist_ok=True)


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


class FakeInput:
    """input.py 替身：记录调用，不装 Hook、不产生任何真实键鼠输入。"""

    def __init__(self):
        self.calls = []
        self.enter_cb = {}
        self.escape_cb = None
        self.reset_cb = None
        self._listening = False
        self._held = set()
        self._mouse = set()

    def press_key(self, k):
        self.calls.append(f"press_key({k})"); self._held.add(k)

    def release_key(self, k):
        self.calls.append(f"release_key({k})"); self._held.discard(k)

    def press_mouse(self, b):
        self.calls.append(f"press_mouse({b})"); self._mouse.add(b)

    def release_mouse(self, b):
        self.calls.append(f"release_mouse({b})"); self._mouse.discard(b)

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
        self.calls.append("set_enter_callbacks()")

    def set_escape_callback(self, cb=None):
        self.escape_cb = cb; self.calls.append("set_escape_callback()")

    def set_reset_callback(self, cb=None):
        self.reset_cb = cb; self.calls.append("set_reset_callback()")

    def start_enter_listener(self):
        self._listening = True; self.calls.append("start_enter_listener()")

    def stop_enter_listener(self):
        self._listening = False; self.calls.append("stop_enter_listener()")

    def is_listening(self):
        return self._listening

    def fire_enter_down(self):
        if self.enter_cb.get("down"):
            self.enter_cb["down"]()

    def fire_enter_up(self):
        if self.enter_cb.get("up"):
            self.enter_cb["up"]()

    def held_nothing(self):
        return not self._held and not self._mouse


def new_app(score_text="1 2 3"):
    fake = FakeInput()
    ctrl = app_controller.AppController(input_module=fake, score_text=score_text)
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    app = ui_module.HarmonicaUI(root, controller=ctrl)
    return fake, ctrl, root, app


print("=" * 70)
print("Task 16 — Open / Save 测试")
print("=" * 70)

# ---------------- A. Open ----------------
print("\n--- A. Open ---")
path_a = os.path.join(TMP, "test_score.txt")
with open(path_a, "w", encoding="utf-8") as fh:
    fh.write("1 2 [\u2191 3 4 5] 6")
fake, ctrl, root, app = new_app(score_text="old content")
result = ctrl.open_file(path_a)
app._set_score_text(ctrl.score_text)
app._apply_result(result)
root.update_idletasks()
check("A1 Open 成功（返回 Opened）", result.startswith("已打开"), f"result={result!r}")
check("A2 Score Text 内容正确", app.score_content() == "1 2 [\u2191 3 4 5] 6",
      f"content={app.score_content()!r}")
check("A3 controller 收到 score 修改", ctrl.score_text_value == "1 2 [\u2191 3 4 5] 6",
      f"text={ctrl.score_text_value!r}")
check("A4 记录了当前文件路径", ctrl.current_path == path_a, f"path={ctrl.current_path!r}")
check("A5 Status 显示 Opened", app.status_text().startswith("已打开"),
      f"status={app.status_text()!r}")
check("A6 无错误", app.error_var.get() == "", f"error={app.error_var.get()!r}")
check("A7 未自动开始播放", ctrl.state != "Playing", f"state={ctrl.state!r}")
check("A8 Hook 未被启动", fake.is_listening() is False)

# Start 用新琴谱解析（解析由 score.py 负责）
ctrl.start()
check("A9 Start 使用新载入的琴谱（1 2 [^ 3 4 5] 6 => 6 个音符）",
      ctrl.player.note_count() == 6, f"note_count={ctrl.player.note_count()}")
ctrl.stop()
app.refresh_from_controller()
root.update_idletasks()

# ---------------- B. Save ----------------
print("\n--- B. Save ---")
path_b = os.path.join(TMP, "save_test.txt")
fake, ctrl, root, app = new_app(score_text="1 2 3")
result = ctrl.save_file(path_b)
app._apply_result(result)
root.update_idletasks()
with open(path_b, "r", encoding="utf-8") as fh:
    saved = fh.read()
check("B1 Save 成功（返回 Saved）", result.startswith("已保存"), f"result={result!r}")
check("B2 文件内容完全正确", saved == "1 2 3", f"saved={saved!r}")
with open(path_b, "rb") as fh:
    raw = fh.read()
check("B3 编码为 UTF-8（无 BOM，内容可解码）",
      raw.decode("utf-8") == "1 2 3" and not raw.startswith(b"\xef\xbb\xbf"),
      f"raw={raw!r}")
check("B4 Status 显示 Saved", app.status_text().startswith("已保存"),
      f"status={app.status_text()!r}")
app.on_close()

# ---------------- C. Open -> 修改 -> Save ----------------
print("\n--- C. Open -> 修改 -> Save -> 重新读取 ---")
path_c = os.path.join(TMP, "roundtrip.txt")
with open(path_c, "w", encoding="utf-8") as fh:
    fh.write("1 2 3")
fake, ctrl, root, app = new_app(score_text="")
ctrl.open_file(path_c)
app._set_score_text(ctrl.score_text)
root.update_idletasks()
check("C1 Open 后内容正确", app.score_content() == "1 2 3", f"content={app.score_content()!r}")
# 用户编辑（走 UI 的 Modified 事件 -> controller）
app.score_text.delete("1.0", "end")
app.score_text.insert("1.0", "1 2 [\u2191 3] 4")
app._on_score_modified()
check("C2 UI 编辑后通知了 controller", ctrl.score_text_value == "1 2 [\u2191 3] 4",
      f"text={ctrl.score_text_value!r}")
result = ctrl.save_file()          # 有已知路径 -> 直接写回，不弹对话框
app._apply_result(result)
root.update_idletasks()
with open(path_c, "r", encoding="utf-8") as fh:
    reread = fh.read()
check("C3 Save 直接写回原文件（无对话框）", result.startswith("已保存"), f"result={result!r}")
check("C4 重新读取内容与修改后一致", reread == "1 2 [\u2191 3] 4", f"reread={reread!r}")
app.on_close()

# ---------------- D. Save As（无已知路径 -> 弹对话框） ----------------
print("\n--- D. Save As（无已知路径） ---")
path_d = os.path.join(TMP, "saveas.txt")
fake, ctrl, root, app = new_app(score_text="1 2 3 4")
check("D1 尚无已知路径", ctrl.current_path is None, f"path={ctrl.current_path!r}")
r = ctrl.save_file()
check("D2 无路径时返回 NEED_DIALOG（交给 UI 弹对话框）",
      r == app_controller.NEED_DIALOG, f"result={r!r}")
# 用 monkeypatch 模拟用户在"另存为"对话框中选中文件（自动化，不弹真实窗口）
calls = []
orig_ask_save = app._ask_save_path
app._ask_save_path = lambda: (calls.append("asksaveasfilename"), path_d)[1]
app.save_button.invoke()
root.update_idletasks()
app._ask_save_path = orig_ask_save
check("D3 UI 调用了 asksaveasfilename()", calls == ["asksaveasfilename"], f"calls={calls}")
check("D4 Save As 写出的文件存在", os.path.exists(path_d), f"path={path_d}")
with open(path_d, "r", encoding="utf-8") as fh:
    content_d = fh.read()
check("D5 Save As 内容正确", content_d == "1 2 3 4", f"content={content_d!r}")
check("D6 之后记录了当前路径", ctrl.current_path == path_d, f"path={ctrl.current_path!r}")
app.on_close()

# ---------------- E. Cancel ----------------
print("\n--- E. Cancel（Open / Save 取消） ---")
fake, ctrl, root, app = new_app(score_text="keep me")
ctrl.start()                        # 进入 Playing，用于验证取消不改变播放状态
root.update_idletasks()
before_state = ctrl.state
before_score = app.score_content()
app._ask_open_path = lambda: ""     # 模拟用户取消 Open
app.open_button.invoke()
root.update_idletasks()
check("E1 Open 取消不崩溃", True, "no exception")
check("E2 Open 取消后 Score 未被清空", app.score_content() == before_score,
      f"content={app.score_content()!r}")
check("E3 Open 取消后播放状态未变", ctrl.state == before_state,
      f"state={ctrl.state!r} (before={before_state!r})")
check("E4 Open 取消后 Status = Open cancelled",
      app.status_text() == ui_module.STATUS_OPEN_CANCELLED, f"status={app.status_text()!r}")
app._ask_save_path = lambda: ""     # 模拟用户取消 Save（当前有路径时不会走到对话框）
ctrl.current_path = None            # 清掉路径以强制走对话框分支
app.save_button.invoke()
root.update_idletasks()
check("E5 Save 取消不崩溃", True, "no exception")
check("E6 Save 取消后 Score 未变", app.score_content() == before_score,
      f"content={app.score_content()!r}")
check("E7 Save 取消后 Status = Save cancelled",
      app.status_text() == ui_module.STATUS_SAVE_CANCELLED, f"status={app.status_text()!r}")
ctrl.stop()
app.on_close()

# ---------------- F. Empty file ----------------
print("\n--- F. 空文件 ---")
path_f = os.path.join(TMP, "empty.txt")
open(path_f, "w", encoding="utf-8").close()
fake, ctrl, root, app = new_app(score_text="something")
result = ctrl.open_file(path_f)
app._set_score_text(ctrl.score_text)
app._apply_result(result)
root.update_idletasks()
check("F1 空文件可以成功打开", result.startswith("已打开"), f"result={result!r}")
check("F2 Score 可以为空", app.score_content() == "", f"content={app.score_content()!r}")
check("F3 空文件不崩溃", True, "no exception")
app.on_close()

# ---------------- G. 非法琴谱 ----------------
print("\n--- G. 非法琴谱 ---")
path_g = os.path.join(TMP, "invalid.txt")
with open(path_g, "w", encoding="utf-8") as fh:
    fh.write("1 2 [\u2191")
fake, ctrl, root, app = new_app(score_text="")
result = ctrl.open_file(path_g)     # Open 只读文本，应当成功
app._set_score_text(ctrl.score_text)
app._apply_result(result)
root.update_idletasks()
check("G1 Open 非法琴谱成功（Open 只负责读文本）", result.startswith("已打开"),
      f"result={result!r}")
check("G2 Score 内容为非法琴谱原文", app.score_content() == "1 2 [\u2191",
      f"content={app.score_content()!r}")
app.start_button.invoke()           # Start 时才解析 -> 应报错但不崩溃
app.refresh_from_controller()
root.update_idletasks()
check("G3 Start 非法琴谱：状态显示 错误", app.status_text() == "错误",
      f"status={app.status_text()!r}")
check("G4 Start 非法琴谱：错误信息非空（来自 score.py 的 ScoreParseError）",
      app.error_var.get() != "" and "line" in app.error_var.get().lower(),
      f"error={app.error_var.get()!r}")
check("G5 未崩溃、无 traceback", True, "no exception")
app.on_close()

# ---------------- H. Playing 状态保护 ----------------
print("\n--- H. Playing 状态下 Open 新文件 ---")
path_h = os.path.join(TMP, "newscore.txt")
with open(path_h, "w", encoding="utf-8") as fh:
    fh.write("1 2 3 4 5")
fake, ctrl, root, app = new_app(score_text="1 2 3")
app.start_button.invoke()
root.update_idletasks()
check("H1 已进入 Playing", ctrl.state == "Playing", f"state={ctrl.state!r}")
fake.fire_enter_down()              # 制造"有输入被按下"的状态
check("H2 前置：有输入被按下", not fake.held_nothing(), f"held={fake.held_keys()}")
result = ctrl.open_file(path_h)
app._set_score_text(ctrl.score_text)
app._apply_result(result)
app.refresh_from_controller()
root.update_idletasks()
check("H3 Open 新文件成功", result.startswith("已打开"), f"result={result!r}")
check("H4 当前输入已安全释放（无残留键鼠）", fake.held_nothing(),
      f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
check("H5 release_all() 由核心执行", "release_all()" in fake.calls,
      f"tail={fake.calls[-3:]}")
check("H6 Hook 已卸载（不再全局吞 Enter）", fake.is_listening() is False)
check("H7 不会自动继续播放", ctrl.state != "Playing", f"state={ctrl.state!r}")
check("H8 新 Score 已载入", app.score_content() == "1 2 3 4 5", f"content={app.score_content()!r}")
check("H9 状态回到 Ready（界面仍显示最近一次操作反馈 Opened）",
      ctrl.state == "Ready" and app.status_text().startswith("已打开"),
      f"controller.state={ctrl.state!r} ui_status={app.status_text()!r}")
# 新琴谱能被正确解析
ctrl.start()
check("H10 Start 用新琴谱解析出 5 个音符", ctrl.player.note_count() == 5,
      f"note_count={ctrl.player.note_count()}")
ctrl.stop()
app.on_close()

# ---------------- 额外：播放中 Save 不改位置 ----------------
print("\n--- 额外：Playing 时 Save 不改变播放器位置 ---")
path_i = os.path.join(TMP, "save_while_playing.txt")
fake, ctrl, root, app = new_app(score_text="1 2 3")
app.start_button.invoke()
root.update_idletasks()
idx_before = ctrl.player.index
state_before = ctrl.state
result = ctrl.save_file(path_i)
root.update_idletasks()
check("I1 Playing 时 Save 成功", result.startswith("已保存"), f"result={result!r}")
check("I2 Save 不改变播放器 index", ctrl.player.index == idx_before,
      f"before={idx_before} after={ctrl.player.index}")
check("I3 Save 不改变播放状态", ctrl.state == state_before,
      f"before={state_before!r} after={ctrl.state!r}")
app.on_close()

print()
failed = [n for n, ok in results if not ok]
print("=" * 70)
print(f"Task 16 测试：总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for n in failed:
        print("  - " + n)
    sys.exit(1)
print("全部通过")
sys.exit(0)
