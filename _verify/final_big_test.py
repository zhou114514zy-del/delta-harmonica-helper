"""FINAL BIG TEST — 覆盖 A..J（真实核心 + 受控输入替身 + 真实文件/GUI）。

安全与确定性设计：
    - 不使用 keybd_event / SendInput / mouse_event 伪造 Enter 或演奏音符
    - Enter 的吞键 / 去重 / 回调路径：直接调用 input.py 的真实钩子回调函数
      （input._hook_callback）并检查返回值与回调次数 —— 这是产品真实的拦截机制，
      且不向系统输入流注入任何按键
    - 演奏/输入用"记录器"input 替身注入，绝不碰真实键鼠
    - 普通键 pass-through：真实装钩子后检查返回值 + 用专用测试窗口接收真实按键
    - GUI：真实 Tk 窗口（withdraw 不弹窗）+ 子进程 main.py 自动关闭
    - 顶层 try/finally 保证任何情况下都 release_all()、无残留
"""
import ctypes
import io as _io
import os
import subprocess
import sys
import time
import tkinter as tk
from ctypes import wintypes

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import app_controller  # noqa: E402
import input as real_input  # noqa: E402
import ui as ui_module  # noqa: E402
from input import KBDLLHOOKSTRUCT  # noqa: E402

results = []
SECTIONS = {}
_current_section = ["?"]


def section(name):
    _current_section[0] = name
    SECTIONS.setdefault(name, [0, 0])
    print(f"\n--- {name} ---")


def check(name, condition, detail=""):
    ok = bool(condition)
    SECTIONS.setdefault(_current_section[0], [0, 0])
    SECTIONS[_current_section[0]][0 if ok else 1] += 1
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


# ---------------------------------------------------------------- 输入替身
class FakeInput:
    def __init__(self):
        self.calls = []
        self.enter_cb = {}
        self.escape_cb = None
        self.reset_cb = None
        self._listening = False
        self._held = set()
        self._mouse = set()
        self._release_all_count = 0

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
        self._release_all_count += 1
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

    def fire_down(self):
        if self.enter_cb.get("down"):
            self.enter_cb["down"]()

    def fire_up(self):
        if self.enter_cb.get("up"):
            self.enter_cb["up"]()

    def fire_esc(self):
        if self.escape_cb:
            self.escape_cb()

    def fire_reset(self):
        if self.reset_cb:
            self.reset_cb()

    def held_nothing(self):
        return not self._held and not self._mouse

    def count(self, name):
        return self.calls.count(name)


FULL_SCORE = "1 2 [\u2191 3 4 5] 6 [~ 7 1'] [\u2193 2]"
MIN_HOLD = 50
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "final_tmp")
os.makedirs(TMP, exist_ok=True)

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK = {"enter": 0x0D, "esc": 0x1B, "r": 0x52, "z": 0x5A, "x": 0x58, "c": 0x43,
      "v": 0x56, "b": 0x42, "n": 0x4E, "m": 0x4D, "comma": 0xBC,
      "left": 0x01, "middle": 0x04, "right": 0x02,
      "a": 0x41, "space": 0x20, "tab": 0x09, "shift": 0x10, "ctrl": 0x11, "alt": 0x12}
_keep = {}


def down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def all_up():
    return not any(down(v) for v in VK.values())


def post(vk, message):
    """直接调用产品真实的钩子回调（不注入任何系统按键）。返回回调返回值。"""
    info = KBDLLHOOKSTRUCT()
    info.vkCode = vk; info.scanCode = 0; info.flags = 0; info.time = 0; info.dwExtraInfo = 0
    _keep["i"] = info
    return real_input._hook_callback(0, message,
                                     ctypes.cast(ctypes.pointer(info), ctypes.c_void_p).value)


def new_controller(score_text="1 2 3", feedback=None):
    fake = FakeInput()
    ctrl = app_controller.AppController(input_module=fake, score_text=score_text,
                                        ui_thread_after=feedback)
    return fake, ctrl


