"""Task 15 测试：UI <-> 播放器核心连接。

做法（既不触发真实输入，又真实验证连接层）：
    - input.py 用"记录器"替身注入（不装 Hook、不模拟任何真实键鼠）
    - score.py 与 harmonica_app.py 使用**真实核心**
    这样 AppController 的连接逻辑得到真实验证，同时 zero 真实输入。

覆盖任务书 A–G：
    A. UI 初始化        B. Start        C. Pause        D. Resume
    E. Stop             F. Reset        G. Score 进入核心
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_controller  # noqa: E402
import ui as ui_module  # noqa: E402

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


class FakeInput:
    """input.py 的替身：记录调用，不装 Hook、不产生任何真实输入。"""

    def __init__(self):
        self.calls = []
        self.enter_cb = {}
        self.escape_cb = None
        self.reset_cb = None
        self._listening = False
        self._held = set()
        self._mouse = set()

    # --- 模拟输入 API（FixedScorePlayer 使用）---
    def press_key(self, k):
        self.calls.append(f"press_key({k})")
        self._held.add(k)

    def release_key(self, k):
        self.calls.append(f"release_key({k})")
        self._held.discard(k)

    def press_mouse(self, b):
        self.calls.append(f"press_mouse({b})")
        self._mouse.add(b)

    def release_mouse(self, b):
        self.calls.append(f"release_mouse({b})")
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

    # --- Hook 相关 API（AppController 使用）---
    def set_enter_callbacks(self, on_down=None, on_up=None):
        self.enter_cb = {"down": on_down, "up": on_up}
        self.calls.append("set_enter_callbacks()")

    def set_escape_callback(self, cb=None):
        self.escape_cb = cb
        self.calls.append("set_escape_callback()")

    def set_reset_callback(self, cb=None):
        self.reset_cb = cb
        self.calls.append("set_reset_callback()")

    def start_enter_listener(self):
        self._listening = True
        self.calls.append("start_enter_listener()")

    def stop_enter_listener(self):
        self._listening = False
        self.calls.append("stop_enter_listener()")

    def is_listening(self):
        return self._listening

    # --- 测试辅助 ---
    def fire_enter_down(self):
        if self.enter_cb.get("down"):
            self.enter_cb["down"]()

    def fire_enter_up(self):
        if self.enter_cb.get("up"):
            self.enter_cb["up"]()

    def fire_escape(self):
        if self.escape_cb:
            self.escape_cb()

    def fire_reset(self):
        if self.reset_cb:
            self.reset_cb()

    def held_nothing(self):
        return not self._held and not self._mouse


SCORE = "1 2 [\u2191 3 4 5] 6 [~ 7 1'] [\u2193 2]"

print("=" * 68)
print("Task 15 — UI <-> 播放器核心连接 测试")
print("=" * 68)

fake_io = FakeInput()
controller = app_controller.AppController(input_module=fake_io, score_text=SCORE)
root = tk.Tk()
root.withdraw()
root.update_idletasks()
app = ui_module.HarmonicaUI(root, controller=controller)

# ---------- A. UI 初始化 ----------
print("\n--- A. UI 初始化 ---")
check("GUI 创建成功", root.winfo_exists() == 1)
check("标题正确", root.title() == "Delta Harmonica Helper", f"title={root.title()!r}")
check("初始 Status 来自核心 = 就绪", app.status_text() == "就绪",
      f"status={app.status_text()!r}")
check("初始 Current Note = '1'（score 已交给核心解析）", app.note_text() == "1",
      f"note={app.note_text()!r}")
check("Score 文本可读取且等于注入的琴谱", app.score_content() == SCORE,
      f"score={app.score_content()!r}")
check("核心已解析出 9 个音符", controller.player.note_count() == 9,
      f"note_count={controller.player.note_count()}")

# ---------- G. Score 交给真实 score.py 解析 ----------
print("\n--- G. Score 文本进入核心（由 score.py 解析） ---")
app.score_text.delete("1.0", "end")
app.score_text.insert("1.0", "1 2 3")
app._on_score_modified()
check("编辑琴谱后 controller 记录了新文本", controller.score_text_value == "1 2 3",
      f"text={controller.score_text_value!r}")
controller.start()
check("start() 后用新琴谱解析出 3 个音符", controller.player.note_count() == 3,
      f"note_count={controller.player.note_count()}")
check("start() 后核心状态 = Playing", controller.state == "Playing",
      f"core state={controller.state!r}")
app.refresh_from_controller()
check("刷新后 UI Status = 播放中", app.status_text() == "播放中",
      f"status={app.status_text()!r}")
check("刷新后 Current Note = '1'", app.note_text() == "1", f"note={app.note_text()!r}")
controller.shutdown()

# 重新用完整琴谱开始（后续用例）
app.score_text.delete("1.0", "end")
app.score_text.insert("1.0", SCORE)
app._on_score_modified()
controller = app_controller.AppController(input_module=fake_io, score_text=SCORE)
app.controller = controller

# ---------- B. Start ----------
print("\n--- B. Start ---")
app.start_button.invoke()
root.update_idletasks()
check("点击 Start -> 核心进入播放状态", controller.state == "Playing",
      f"state={controller.state}")
check("点击 Start -> UI Status = 播放中", app.status_text() == "播放中",
      f"status={app.status_text()!r}")
check("点击 Start -> Current Note = '1'", app.note_text() == "1",
      f"note={app.note_text()!r}")
check("点击 Start -> Enter Hook 已就绪（由核心负责）", fake_io.is_listening() is True)
check("点击 Start -> 已注册 Enter/Esc/R 回调",
      bool(fake_io.enter_cb.get("down")) and fake_io.escape_cb is not None
      and fake_io.reset_cb is not None)
check("点击 Start -> 核心 index = 0", controller.player.index == 0,
      f"index={controller.player.index}")

# 模拟核心的 Enter 按下/松开（完全等价于 Hook 回调被触发）
fake_io.fire_enter_down()
root.update_idletasks()
check("核心 Enter DOWN -> 真实按下当前音符键",
      "press_key(z)" in fake_io.calls, f"calls tail={fake_io.calls[-2:]}")
fake_io.fire_enter_up()
import time as _t
_t.sleep(0.15)                       # 等 min_hold_ms 落地（真实 timer）
fake_io.fire_enter_down()            # 播放第 2 个音符
fake_io.fire_enter_up()
_t.sleep(0.15)
app.refresh_from_controller()
check("推进 2 个音符后 Current Note 跟随核心 = '3'", app.note_text() == "3",
      f"note={app.note_text()!r} core_index={controller.player.index}")

# ---------- C. Pause ----------
print("\n--- C. Pause ---")
index_before_pause = controller.player.index
app.pause_button.invoke()
root.update_idletasks()
check("点击 Pause -> Status = 已暂停", app.status_text() == "已暂停",
      f"status={app.status_text()!r}")
check("点击 Pause -> 位置未重置（index 不变）",
      controller.player.index == index_before_pause,
      f"before={index_before_pause} after={controller.player.index}")
check("点击 Pause -> 无残留输入", fake_io.held_nothing(),
      f"held={fake_io.held_keys()} mouse={fake_io.held_mouse_buttons()}")
check("点击 Pause -> Hook 已卸载（不再全局吞 Enter）", fake_io.is_listening() is False)
check("点击 Pause -> 与 Reset 不同（index 未归零）", controller.player.index != 0,
      f"index={controller.player.index}")

# ---------- D. Resume ----------
print("\n--- D. Resume ---")
app.resume_button.invoke()
root.update_idletasks()
check("点击 Resume -> Status = 播放中", app.status_text() == "播放中",
      f"status={app.status_text()!r}")
check("点击 Resume -> 从暂停位置继续（不回到第一个音符）",
      controller.player.index == index_before_pause,
      f"index={controller.player.index}")
check("点击 Resume -> Hook 重新就绪", fake_io.is_listening() is True)

# ---------- E. Stop ----------
print("\n--- E. Stop ---")
fake_io.fire_enter_down()            # 制造一个"正在按住"的状态
check("Stop 前有输入被按下（前置条件成立）", not fake_io.held_nothing(),
      f"held={fake_io.held_keys()}")
app.stop_button.invoke()
root.update_idletasks()
check("点击 Stop -> Status = 已停止", app.status_text() == "已停止",
      f"status={app.status_text()!r}")
check("点击 Stop -> release_all 已执行（无残留输入）", fake_io.held_nothing(),
      f"held={fake_io.held_keys()} mouse={fake_io.held_mouse_buttons()}")
check("点击 Stop -> release_all() 被核心调用", "release_all()" in fake_io.calls)
check("点击 Stop -> Hook 已卸载", fake_io.is_listening() is False)

# ---------- F. Reset ----------
print("\n--- F. Reset ---")
app.reset_button.invoke()
root.update_idletasks()
check("点击 Reset -> Status = 就绪", app.status_text() == "就绪",
      f"status={app.status_text()!r}")
check("点击 Reset -> index 回到 0", controller.player.index == 0,
      f"index={controller.player.index}")
check("点击 Reset -> Current Note = '1'", app.note_text() == "1",
      f"note={app.note_text()!r}")
check("点击 Reset -> 无残留输入", fake_io.held_nothing(),
      f"held={fake_io.held_keys()} mouse={fake_io.held_mouse_buttons()}")

# ---------- 核心快捷键路径（不重做，只是验证 UI 与核心共存） ----------
print("\n--- 核心 Esc / R 回调仍然可用（UI 未重做它们） ---")
app.start_button.invoke()
root.update_idletasks()
fake_io.fire_enter_down()
_t.sleep(0.02)
fake_io.fire_escape()
_t.sleep(0.05)
check("核心 Esc 回调 -> 释放输入且 index 保留",
      fake_io.held_nothing() and controller.player.index == 0,
      f"held={fake_io.held_keys()} index={controller.player.index}")
fake_io.fire_reset()
check("核心 R 回调 -> index 归零", controller.player.index == 0,
      f"index={controller.player.index}")

# ---------- 关闭 ----------
print("\n--- 关闭窗口（on_close -> controller.shutdown） ---")
app.on_close()
try:
    alive = root.winfo_exists()
except Exception:
    alive = 0
check("on_close() 后窗口已销毁", alive == 0, f"winfo_exists={alive}")
check("on_close() 后无残留输入", fake_io.held_nothing(),
      f"held={fake_io.held_keys()} mouse={fake_io.held_mouse_buttons()}")
check("on_close() 后 Hook 已卸载", fake_io.is_listening() is False)

# ---------- 占位按钮仍为占位（Task 16 才实现文件操作）----------
print("\n--- Open / Save 仍为占位（Task 16） ---")
root2 = tk.Tk()
root2.withdraw()
ctrl2 = app_controller.AppController(input_module=FakeInput(), score_text=SCORE)
app2 = ui_module.HarmonicaUI(root2, controller=ctrl2)
# Task 15 时 Open/Save 是占位按钮；Task 16 把它们接成了真实文件功能。
# 因此这里不再断言"占位文案"，改为验证 Task 16 之后的实际契约，并且**绝不调用会弹
# 系统文件对话框的路径**（那会阻塞等待人工操作，导致测试挂起）：
#   - 有已知文件路径时 -> save_file() 直接写文件，不弹对话框
#   - 无路径时 -> 返回 NEED_DIALOG（要不要弹框由 UI 决定）
import tempfile as _tempfile
_tmpdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "task15_tmp")
os.makedirs(_tmpdir, exist_ok=True)
_tmppath = os.path.join(_tmpdir, "task15_save.txt")

app2._apply_result(ctrl2.save_file(_tmppath))   # 直接给路径：不弹对话框
root2.update_idletasks()
check("Save（有路径）写出文件且不弹对话框",
      os.path.exists(_tmppath), f"exists={os.path.exists(_tmppath)}")
check("Save 状态显示 已保存", app2.status_text().startswith("已保存"),
      f"status={app2.status_text()!r}")

ctrl2.current_path = None
r2 = ctrl2.save_file()
check("Save（无路径）返回 NEED_DIALOG 交给 UI 弹框",
      r2 == app_controller.NEED_DIALOG, f"result={r2!r}")

ctrl2.current_path = None
r3 = ctrl2.open_file()
check("Open（无路径）返回 NEED_DIALOG 交给 UI 弹框",
      r3 == app_controller.NEED_DIALOG, f"result={r3!r}")

app2.on_close()

print()
failed = [n for n, ok in results if not ok]
print("=" * 68)
print(f"Task 15 连接测试：总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for n in failed:
        print("  - " + n)
    sys.exit(1)
print("全部通过")
sys.exit(0)
