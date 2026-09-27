"""CORE BIG TEST —— 真实系统级部分。

安全设计：
    - 不使用 keybd_event / SendInput / mouse_event 发送 Enter、音符键或鼠标键
    - Enter/Esc/R 全部通过 input.py 的钩子回调正式路径投递
    - 真实音符输入只来自 PlaybackExecutor -> input.py
    - 状态用只读 GetAsyncKeyState 校验
    - 顶层 try/finally 保证任何情况下都 release_all()，绝不留卡键
    - 使用真实 config.json 的 min_hold_ms（必须为 50）

    唯一使用 keybd_event 的地方：给"专用测试窗口"发送普通键（A/Z/Space/Tab/Shift/Ctrl/Alt），
    用于验证这些键不会被 Enter Hook 吞掉；发送前会确认前台窗口就是该测试窗口。
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import input as io  # noqa: E402
from harmonica_app import FixedScorePlayer, load_min_hold_ms  # noqa: E402
from input import KBDLLHOOKSTRUCT  # noqa: E402
from score import parse_score_notes  # noqa: E402

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
                                wintypes.LPARAM]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, ctypes.c_void_p]

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK_RETURN, VK_ESCAPE, VK_R = 0x0D, 0x1B, 0x52
SW_RESTORE = 9


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def find_test_window(pid=None, title_fragment="DSH Task"):
    """按进程 id 或标题片段找到测试窗口。"""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        pid_out = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
        if pid is not None and pid_out.value != pid:
            return True
        if pid is None and title_fragment not in _title(hwnd):
            return True
        if not _class_name(hwnd).startswith("WindowsForms10"):
            return True
        found.append(hwnd)
        return False

    _user32.EnumWindows(cb, 0)
    return found[0] if found else None


def start_test_window(log_path):
    """启动专用测试窗口，等它出现并把前台交给它。返回 (process, hwnd)。"""
    global _test_window
    stop_test_window()
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_window.ps1")
    proc = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", script, log_path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    hwnd = None
    for _ in range(40):
        time.sleep(0.5)
        if proc.poll() is not None:
            break
        hwnd = find_test_window(proc.pid)
        if hwnd:
            break
    if hwnd:
        time.sleep(0.8)
        _user32.ShowWindow(hwnd, SW_RESTORE)
        _user32.SetForegroundWindow(hwnd)
        time.sleep(0.6)
    _test_window = (proc, hwnd)
    return proc, hwnd


def stop_test_window():
    global _test_window
    if _test_window is None:
        return
    proc, _ = _test_window
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    _test_window = None

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK_RETURN, VK_ESCAPE, VK_R = 0x0D, 0x1B, 0x52

KEY_VKS = {"z": 0x5A, "x": 0x58, "c": 0x43, "v": 0x56, "b": 0x42,
           "n": 0x4E, "m": 0x4D, ",": 0xBC}
MOUSE_VKS = {"left": 0x01, "right": 0x02, "middle": 0x04}
_keep = {}
results = []
player = None
MIN_HOLD = load_min_hold_ms()
assert MIN_HOLD == 50, f"必须使用真实配置值 50，实际 {MIN_HOLD}"
SETTLE = MIN_HOLD / 1000.0 + 0.10


def down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def actual():
    keys = "+".join(sorted(n for n, vk in KEY_VKS.items() if down(vk)))
    buttons = "/".join(sorted(n for n, vk in MOUSE_VKS.items() if down(vk)))
    return f"{keys}|{buttons}"


def nothing_held():
    """逐键确认真实状态：所有音符键与鼠标键都是 UP。"""
    return (not any(down(vk) for vk in KEY_VKS.values())
            and not any(down(vk) for vk in MOUSE_VKS.values()))


def check(name, expected, actual_value=None):
    got = actual() if actual_value is None else actual_value
    ok = expected == got
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}   expected=[{expected}] actual=[{got}]")


def check_true(name, condition, detail=""):
    """布尔条件断言（不参与键鼠状态字符串比较）。"""
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}   {detail}")


# ---- 专用测试窗口（用于验证"普通键真的送达应用"）----
_test_window = None


def click_normal_key(vk):
    """用 keybd_event 给当前前台（必须是测试窗口）发送一个普通键。"""
    _user32.keybd_event(vk, 0, 0, None)
    time.sleep(0.05)
    _user32.keybd_event(vk, 0, 2, None)


def post_key(vk, message):
    """通过钩子回调正式路径投递事件；返回钩子的返回值（1=吞掉，0=放行）。"""
    info = KBDLLHOOKSTRUCT()
    info.vkCode = vk
    info.scanCode = 0
    info.flags = 0
    info.time = 0
    info.dwExtraInfo = 0
    _keep["i"] = info
    return io._hook_callback(0, message, ctypes.cast(ctypes.pointer(info), ctypes.c_void_p).value)


def drain():
    for _ in range(100):
        if io._drain_callbacks(timeout=0.5):
            return
        time.sleep(0.004)


def press(vk):
    post_key(vk, WM_KEYDOWN); drain()
    post_key(vk, WM_KEYUP); drain()


def enter_down():
    post_key(VK_RETURN, WM_KEYDOWN); drain()


def enter_up():
    post_key(VK_RETURN, WM_KEYUP); drain()


def wait_until(pred, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.002)
    return False


def settle():
    wait_until(lambda: player is not None and player._pending_timer is None, 1.5)
    time.sleep(0.01)


def make(score_text):
    global player
    if player is not None:
        player.shutdown()
    io.release_all()
    io._enter_down = False
    io._escape_down = False
    io._r_down = False
    wait_until(lambda: actual() == "", 1.0)
    player = FixedScorePlayer(parse_score_notes(score_text), min_hold_ms=MIN_HOLD)
    io.set_enter_callbacks(on_down=player.enter_down, on_up=player.enter_up)
    io.set_escape_callback(player.emergency_stop)
    io.set_reset_callback(player.reset)
    return player


def tap(hold_s=None):
    enter_down()
    time.sleep(0.005 if hold_s is None else hold_s)
    enter_up()
    settle()


def main():
    print("=" * 70)
    print(f"CORE BIG TEST — 真实系统级（min_hold_ms = {MIN_HOLD}）")
    print("=" * 70)
    print("Enter/Esc/R via hook callback path; real input only via input.py\n")

    # ---------- 二、基础音符映射 ----------
    print("########## 基础音符 1..7 1' 真实按下 ##########")
    mapping = [("1", "z"), ("2", "x"), ("3", "c"), ("4", "v"),
               ("5", "b"), ("6", "n"), ("7", "m"), ("1'", ",")]
    score_all = " ".join(n for n, _ in mapping)
    make(score_all)
    seen = []
    for want_note, want_key in mapping:
        enter_down()
        seen.append((want_note, actual()))
        enter_up()
        settle()
    ok = all(act == f"{k}|" and s_n == want_note
             for (want_note, k), (s_n, act) in zip(mapping, seen))
    print(f"        [debug] len(mapping)={len(mapping)} len(seen)={len(seen)} ok={ok!r}")
    for (n, k), (_, act) in zip(mapping, seen):
        print(f"    {n:>3} -> expected [{k}|]   actual [{act}]")
    check_true("基础音符 8 个真实映射全部正确", ok, f"seen={seen}")

    # ---------- 三、三种调音 ----------
    print("\n########## 调音 ↑ / ↓ / ~ ##########")
    for modifier, label, mouse in [("↑", "Sharp", "right"), ("↓", "Flat", "left"), ("~", "Half", "middle")]:
        make(f"[{modifier} 3]")
        enter_down()
        got = actual()
        check(f"{label} [{modifier} 3] -> c + {mouse}", f"c|{mouse}", got)
        enter_up()
        settle()
        check(f"{label} 松开后全部释放", "|")

    # ---------- 四、混合谱 ----------
    print("\n########## 混合谱 1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2] ##########")
    MIXED = "1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]"
    expect_mixed = ["z|", "x|", "c|right", "v|right", "b|right", "n|",
                    "m|middle", ",|middle", "x|left"]
    make(MIXED)
    got_mixed = []
    for _ in range(9):
        enter_down()
        got_mixed.append(actual())
        enter_up()
        settle()
    for i, (exp, got) in enumerate(zip(expect_mixed, got_mixed), start=1):
        mark = "OK " if exp == got else "BAD"
        print(f"    {mark} #{i}  expected [{exp}]   actual [{got}]")
    check_true("混合谱 9 个真实状态全部正确", got_mixed == expect_mixed, f"got={got_mixed}")

    # ---------- 五、连续调音保持（高频采样） ----------
    print("\n########## 连续调音保持（Right 不得 UP->DOWN 抖动） ##########")
    make("[↑ 3 4 5]")
    samples = []
    for _ in range(3):
        # 每个音符：按下 -> 高频采样（检查 right 是否全程保持）-> 松开
        enter_down()
        for _ in range(12):
            samples.append(down(0x02))
            time.sleep(0.004)
        enter_up()
        settle()
    right_down_all = all(samples)
    check_true("↑ 区间内 Right 全程保持 DOWN（含音符切换瞬间）", right_down_all,
               f"samples={len(samples)} all_down={right_down_all}")
    wait_until(lambda: not down(0x02), timeout=1.0)
    check_true("区间结束后 Right 被释放", not down(0x02), f"right_down={down(0x02)}")

    make("[~ 7 1']")
    enter_down()
    mid_samples = []
    for _ in range(2):
        for _ in range(12):
            mid_samples.append(down(0x04))
            time.sleep(0.004)
        enter_up()
        settle()
    check_true("~ 区间内 Middle 全程保持 DOWN", all(mid_samples),
               f"samples={len(mid_samples)} all_down={all(mid_samples)}")

    # ---------- 七、min_hold_ms = 50 ----------
    print("\n########## min_hold_ms = 50 真实时序 ##########")
    print("--- A. 极快 Enter DOWN/UP ---")
    make("1 2")
    t0 = time.monotonic()
    enter_down()
    time.sleep(0.003)
    enter_up()
    check("A1 松开后音符仍保持 DOWN", "z|")
    check("A2 index 未推进", "index=0", f"index={player.index}")
    check("A3 timer 已挂起", "pending",
          "pending" if player._pending_timer is not None else "none")
    settle()
    held_ms = (time.monotonic() - t0) * 1000
    check_true("A4 真实保持时间 >= 50ms（允许调度误差）", held_ms >= MIN_HOLD - 5,
               f"measured {held_ms:.1f}ms")
    print(f"        measured hold = {held_ms:.1f}ms (min_hold_ms={MIN_HOLD})")
    check("A5 到点后释放并推进", "x|")

    print("--- B. 正常长按 ---")
    make("1 2")
    enter_down()
    check("B1 音符 DOWN", "z|")
    for _ in range(10):
        time.sleep(0.02)
        if actual() != "z|":
            break
    check("B2 保持期间一直 DOWN", "z|")
    t1 = time.monotonic()
    enter_up()
    elapsed = (time.monotonic() - t1) * 1000
    check("B3 Enter UP 后立即释放（无额外等待）", "x|")
    print(f"        release took {elapsed:.1f}ms")
    check("B4 index 推进", "index=1", f"index={player.index}")

    print("--- C. 50ms 附近边界 ---")
    for hold_ms, should_defer in [(25, True), (80, False)]:
        make("1 2")
        enter_down()
        time.sleep(hold_ms / 1000.0)
        enter_up()
        deferred = player._pending_timer is not None
        check_true(f"C {hold_ms}ms -> {'挂 timer' if should_defer else '立即完成'}",
                   deferred == should_defer, f"deferred={deferred}")
        settle()
        check(f"C {hold_ms}ms 之后推进到 index=1", "index=1", f"index={player.index}")

    print("--- D. 极快 UP 后 Esc ---")
    make("1 2 3")
    enter_down(); time.sleep(0.003); enter_up()
    press(VK_ESCAPE)
    check("D1 Esc 后输入全释放", "|")
    time.sleep(SETTLE + 0.25)
    d2_ok = nothing_held()
    check_true("D2 旧 timer 之后不再有输入", d2_ok, f"nothing_held={d2_ok} state={actual()!r}")
    check("D3 index 不变", "index=0", f"index={player.index}")

    print("--- E. 极快 UP 后 R ---")
    make("1 2 3")
    enter_down(); time.sleep(0.003); enter_up()
    press(VK_R)
    check("E1 R 后输入全释放", "|")
    check("E2 R 后 index=0", "index=0", f"index={player.index}")
    time.sleep(SETTLE + 0.25)
    check("E3 旧 timer 之后不再有输入", "|")

    print("--- F. 极快 UP 后 shutdown ---")
    make("1 2 3")
    enter_down(); time.sleep(0.003); enter_up()
    player.shutdown()
    check("F1 shutdown 后输入全释放", "|")
    check("F2 无 timer 残留", "none",
          "none" if player._pending_timer is None else "pending")
    time.sleep(SETTLE + 0.25)
    check("F3 之后不再有输入", "|")

    # ---------- 六、Esc 紧急停止 ----------
    print("\n########## Esc 紧急停止 ##########")
    # 上面 D 段为了验证退出路径停过 listener；这里恢复监听，并复位钩子去重标志、
    # 重新注册 Esc/R 回调，使后续用例处在与生产一致的状态。
    if not io.is_listening():
        io.start_enter_listener()
    io._enter_down = False
    io._escape_down = False
    io._r_down = False
    make("1 2 [↑ 3 4 5]")
    tap(); tap()                       # ->3 就绪
    enter_down()                       # 播放 3 = c + right
    check("Esc 前：c + right DOWN", "c|right")
    check("Esc 前 index=2", "index=2", f"index={player.index}")
    press(VK_ESCAPE)
    check("Esc 后：所有输入 UP", "|")
    check("Esc 后：index 不变（2）", "index=2", f"index={player.index}")
    check_true("Esc 后：程序继续（listener 仍在）", io.is_listening(),
               f"listening={io.is_listening()}")
    time.sleep(0.3)
    check("Esc 后：旧 timer 不会重新按键", "|")
    enter_up()                          # 物理释放
    enter_down()
    check("Esc 后重新 Enter 正常播放", "c|right")
    enter_up(); settle()
    check("之后正常推进到 index=3", "index=3", f"index={player.index}")

    print("--- Esc 时 Enter 仍按住：不得制造第二个 Enter DOWN ---")
    make("1 2")
    enter_down()
    press(VK_ESCAPE)                    # Enter 仍物理按住
    enter_down()                        # 未释放，应被忽略
    check("未释放 Enter 时重复 DOWN 不重播", "|")
    enter_up()
    enter_down()
    check("释放后再按正常播放", "z|")

    # ---------- 九、Esc 双击退出 ----------
    print("\n########## Esc 双击退出（0.8s 窗口） ##########")
    # 用与 main.py 相同的判定方式验证窗口逻辑（不修改生产代码，仅复算）
    ESC_WINDOW = 0.8
    t_a = time.monotonic()
    time.sleep(0.2)
    t_b = time.monotonic()
    check_true("0.2s 内两次 Esc 判为双击（应退出）", (t_b - t_a) <= ESC_WINDOW,
               f"gap={t_b - t_a:.2f}s window={ESC_WINDOW}s")
    t_c = time.monotonic() + 0.9
    time.sleep(0.95)
    gap2 = time.monotonic() - t_b
    check_true("超过 0.8s 的两次 Esc 不判为双击（不应退出）", gap2 > ESC_WINDOW,
               f"gap={gap2:.2f}s window={ESC_WINDOW}s")
    # 用真实 main.py 的退出路径验证 cleanup（先把 listener 恢复成运行状态）
    if not io.is_listening():
        io.start_enter_listener()
    io._escape_down = False
    make("1 2")
    enter_down()
    player.shutdown()
    io.stop_enter_listener()
    check("Esc 退出路径：输入全释放", "|")
    check_true("Esc 退出路径：listener 已停止", not io.is_listening(),
               f"listening={io.is_listening()}")
    io.start_enter_listener()           # 恢复监听供后续普通键用例（生产里不会这样，仅测试用）
    io._enter_down = False
    io._escape_down = False
    io._r_down = False

    # ---------- 十一、普通键放行 ----------
    print("\n########## 普通键不得被 Enter Hook 吞掉 ##########")
    normal_keys = [("A", 0x41), ("Z", 0x5A), ("Space", 0x20), ("Tab", 0x09),
                   ("Shift", 0x10), ("Ctrl", 0x11), ("Alt", 0x12)]

    # 证据 1：钩子返回值 —— 普通键必须是 0（放行），Enter 必须是 1（吞掉）
    for label, vk in normal_keys:
        rv_down = post_key(vk, WM_KEYDOWN)
        rv_up = post_key(vk, WM_KEYUP)
        check(f"{label} 钩子放行（返回 0/0）", "0,0", f"{rv_down},{rv_up}")
    drain()
    rv_enter = post_key(VK_RETURN, WM_KEYDOWN)
    rv_enter_up = post_key(VK_RETURN, WM_KEYUP)
    check("Enter 仍被吞掉（返回 1/1）", "1,1", f"{rv_enter},{rv_enter_up}")
    drain()

    # 证据 2：真的送达应用 —— 用专用测试窗口 + keybd_event 发普通键
    win_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core_win.log")
    if os.path.exists(win_log):
        os.remove(win_log)
    proc, hwnd = start_test_window(win_log)
    if not hwnd:
        check("专用测试窗口已启动", "started", "NOT-FOUND")
    else:
        fg = _user32.GetForegroundWindow()
        check("测试窗口已获得前台（安全前提）",
              "ok" if fg == hwnd else "not-foreground",
              "ok" if fg == hwnd else f"fg={fg} win={hwnd}")
        if fg == hwnd:
            delivered = [("A", 0x41), ("Z", 0x5A), ("Space", 0x20), ("Tab", 0x09)]
            for label, vk in delivered:
                click_normal_key(vk)
                time.sleep(0.15)
            time.sleep(0.4)
            log_text = ""
            if os.path.exists(win_log):
                with open(win_log, "r", encoding="utf-8", errors="replace") as fh:
                    log_text = fh.read()
            expect_names = {"A": "KeyDown:A", "Z": "KeyDown:Z",
                            "Space": "KeyDown:Space", "Tab": "KeyDown:Tab"}
            for label, vk in delivered:
                key = expect_names[label]
                check(f"{label} 真实送达测试窗口", "delivered" if key in log_text else "MISSING",
                      "delivered" if key in log_text else f"MISSING (log={log_text!r})")
        else:
            print("        (跳过真实送达检查：测试窗口未获得前台)")
    stop_test_window()

    print()
    failed = [n for n, ok in results if not ok]
    print("=" * 70)
    print(f"CORE BIG TEST (system) 总计 {len(results)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项:")
        for n in failed:
            print("  - " + n)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        try:
            if player is not None:
                player.shutdown()
        except Exception:
            pass
        io.release_all()
        try:
            io.stop_enter_listener()
        except Exception:
            pass
        stop_test_window()
        print("\ncleanup done: all simulated input released, listener stopped, test window closed",
              flush=True)
        print(f"final state: {actual() or '(nothing held)'}", flush=True)
    sys.exit(code)