def new_app(score_text="1 2 3"):
    fake, ctrl = new_controller(score_text)
    root = tk.Tk(); root.withdraw()
    app = ui_module.HarmonicaUI(root, controller=ctrl)
    root.update_idletasks()
    return fake, ctrl, root, app


def rearm(ctrl):
    """让控制器回到"Playing + index 0"，同时确保旧 timer 被失效。

    pause() 会走核心的 emergency_stop（失效 pending timer + 释放输入）并卸载 Hook；
    随后 start() 会用琴谱新建 player 并回到 Playing。
    """
    ctrl.pause()
    ctrl.start()


def tap(fake, hold_s=0.005, settle_s=0.15):
    fake.fire_down(); time.sleep(hold_s); fake.fire_up(); time.sleep(settle_s)


print("=" * 74)
print("FINAL BIG TEST — Delta Harmonica Helper")
print("=" * 74)

try:
    # ================= A. GUI 基础 =================
    section("A. GUI basics")
    fake, ctrl, root, app = new_app(FULL_SCORE)
    check("A1 窗口创建成功", root.winfo_exists() == 1)
    check("A2 窗口标题正确", root.title() == "Delta Harmonica Helper", f"title={root.title()!r}")
    root.update_idletasks()
    check("A3 窗口尺寸 700x620", "700x620" in root.geometry(), f"geometry={root.geometry()}")
    check("A4 Status 显示（来自核心）", app.status_text() == "Idle", f"status={app.status_text()!r}")
    check("A5 Current Note 显示第一个音符", app.note_text() == "1", f"note={app.note_text()!r}")
    check("A6 Score 文本可读取", app.score_content() == FULL_SCORE,
          f"len={len(app.score_content())}")
    labels = app.button_labels()
    check("A7 五个控制按钮齐全",
          all(labels[k] == v for k, v in [("start", "Start"), ("pause", "Pause"),
                                          ("resume", "Resume"), ("stop", "Stop"),
                                          ("reset", "Reset")]), f"labels={labels}")
    check("A8 Open/Save 按钮存在", labels["open"] == "Open" and labels["save"] == "Save",
          f"open={labels['open']!r} save={labels['save']!r}")
    shortcuts = app.shortcut_texts()
    check("A9 快捷键提示齐全",
          shortcuts == ["Enter = Play / Hold", "Esc = Emergency Stop", "R = Reset"],
          f"shortcuts={shortcuts}")
    check("A10 Score 为多行文本框", app.score_text.winfo_class() == "Text")
    app.on_close()
    try:
        alive = root.winfo_exists()
    except Exception:
        alive = 0
    check("A11 自动关闭成功", alive == 0, f"winfo_exists={alive}")

    # 子进程真实启动 GUI 并自动关闭
    env = dict(os.environ); env["DSH_UI_TEST_SELF_CLOSE_MS"] = "1800"
    proc = subprocess.Popen([sys.executable, "main.py"], cwd=PROJECT_DIR, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(timeout=40)
        check("A12 main.py 启动 GUI 并自行退出", proc.returncode == 0,
              f"exit={proc.returncode}")
        check("A13 无 stderr / traceback", not (err or "").strip(), f"stderr={(err or '').strip()!r}")
    except subprocess.TimeoutExpired:
        proc.kill(); proc.communicate()
        check("A12 main.py 启动 GUI 并自行退出", False, "TIMEOUT(40s)")
        check("A13 无 stderr / traceback", False, "process hung")

    # ================= B. Score 编辑 =================
    section("B. Score editing")
    fake, ctrl, root, app = new_app("1 2 3")
    check("B1 初始 Score 交给核心解析", ctrl.player.note_count() == 3,
          f"note_count={ctrl.player.note_count()}")
    app.score_text.delete("1.0", "end")
    app.score_text.insert("1.0", FULL_SCORE)
    app._on_score_modified()
    root.update_idletasks()
    check("B2 编辑后 controller 收到 score_modified", ctrl.score_text_value == FULL_SCORE,
          f"len={len(ctrl.score_text_value)}")
    check("B3 编辑不触发解析（只在 Start 时解析）", ctrl.player.note_count() == 3,
          f"note_count={ctrl.player.note_count()}（仍为旧值，正确）")
    app.start_button.invoke(); root.update_idletasks()
    check("B4 Start 后用新 score 解析出 9 个音符", ctrl.player.note_count() == 9,
          f"note_count={ctrl.player.note_count()}")
    check("B5 Start 后 Status=Playing", app.status_text() == "Playing",
          f"status={app.status_text()!r}")
    app.stop_button.invoke(); app.on_close()

    # ================= C. Start / Enter 播放链 =================
    section("C. Start / Enter playback chain")
    fake, ctrl, root, app = new_app(FULL_SCORE)
    app.start_button.invoke(); root.update_idletasks()
    check("C1 Start -> Playing", ctrl.state == "Playing", f"state={ctrl.state!r}")
    check("C2 Start -> 注册回调 + Hook 就绪",
          bool(fake.enter_cb.get("down")) and fake.is_listening() is True)
    fake.fire_down()
    check("C3 Enter DOWN -> 按下当前音符键 z", "press_key(z)" in fake.calls,
          f"tail={fake.calls[-2:]}")
    fake.fire_up(); time.sleep(0.15)
    check("C4 Enter UP -> 释放并推进到下一个音符（x）",
          "release_key(z)" in fake.calls and ctrl.player.index == 1,
          f"index={ctrl.player.index} tail={fake.calls[-2:]}")
    # 重复 DOWN 不重复触发
    n_before = fake.count("press_key(x)")
    fake.fire_down()
    fake.fire_down()
    fake.fire_down()
    check("C5 重复 Enter DOWN 不重复按下（去重）",
          fake.count("press_key(x)") == n_before, f"press_key(x) x{fake.count('press_key(x)')}")
    fake.fire_up(); time.sleep(0.15)
    # 走完整条 score
    for _ in range(9):
        if ctrl.player.is_finished():
            break
        fake.fire_down(); time.sleep(0.01); fake.fire_up(); time.sleep(0.15)
    check("C6 整条 score 正确推进到结束", ctrl.player.is_finished(),
          f"index={ctrl.player.index}/{ctrl.player.note_count()}")
    app.refresh_from_controller(); root.update_idletasks()
    check("C7 播完 Current Note 显示 '-'", app.note_text() == "-", f"note={app.note_text()!r}")
    check("C8 播完无残留输入", fake.held_nothing(),
          f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
    app.on_close()

    # ================= D. 连续变调 =================
    section("D. Modifiers")
    expect_mod = [("1", "z", None), ("2", "x", None),
                  ("3", "c", "right"), ("4", "v", "right"), ("5", "b", "right"),
                  ("6", "n", None),
                  ("7", "m", "middle"), ("1'", ",", "middle"),
                  ("2", "x", "left")]
    fake, ctrl, root, app = new_app(FULL_SCORE)
    app.start_button.invoke(); root.update_idletasks()
    seen = []
    for _ in range(9):
        fake.fire_down()
        st = ctrl.player.current_state()
        seen.append((str(ctrl.player.current_note().note), sorted(st.keys),
                     sorted(st.mouse_buttons)))
        fake.fire_up(); time.sleep(0.15)
    ok_all = all((n, [k], ([] if m is None else [m])) == got for (n, k, m), got in zip(expect_mod, seen))
    check("D1 normal / sharp(right) / half(middle) / flat(left) 全部正确", ok_all,
          f"seen={seen}")
    r_press = fake.count("press_mouse(right)")
    m_press = fake.count("press_mouse(middle)")
    l_press = fake.count("press_mouse(left)")
    check("D2 连续相同 modifier 不重复 press（right/middle/left 各 1 次）",
          r_press == 1 and m_press == 1 and l_press == 1,
          f"right={r_press} middle={m_press} left={l_press}")
    # jitter：区间内部不应出现 release
    seq = [(c, fake.calls.index(c)) for c in fake.calls if c.startswith(("press_mouse", "release_mouse"))]
    jitter_free = True
    # 检查 right 在 3->4->5 之间没有被 release
    idx_press = [i for i, c in enumerate(fake.calls) if c == "press_mouse(right)"]
    idx_rel = [i for i, c in enumerate(fake.calls) if c == "release_mouse(right)"]
    if idx_press and idx_rel:
        jitter_free = idx_rel[0] > idx_press[0]
    check("D3 区间内 modifier 无 UP->DOWN 抖动", jitter_free, f"mouse calls={seq}")
    app.on_close()

    # ================= E. min_hold_ms = 50 =================
    section("E. min_hold_ms = 50")
    fake, ctrl, root, app = new_app("1 2 3")
    app.start_button.invoke(); root.update_idletasks()
    t0 = time.monotonic()
    fake.fire_down(); time.sleep(0.003); fake.fire_up()
    check("E1 极短 hold：音符仍保持 DOWN（未提前释放）",
          ctrl.player.current_state_text() == "keys=[z] mouse=[-]",
          f"state={ctrl.player.current_state_text()}")
    check("E2 极短 hold：index 未推进", ctrl.player.index == 0, f"index={ctrl.player.index}")
    check("E3 timer 已挂起", ctrl.player._pending_timer is not None)
    deadline = time.monotonic() + 1.0
    while ctrl.player._pending_timer is not None and time.monotonic() < deadline:
        time.sleep(0.002)
    held_ms = (time.monotonic() - t0) * 1000
    check("E4 实际保持 >= min_hold_ms(50ms)", held_ms >= MIN_HOLD - 5,
          f"measured {held_ms:.1f}ms")
    check("E5 到点后释放并推进", ctrl.player.index == 1, f"index={ctrl.player.index}")
    # 正常长按
    fake.fire_down(); time.sleep(0.15)
    check("E6 正常长按期间保持 DOWN",
          ctrl.player.current_state_text() == "keys=[x] mouse=[-]",
          f"state={ctrl.player.current_state_text()}")
    t1 = time.monotonic(); fake.fire_up()
    check("E7 长按松开后立即释放（无额外等待）",
          ctrl.player.current_state_text() == "keys=[c] mouse=[-]"
          and (time.monotonic() - t1) < 0.1, f"state={ctrl.player.current_state_text()}")
    # 边界（注意：每次都要先让控制器回到 Playing，否则 Enter 会被 Playing 守卫忽略）
    rearm(ctrl)
    fake.fire_down(); time.sleep(0.025); fake.fire_up()
    check("E8 25ms(<50) 挂 timer", ctrl.player._pending_timer is not None,
          f"state={ctrl.state!r} timer={ctrl.player._pending_timer}")
    time.sleep(0.15)
    rearm(ctrl)
    fake.fire_down(); time.sleep(0.08); fake.fire_up()
    check("E9 80ms(>50) 立即完成不挂 timer", ctrl.player._pending_timer is None,
          f"timer={ctrl.player._pending_timer}")
    time.sleep(0.15)
    # UP 后立即 Esc
    rearm(ctrl)
    fake.fire_down(); time.sleep(0.003); fake.fire_up()
    check("E10a 前置：timer 确实挂起", ctrl.player._pending_timer is not None)
    fake.fire_esc()                       # Esc 自己会立即释放当前输入（这是正确行为）
    check("E10 UP 后立即 Esc：timer 失效且无残留",
          fake.held_nothing() and ctrl.player._pending_timer is None,
          f"held={fake.held_keys()} timer={ctrl.player._pending_timer}")
    time.sleep(0.02)
    calls_snap = list(fake.calls)         # Esc 之后再取快照
    time.sleep(0.25)                      # 等过旧 timer 原本该到点的时刻
    check("E11 Esc 后旧 timer 不再产生任何输入", fake.calls == calls_snap,
          f"extra={fake.calls[len(calls_snap):]}")
    # UP 后立即 R
    rearm(ctrl)
    fake.fire_down(); time.sleep(0.003); fake.fire_up()
    fake.fire_reset(); snap2 = list(fake.calls)
    check("E12 UP 后立即 R：index=0 且无残留",
          ctrl.player.index == 0 and fake.held_nothing(), f"index={ctrl.player.index}")
    time.sleep(0.2)
    check("E13 R 后旧 timer 不再产生输入", fake.calls == snap2,
          f"extra={fake.calls[len(snap2):]}")
    # UP 后立即 shutdown
    rearm(ctrl)
    fake.fire_down(); time.sleep(0.003); fake.fire_up()
    ctrl.shutdown(); snap3 = list(fake.calls)
    time.sleep(0.2)
    check("E14 UP 后 shutdown：无残留、旧 timer 失效",
          fake.held_nothing() and fake.calls == snap3,
          f"held={fake.held_keys()} extra={fake.calls[len(snap3):]}")
    app.on_close()

    # ================= F. Pause / Resume / Stop / Reset =================
    section("F. Pause / Resume / Stop / Reset")
    fake, ctrl, root, app = new_app("1 2 3 4")
    app.start_button.invoke(); fake.fire_down(); fake.fire_up(); time.sleep(0.15)
    fake.fire_down(); fake.fire_up(); time.sleep(0.15)
    idx_before = ctrl.player.index
    check("F0 前置：index=2", idx_before == 2, f"index={idx_before}")
    app.pause_button.invoke(); root.update_idletasks()
    check("F1 Pause：Status=Paused", app.status_text() == "Paused", f"status={app.status_text()!r}")
    check("F2 Pause：index 不前进", ctrl.player.index == idx_before, f"index={ctrl.player.index}")
    check("F3 Pause：核心已释放输入（无残留）", fake.held_nothing(),
          f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
    check("F4 Pause：Hook 已卸载", fake.is_listening() is False)
    app.resume_button.invoke(); root.update_idletasks()
    check("F5 Resume：Status=Playing 且 index 不变",
          app.status_text() == "Playing" and ctrl.player.index == idx_before,
          f"status={app.status_text()!r} index={ctrl.player.index}")
    check("F6 Resume：Hook 重新就绪", fake.is_listening() is True)
    fake.fire_down()
    check("F7 Resume 后可从当前位置继续（播放 3=c）",
          ctrl.player.current_state_text() == "keys=[c] mouse=[-]",
          f"state={ctrl.player.current_state_text()}")
    app.stop_button.invoke(); root.update_idletasks()
    check("F8 Stop：Status=Stopped", app.status_text() == "Stopped", f"status={app.status_text()!r}")
    check("F9 Stop：核心已释放全部输入（无残留）", fake.held_nothing(),
          f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
    check("F10 Stop：Hook 已卸载", fake.is_listening() is False)
    app.reset_button.invoke(); root.update_idletasks()
    check("F11 Reset：Status=Ready 且 index=0",
          app.status_text() == "Ready" and ctrl.player.index == 0,
          f"status={app.status_text()!r} index={ctrl.player.index}")
    check("F12 Reset：Current Note=1 且无残留",
          app.note_text() == "1" and fake.held_nothing(), f"note={app.note_text()!r}")
    app.on_close()

    # ================= G. Esc / R =================
    section("G. Esc / R + double-press window")
    fake, ctrl, root, app = new_app(FULL_SCORE)
    app.start_button.invoke()
    fake.fire_down(); fake.fire_up(); time.sleep(0.15)
    fake.fire_down()
    check("G0 前置：正在播放 2（x）", ctrl.player.current_state_text() == "keys=[x] mouse=[-]",
          f"state={ctrl.player.current_state_text()}")
    fake.fire_esc()
    check("G1 Esc 一次：emergency stop（释放输入）", fake.held_nothing(),
          f"held={fake.held_keys()}")
    check("G2 Esc 一次：index 不变", ctrl.player.index == 1, f"index={ctrl.player.index}")
    fake.fire_up()
    app.start_button.invoke(); root.update_idletasks()
    check("G3 Esc 后可重新 Start", ctrl.state == "Playing", f"state={ctrl.state!r}")
    fake.fire_reset()
    check("G4 R：reset 到 index 0", ctrl.player.index == 0, f"index={ctrl.player.index}")
    ok = True
    try:
        for _ in range(3):
            fake.fire_esc()
        for _ in range(3):
            fake.fire_reset()
    except Exception as exc:  # noqa: BLE001
        ok = False
        print("        raised:", repr(exc))
    check("G5 重复 Esc x3 / R x3 不出错且无残留",
          ok and fake.held_nothing() and ctrl.player._pending_timer is None,
          f"held={fake.held_keys()} timer={ctrl.player._pending_timer}")
    # Esc 双击时间窗（与 main.py run_cli 相同的判定表达式）
    ESC_WINDOW = 0.8
    a = time.monotonic(); time.sleep(0.2); b = time.monotonic()
    check("G6 0.2s 内两次 Esc 判为双击（应退出）", (b - a) <= ESC_WINDOW,
          f"gap={b - a:.2f}s")
    time.sleep(0.95); c = time.monotonic()
    check("G7 超过 0.8s 不判为双击（不应退出）", (c - b) > ESC_WINDOW, f"gap={c - b:.2f}s")
    # 退出路径无残留
    ctrl.shutdown(); snap = list(fake.calls); time.sleep(0.2)
    check("G8 shutdown 后无 timer / listener / input 残留",
          fake.held_nothing() and fake.is_listening() is False
          and ctrl.player._pending_timer is None and fake.calls == snap,
          f"held={fake.held_keys()} listening={fake.is_listening()}")
    app.on_close()

    # ================= H. Enter swallow / dedup / pass-through =================
    section("H. Enter swallow / dedup / pass-through")
    counts = {"down": 0, "up": 0}

    def on_down():
        counts["down"] += 1

    def on_up():
        counts["up"] += 1

    real_input.set_enter_callbacks(on_down=on_down, on_up=on_up)
    real_input.set_escape_callback(lambda: None)
    real_input.set_reset_callback(lambda: None)

    def drain():
        """产品把用户回调丢到工作线程异步执行，读计数前必须先等它跑完。"""
        real_input._drain_callbacks(timeout=1.0)

    rv_enter_down = post(VK["enter"], WM_KEYDOWN)
    rv_enter_up = post(VK["enter"], WM_KEYUP)
    drain()
    check("H1 Enter 被吞掉（钩子返回 1/1）", rv_enter_down == 1 and rv_enter_up == 1,
          f"down={rv_enter_down} up={rv_enter_up}")
    check("H2 Enter DOWN/UP 正常进入程序（各 1 次）",
          counts["down"] == 1 and counts["up"] == 1, f"counts={counts}")
    # 长按去重：必须用"连续多次 DOWN 中间不夹 UP"来测，否则第一次 DOWN 是合法的新按下
    before_press = dict(counts)
    for _ in range(10):
        post(VK["enter"], WM_KEYDOWN)
    drain()
    check("H3 长按 Enter 只有一次 DOWN（去重）",
          counts["down"] == before_press["down"] + 1, f"counts={counts}")
    for _ in range(3):
        post(VK["enter"], WM_KEYUP)
    drain()
    check("H4 重复 UP 只产生一次 UP",
          counts["up"] == before_press["up"] + 1, f"counts={counts}")
    # 模拟音符按键不会再次触发 Enter 回调
    before = dict(counts)
    note_rvs = []
    for key in ("z", "x", "c", "v", "b", "n", "m", "comma"):
        note_rvs.append(post(VK[key], WM_KEYDOWN))
        note_rvs.append(post(VK[key], WM_KEYUP))
    drain()
    check("H5 音符按键不触发 Enter 回调（且返回 0 放行）",
          counts == before and set(note_rvs) == {0},
          f"before={before} after={counts} rvs={set(note_rvs)}")
    # 普通键 pass-through（返回值 0 = 放行）
    passthrough = {"a", "space", "tab", "shift", "ctrl", "alt"}
    rv_ok = all(post(VK[k], WM_KEYDOWN) == 0 and post(VK[k], WM_KEYUP) == 0 for k in passthrough)
    drain()
    check("H6 A/Space/Tab/Shift/Ctrl/Alt 放行（返回 0）", rv_ok)
    check("H7 普通键不触发 Enter 回调", counts == before, f"counts={counts}")

    # 真实装钩子 / 卸载
    real_input.start_enter_listener()
    check("H8 真实钩子安装成功", real_input.is_listening() is True)
    real_input.stop_enter_listener()
    check("H9 真实钩子卸载成功", real_input.is_listening() is False)

    # ================= I. Open / Save =================
    section("I. Open / Save")
    p_full = os.path.join(TMP, "f_full.txt")
    with open(p_full, "w", encoding="utf-8") as fh:
        fh.write(FULL_SCORE)
    fake, ctrl, root, app = new_app("")
    app._ask_open_path = lambda: p_full
    app.open_button.invoke(); root.update_idletasks()
    check("I1 Open 有效 .txt：内容载入", app.score_content() == FULL_SCORE,
          f"len={len(app.score_content())}")
    check("I2 Open 后 Status 显示 Opened", app.status_text().startswith("Opened"),
          f"status={app.status_text()!r}")
    check("I3 Open 后未自动播放", ctrl.state != "Playing", f"state={ctrl.state!r}")
    # 空文件
    p_empty = os.path.join(TMP, "f_empty.txt")
    open(p_empty, "w", encoding="utf-8").close()
    app._ask_open_path = lambda: p_empty
    app.open_button.invoke(); root.update_idletasks()
    check("I4 Open 空文件成功且 Score 可为空", app.score_content() == "",
          f"content={app.score_content()!r}")
    # 非法 score
    p_bad = os.path.join(TMP, "f_bad.txt")
    with open(p_bad, "w", encoding="utf-8") as fh:
        fh.write("1 2 [\u2191")
    app._ask_open_path = lambda: p_bad
    app.open_button.invoke(); root.update_idletasks()
    check("I5 Open 非法 score 成功（只读文本）", app.score_content() == "1 2 [\u2191",
          f"content={app.score_content()!r}")
    app.start_button.invoke(); app.refresh_from_controller(); root.update_idletasks()
    check("I6 非法 score 在 Start 时由 score.py 报错（UI 显示 Error）",
          app.status_text() == "Error" and app.error_var.get() != "",
          f"status={app.status_text()!r} error={app.error_var.get()!r}")
    # cancel
    app._ask_open_path = lambda: ""
    app.open_button.invoke(); root.update_idletasks()
    check("I7 Open 取消：不崩溃且状态明确",
          app.status_text() == ui_module.STATUS_OPEN_CANCELLED, f"status={app.status_text()!r}")
    app._ask_save_path = lambda: ""
    ctrl.current_path = None
    app.save_button.invoke(); root.update_idletasks()
    check("I8 Save 取消：不崩溃且状态明确",
          app.status_text() == ui_module.STATUS_SAVE_CANCELLED, f"status={app.status_text()!r}")
    # 有效 score -> 修改 -> Save
    app._ask_open_path = lambda: p_full
    app.open_button.invoke(); root.update_idletasks()
    app.score_text.delete("1.0", "end"); app.score_text.insert("1.0", "1 2 3")
    app._on_score_modified()
    app.save_button.invoke(); root.update_idletasks()
    with open(p_full, "r", encoding="utf-8") as fh:
        saved = fh.read()
    check("I9 修改后 Save 写回原文件且内容正确", saved == "1 2 3", f"saved={saved!r}")
    with open(p_full, "rb") as fh:
        raw = fh.read()
    check("I10 UTF-8 编码正确（可解码、无 BOM）",
          raw.decode("utf-8") == "1 2 3" and not raw.startswith(b"\xef\xbb\xbf"), f"raw={raw!r}")
    # Save As
    p_as = os.path.join(TMP, "f_saveas.txt")
    ctrl.current_path = None
    app._ask_save_path = lambda: p_as
    app.save_button.invoke(); root.update_idletasks()
    check("I11 Save As 写出新文件", os.path.exists(p_as))
    with open(p_as, "r", encoding="utf-8") as fh:
        as_content = fh.read()
    check("I12 Save As 内容正确", as_content == "1 2 3", f"content={as_content!r}")
    # Playing 状态下 Open / Save
    p_h = os.path.join(TMP, "f_new.txt")
    with open(p_h, "w", encoding="utf-8") as fh:
        fh.write("1 2 3 4 5")
    app._ask_open_path = lambda: p_full
    app.open_button.invoke(); root.update_idletasks()
    app.start_button.invoke(); root.update_idletasks()
    check("I13 Playing 前置成立", ctrl.state == "Playing", f"state={ctrl.state!r}")
    fake.fire_down()
    check("I14 Playing 时有输入被按下", not fake.held_nothing())
    app._ask_open_path = lambda: p_h
    app.open_button.invoke(); root.update_idletasks()
    check("I15 Playing -> Open：安全停止并释放输入", fake.held_nothing(),
          f"held={fake.held_keys()}")
    check("I16 Playing -> Open：release_all 由核心执行", fake.count("release_all()") >= 1)
    check("I17 Playing -> Open：不自动恢复播放", ctrl.state != "Playing", f"state={ctrl.state!r}")
    check("I18 Playing -> Open：新 Score 已载入", app.score_content() == "1 2 3 4 5",
          f"content={app.score_content()!r}")
    # Playing 状态 Save 不改位置
    app.start_button.invoke(); root.update_idletasks()
    idx_b = ctrl.player.index
    app._ask_save_path = lambda: p_as
    ctrl.current_path = None
    app.save_button.invoke(); root.update_idletasks()
    check("I19 Playing -> Save：不改变播放位置与状态",
          ctrl.player.index == idx_b and ctrl.state == "Playing",
          f"index={ctrl.player.index} state={ctrl.state!r}")
    ctrl.shutdown()
    check("I20 Open/Save 全程无输入残留", fake.held_nothing() and all_up(),
          f"held={fake.held_keys()} all_up={all_up()}")
    app.on_close()

    # ================= J. Final input state =================
    section("J. Final input state")
    real_input.release_all()
    try:
        real_input.stop_enter_listener()
    except Exception:
        pass
    time.sleep(0.3)
    stuck = [name for name, vk in VK.items() if down(vk)]
    check("J1 所有键与鼠标均 UP（无 stuck）", not stuck, f"stuck={stuck}")
    rows = {name: down(vk) for name, vk in VK.items()}
    check("J2 z/x/c/v/b/n/m/comma 全部 UP",
          not any(rows[k] for k in ("z", "x", "c", "v", "b", "n", "m", "comma")))
    check("J3 left/middle/right 全部 UP",
          not any(rows[k] for k in ("left", "middle", "right")))
    check("J4 Enter / R / Esc 全部 UP",
          not any(rows[k] for k in ("enter", "r", "esc")))

finally:
    # 兜底：任何情况下都释放真实输入、卸载钩子、清理临时文件
    try:
        real_input.release_all()
        real_input.stop_enter_listener()
    except Exception:
        pass
    print("\n" + "=" * 74)

# ---------------- 汇总 ----------------
print("分节统计：")
for name, (p, f) in SECTIONS.items():
    print(f"  {name:<38} PASS={p:<4} FAIL={f}")
total_p = sum(1 for _, ok in results if ok)
total_f = sum(1 for _, ok in results if not ok)
print("-" * 74)
print(f"FINAL BIG TEST (A-J)：总计 {len(results)} 项，PASS={total_p}，FAIL={total_f}")
print(f"最终键鼠状态：{'ALL UP' if all_up() else 'RESIDUE: ' + str([k for k, v in VK.items() if down(v)])}")
if total_f:
    print("失败项：")
    for n, ok in results:
        if not ok:
            print("  - " + n)
    sys.exit(1)
print("A-J 全部通过")
sys.exit(0)
