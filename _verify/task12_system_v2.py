"""Task 12 真实系统级测试：min_hold_ms 在真实输入上的行为。

安全设计（沿用已验证的模式）：
    - 单个 Python 进程，顶层 try/finally 保证任何情况下都 release_all()，绝不留卡键
    - Enter 通过 input.py 的钩子回调正式路径投递（不用 keybd_event/SendInput）
    - 真实输入只来自 PlaybackExecutor -> input.py
    - 状态用只读 GetAsyncKeyState 校验
    - 用 time.monotonic() 量测真实保持时间

两个等待辅助函数语义不同，不要混用：
    wait_settled()  等"延迟完成已经落地"（timer 结束）。完成后下一个音符是**就绪并按住**的。
    wait_empty()    等"没有任何键按住"（只在真正应该全空的场景使用）。
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import input as io  # noqa: E402
from harmonica_app import FixedScorePlayer, load_min_hold_ms  # noqa: E402
from input import KBDLLHOOKSTRUCT  # noqa: E402
from score import parse_score_notes  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK_RETURN = 0x0D

KEY_VKS = {"z": 0x5A, "x": 0x58, "c": 0x43, "v": 0x56, "b": 0x42,
           "n": 0x4E, "m": 0x4D, ",": 0xBC}
MOUSE_VKS = {"left": 0x01, "right": 0x02, "middle": 0x04}
_keep = {}
results = []
player = None


def down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def actual():
    keys = "+".join(sorted(n for n, vk in KEY_VKS.items() if down(vk))) or ""
    buttons = "/".join(sorted(n for n, vk in MOUSE_VKS.items() if down(vk))) or ""
    return f"{keys}|{buttons}"


def check(name, expected, actual_value=None):
    got = actual() if actual_value is None else actual_value
    ok = expected == got
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}   expected=[{expected}] actual=[{got}]")


def post_key(vk, message):
    info = KBDLLHOOKSTRUCT()
    info.vkCode = vk
    info.scanCode = 0
    info.flags = 0
    info.time = 0
    info.dwExtraInfo = 0
    _keep["i"] = info
    io._hook_callback(0, message, ctypes.cast(ctypes.pointer(info), ctypes.c_void_p).value)


def drain():
    for _ in range(100):
        if io._drain_callbacks(timeout=0.5):
            return
        time.sleep(0.005)


def enter_down():
    post_key(VK_RETURN, WM_KEYDOWN)
    drain()


def enter_up():
    post_key(VK_RETURN, WM_KEYUP)
    drain()


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.003)
    return False


def wait_settled(timeout=2.0):
    """等到没有挂起的 timer（延迟完成落地）。之后下一个音符是就绪并按住的。"""
    ok = wait_until(lambda: player is not None and player._pending_timer is None, timeout)
    time.sleep(0.01)
    return ok


def wait_empty(timeout=2.0):
    """等到没有任何键按住。"""
    return wait_until(lambda: player is not None and player._pending_timer is None and actual() == "",
                      timeout)


def make(score_text, min_hold_ms):
    """干净地开一段新测试：先释放上一段留下的任何输入。"""
    global player
    if player is not None:
        player.shutdown()
    io.release_all()
    io._enter_down = False
    wait_until(lambda: actual() == "", timeout=1.0)
    player = FixedScorePlayer(parse_score_notes(score_text), min_hold_ms=min_hold_ms)
    io.set_enter_callbacks(on_down=player.enter_down, on_up=player.enter_up)
    return player


def main():
    print("================ Task 12 real system-level test ================")
    print(f"config.json min_hold_ms = {load_min_hold_ms()}")
    print("real input only via PlaybackExecutor -> input.py; Enter via the hook callback path")
    print("no keybd_event / SendInput / mouse_event is used\n")

    # ---------- A. 正常长按 ----------
    print("=== A. normal long hold (held longer than min_hold_ms) ===")
    make("1 2", 80)
    enter_down()
    check("A1 Enter DOWN -> Z down", "z|")
    time.sleep(0.12)                       # 超过 min_hold_ms
    enter_up()
    check("A2 after UP: all released (Task 27A)", "|")
    check("A3 index == 1", "index=1", f"index={player.index}")
    check("A4 no pending timer (immediate completion)",
          "none", "none" if player._pending_timer is None else "pending")

    # ---------- B. 快速点击：必须至少保持 min_hold_ms ----------
    print("\n=== B. short tap (held ~10ms, must last min_hold_ms) ===")
    make("1 2", 120)
    t_down = time.monotonic()
    enter_down()
    time.sleep(0.01)
    enter_up()
    check("B1 after UP the note is still held", "z|")
    check("B2 index not advanced yet", "index=0", f"index={player.index}")
    settled = wait_settled()
    t_settled = time.monotonic()
    held_ms = (t_settled - t_down) * 1000
    check("B3 timer completed and advanced", "index=1", f"index={player.index}")
    check("B4 the note was held about min_hold_ms (120ms, +-70ms)",
          "in-range" if 50 <= held_ms <= 190 else "out-of-range",
          "in-range" if 50 <= held_ms <= 190 else f"out-of-range {held_ms:.0f}ms")
    print(f"        (settled={settled}, measured hold = {held_ms:.0f}ms, min_hold_ms=120)")
    player.shutdown()
    wait_empty()

    # ---------- C. 连续四次快速敲击 1 2 3 4 ----------
    print("\n=== C. four fast taps on 1 2 3 4 ===")
    make("1 2 3 4", 60)
    expected = ["z|", "x|", "c|", "v|"]
    seen = []
    for i, want in enumerate(expected):
        enter_down()
        time.sleep(0.008)
        seen.append(actual())
        enter_up()
        wait_settled()
    check("C1 each note pressed in order (z,x,c,v)",
          "all-pass" if seen == expected else "mismatch",
          "all-pass" if seen == expected else f"mismatch {seen}")
    check("C2 index reached 4 exactly (no double advance, no skip)", "index=4",
          f"index={player.index}")
    wait_empty()
    check("C3 nothing left held", "|")

    # ---------- D. 快速调音音符 [↑ 3 4 5] ----------
    print("\n=== D. fast tuned notes [^ 3 4 5] ===")
    make("[↑ 3 4 5]", 70)
    seen_d = []
    for _ in range(3):
        enter_down()
        time.sleep(0.008)
        seen_d.append(actual())
        enter_up()
        wait_settled()
    check("D1 all three notes had c/v/b with right held",
          "all-pass" if all(s in ("c|right", "v|right", "b|right") for s in seen_d) else "mismatch",
          "all-pass" if all(s in ("c|right", "v|right", "b|right") for s in seen_d) else f"mismatch {seen_d}")
    check("D2 index == 3", "index=3", f"index={player.index}")
    wait_empty()
    check("D3 right released at the end of the range, nothing left", "|")

    # ---------- E. shutdown 取消挂起的 timer ----------
    print("\n=== E. shutdown while a timer is pending ===")
    make("1 2 3", 400)
    enter_down()
    time.sleep(0.01)
    enter_up()
    check("E1 note still held (timer pending)", "z|")
    check("E2 a timer really is pending",
          "pending", "pending" if player._pending_timer is not None else "none")
    player.shutdown()
    check("E3 shutdown releases everything immediately", "|")
    time.sleep(0.5)                        # 等过旧 timer 该到点的时刻
    check("E4 old timer never produces any input afterwards", "|")
    check("E5 index untouched by the old timer", "index=0", f"index={player.index}")

    # ---------- F. 播放结束 ----------
    print("\n=== F. after the score is finished ===")
    make("1", 60)
    enter_down()
    time.sleep(0.008)
    enter_up()
    wait_settled()
    wait_empty()
    check("F1 finished, everything released", "|")
    check("F2 index == 1", "index=1", f"index={player.index}")
    enter_down()
    check("F3 Enter after finish produces no input", "|")
    enter_up()
    check("F4 still nothing held", "|")

    # ---------- G. 长按期间的重复 DOWN ----------
    print("\n=== G. repeated Enter DOWN (auto-repeat) ===")
    make("1 2", 80)
    enter_down()
    for _ in range(10):
        enter_down()
    check("G1 repeated DOWN keeps the same note held", "z|")
    check("G2 index not advanced", "index=0", f"index={player.index}")
    time.sleep(0.12)
    enter_up()
    check("G3 after UP: all released (Task 27A)", "|")
    check("G4 index == 1", "index=1", f"index={player.index}")

    # ---------- H. 用 config.json 的真实值 ----------
    print("\n=== H. with the real config.json min_hold_ms ===")
    cfg = load_min_hold_ms()
    make("1 2", cfg)
    enter_down()
    time.sleep(0.005)                      # 远小于配置值
    enter_up()
    check("H1 short tap still held (config value in effect)", "z|")
    ok = wait_settled()
    check("H2 advanced after the configured hold time", "index=1", f"index={player.index}")
    print(f"        (settled={ok}, config min_hold_ms={cfg})")

    print()
    failed = [name for name, ok in results if not ok]
    print(f"total {len(results)} checks, failed {len(failed)}")
    if failed:
        print("failed:")
        for name in failed:
            print("  - " + name)
        return 1
    print("ALL PASS")
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
        print("\ncleanup done: all simulated input released", flush=True)
        print(f"final state: {actual() or '(nothing held)'}", flush=True)
    sys.exit(code)
