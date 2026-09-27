"""Task 13 真实系统级测试：Esc / R / shutdown 的真实输入释放。

安全设计：
    - 单个 Python 进程，顶层 try/finally 保证任何情况下都 release_all()，绝不留卡键
    - Enter / Esc / R 都通过 input.py 的钩子回调正式路径投递（不用 keybd_event 发按键）
    - 真实输入只来自 PlaybackExecutor -> input.py
    - 状态用只读 GetAsyncKeyState 校验
    - 使用最终 config.json 的真实 min_hold_ms（不是 0）
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
VK_RETURN, VK_ESCAPE, VK_R = 0x0D, 0x1B, 0x52

KEY_VKS = {"z": 0x5A, "x": 0x58, "c": 0x43, "v": 0x56, "b": 0x42,
           "n": 0x4E, "m": 0x4D, ",": 0xBC}
MOUSE_VKS = {"left": 0x01, "right": 0x02, "middle": 0x04}
_keep = {}
results = []
player = None
MIN_HOLD = load_min_hold_ms()
HOLD_WAIT = MIN_HOLD / 1000.0 + 0.12


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


def press(vk):
    post_key(vk, WM_KEYDOWN)
    drain()
    post_key(vk, WM_KEYUP)
    drain()


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
    ok = wait_until(lambda: player is not None and player._pending_timer is None, timeout)
    time.sleep(0.01)
    return ok


def wait_empty(timeout=2.0):
    return wait_until(lambda: player is not None and actual() == "", timeout)


def make(score_text):
    global player
    if player is not None:
        player.shutdown()
    io.release_all()
    io._enter_down = False
    io._escape_down = False
    io._r_down = False
    wait_until(lambda: actual() == "", timeout=1.0)
    player = FixedScorePlayer(parse_score_notes(score_text), min_hold_ms=MIN_HOLD)
    io.set_enter_callbacks(on_down=player.enter_down, on_up=player.enter_up)
    io.set_escape_callback(player.emergency_stop)
    io.set_reset_callback(player.reset)
    return player


def main():
    print("================ Task 13 real system-level test ================")
    print(f"config.json min_hold_ms = {MIN_HOLD}")
    print("Enter/Esc/R go through the hook callback path; real input only via input.py")
    print("no keybd_event / SendInput / mouse_event is used to send keys\n")

    # ---------- A. Esc 紧急停止（正在播放时） ----------
    print("=== A. Esc emergency stop while a note is playing ===")
    make("1 2 [↑ 3 4 5]")
    enter_down(); enter_up(); wait_settled()      # 1 -> 2
    enter_down(); enter_up(); wait_settled()      # 2 -> 3 就绪
    enter_down()                                  # 播放 3 = C + right
    check("A1 playing note 3 -> C + Right down", "c|right")
    check("A2 index == 2", "index=2", f"index={player.index}")
    press(VK_ESCAPE)
    wait_empty()
    check("A3 after Esc: C released", "|")
    check("A4 after Esc: index unchanged (2)", "index=2", f"index={player.index}")
    check("A5 after Esc: no pending timer", "none",
          "none" if player._pending_timer is None else "pending")
    time.sleep(0.3)
    check("A6 old timer never re-pressed anything", "|")

    # ---------- B. Esc 后可重新开始 ----------
    print("\n=== B. restart after Esc ===")
    enter_up()                                    # 真实操作：松开 Enter
    enter_down()
    check("B1 Enter after Esc replays the current note (C+Right)", "c|right")
    enter_up()
    wait_settled()
    check("B2 advanced normally to index 3", "index=3", f"index={player.index}")

    # ---------- C. R 重置 ----------
    print("\n=== C. R reset ===")
    make("1 2 3 4")
    enter_down(); enter_up(); wait_settled()
    enter_down(); enter_up(); wait_settled()      # -> 3
    enter_down()
    check("C1 playing note 3 -> C down", "c|")
    check("C2 index == 2", "index=2", f"index={player.index}")
    press(VK_R)
    wait_empty()
    check("C3 after R: everything released", "|")
    check("C4 after R: index == 0", "index=0", f"index={player.index}")
    check("C5 after R: current note is 1", "note=1",
          f"note={player.current_note().note}" if player.current_note() else "note=None")
    enter_up()                                    # 真实操作：松开 Enter
    enter_down()
    check("C6 Enter after R starts from note 1 (Z)", "z|")
    enter_up()
    wait_settled()
    check("C7 advanced to index 1", "index=1", f"index={player.index}")

    # ---------- D. timer race：快速 UP（timer pending）-> Esc ----------
    print("\n=== D. race: short tap (timer pending) then Esc ===")
    make("1 2 3")
    enter_down()
    time.sleep(0.005)
    enter_up()                                    # timer pending
    check("D1 note still held, timer pending", "z|")
    check("D2 timer really pending", "pending",
          "pending" if player._pending_timer is not None else "none")
    press(VK_ESCAPE)
    wait_empty()
    check("D3 after Esc: released", "|")
    time.sleep(MIN_HOLD / 1000.0 + 0.25)          # 等过旧 timer 该到点的时刻
    check("D4 old timer never re-pressed anything", "|")
    check("D5 index untouched by old timer", "index=0", f"index={player.index}")

    # ---------- E. timer race：快速 UP -> R ----------
    print("\n=== E. race: short tap (timer pending) then R ===")
    make("1 2 3")
    enter_down(); time.sleep(0.005); enter_up()
    press(VK_R)
    wait_empty()
    check("E1 after R: released, index 0", "index=0", f"index={player.index}")
    check("E2 nothing held", "|")
    time.sleep(MIN_HOLD / 1000.0 + 0.25)
    check("E3 old timer never re-pressed anything", "|")
    check("E4 index still 0", "index=0", f"index={player.index}")

    # ---------- F. 连续 Esc / 连续 R ----------
    print("\n=== F. repeated Esc and repeated R ===")
    make("1 2 [↑ 3 4 5]")
    enter_down()
    ok = True
    try:
        for _ in range(3):
            press(VK_ESCAPE)
    except Exception as exc:  # noqa: BLE001
        ok = False
        print("        raised:", repr(exc))
    wait_empty()
    check("F1 three Esc presses do not raise", "ok", "ok" if ok else "raised")
    check("F2 nothing held after three Esc", "|")
    ok = True
    try:
        for _ in range(3):
            press(VK_R)
    except Exception as exc:  # noqa: BLE001
        ok = False
        print("        raised:", repr(exc))
    wait_empty()
    check("F3 three R presses do not raise", "ok", "ok" if ok else "raised")
    check("F4 nothing held after three R", "|")
    check("F5 index == 0 after R", "index=0", f"index={player.index}")

    # ---------- G. shutdown 清理（按住 + timer pending） ----------
    print("\n=== G. shutdown while input is held ===")
    make("1 2 [↑ 3 4 5]")
    enter_down()
    time.sleep(0.005)
    enter_up()                                    # timer pending
    enter_down()                                  # 再次按住
    check("G1 something is held before shutdown", "held",
          "held" if actual() != "" else "nothing")
    player.shutdown()
    wait_empty()
    check("G2 after shutdown: everything released", "|")
    check("G3 after shutdown: no pending timer", "none",
          "none" if player._pending_timer is None else "pending")
    time.sleep(MIN_HOLD / 1000.0 + 0.25)
    check("G4 nothing appears after shutdown", "|")

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
