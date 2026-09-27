"""Task 11 真实系统级测试（自包含、防卡键）。

设计要点（针对前两次卡死）：
    - 单个 Python 进程，自己驱动 Enter（通过 input.py 的钩子回调正式路径），
      不经过 PowerShell 管道，因此没有管道死锁、不会被中途打断在"按键中途"
    - 顶层 try/finally 保证任何异常/中断都会 release_all()
    - 真实输入只来自 PlaybackExecutor -> input.py
    - 每个断言都读 GetAsyncKeyState 做只读校验
    - 不使用 keybd_event / SendInput 发送 Enter 或音符键
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import input as io  # noqa: E402
from harmonica_app import FixedScorePlayer  # noqa: E402
from input import KBDLLHOOKSTRUCT  # noqa: E402
from score import parse_score_notes  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK_RETURN = 0x0D

KEY_VKS = {"z": 0x5A, "x": 0x58, "c": 0x43, "v": 0x56, "b": 0x42,
           "n": 0x4E, "m": 0x4D, ",": 0xBC}
MOUSE_VKS = {"left": 0x01, "right": 0x02, "middle": 0x04}

_keep_alive = {}
results = []


def down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def actual_state():
    keys = "+".join(sorted(n for n, vk in KEY_VKS.items() if down(vk))) or ""
    buttons = "/".join(sorted(n for n, vk in MOUSE_VKS.items() if down(vk))) or ""
    return f"{keys}|{buttons}"


def check(name, expected, actual=None):
    got = actual_state() if actual is None else actual
    ok = expected == got
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}   expected=[{expected}] actual=[{got}]")


def post_key(vk, message):
    """通过 input.py 的低级键盘钩子回调正式路径投递一次按键事件。"""
    info = KBDLLHOOKSTRUCT()
    info.vkCode = vk
    info.scanCode = 0
    info.flags = 0
    info.time = 0
    info.dwExtraInfo = 0
    _keep_alive["info"] = info
    addr = ctypes.cast(ctypes.pointer(info), ctypes.c_void_p).value
    io._hook_callback(0, message, addr)


def drain():
    for _ in range(100):
        if io._drain_callbacks(timeout=0.5):
            return
        time.sleep(0.01)


def enter_down():
    post_key(VK_RETURN, WM_KEYDOWN)
    drain()


def enter_up():
    post_key(VK_RETURN, WM_KEYUP)
    drain()


player = None


def load(score_text):
    global player
    if player is not None:
        player.shutdown()
    # This self-test invokes the hook callback directly instead of physically
    # pressing Enter.  A prior run may deliberately end after a synthetic
    # KEYDOWN, so reset that synthetic hook state before replacing the player.
    # In normal use a physical KEYUP performs this transition.
    io._enter_down = False
    notes = parse_score_notes(score_text)
    # Task 12 给 FixedScorePlayer 加了默认 min_hold_ms=50。本文件是 Task 11 的回归测试，
    # 它验证的是"Enter UP 后立即推进"的同步语义，并且断言紧随 enter_up() 之后读取状态，
    # 所以这里显式关闭 min_hold_ms（=0），保持 Task 11 的行为契约。
    # Task 12 的 min_hold_ms 行为由 _verify\task12_logic.py / task12_system_selftest.py 覆盖。
    player = FixedScorePlayer(notes, min_hold_ms=0)
    io.set_enter_callbacks(on_down=player.enter_down, on_up=player.enter_up)
    return notes


def run(score_text, actions):
    """载入琴谱并执行一串动作：'d' = Enter DOWN，'u' = Enter UP。"""
    load(score_text)
    for action in actions:
        if action == "d":
            enter_down()
        elif action == "u":
            enter_up()
    return player.index


def main():
    print("================ Task 11 real system-level test ================")
    print("all input goes through PlaybackExecutor -> input.py; Enter via the hook callback path")
    print("no keybd_event / SendInput is used to send Enter or note keys\n")

    # ---------- A. single note ----------
    print("=== A. single note ===")
    run("1", "d")
    check("A1 Enter DOWN -> Z DOWN", "z|")
    run("1", "du")
    check("A2 Enter UP -> Z UP", "|")
    check("A3 index == 1", "index=1", f"index={player.index}")

    # ---------- B. consecutive notes ----------
    print("\n=== B. consecutive 1 2 3 ===")
    run("1 2 3", "d")
    check("B1 note1 -> Z", "z|")
    run("1 2 3", "du")
    check("B2 after UP: all released (Task 27A)", "|")
    run("1 2 3", "dud")
    check("B3 note2 -> X (pressed by the next DOWN)", "x|")
    run("1 2 3", "dudu")
    check("B4 after UP: all released", "|")
    run("1 2 3", "dudud")
    check("B5 note3 -> C", "c|")
    idx = run("1 2 3", "dududu")
    check("B6 finished, all released", "|")
    check("B7 index == 3", "index=3", f"index={idx}")

    # ---------- C. hold Enter with repeated DOWN ----------
    print("\n=== C. hold Enter (repeated DOWN events) ===")
    run("1", "d")
    check("C1 after DOWN -> Z DOWN", "z|")
    for _ in range(15):
        enter_down()          # 模拟长按期间的自动重复
    check("C2 after 15 repeated DOWNs: still only Z DOWN", "z|")
    check("C3 index still 0", "index=0", f"index={player.index}")
    enter_up()
    check("C4 after release: all up", "|")

    # ---------- D. tuning ----------
    print("\n=== D. tuning [↑ 3] ===")
    run("[↑ 3]", "d")
    check("D1 Enter DOWN -> C + Right DOWN", "c|right")
    run("[↑ 3]", "du")
    check("D2 Enter UP -> C + Right all UP", "|")

    # ---------- E. tuning run ----------
    print("\n=== E. tuning run [↑ 3 4 5] ===")
    run("[↑ 3 4 5]", "d")
    check("E1 3 -> C+right", "c|right")
    run("[↑ 3 4 5]", "du")
    check("E2 after UP: all released (Task 27A, right no longer kept)", "|")
    run("[↑ 3 4 5]", "dud")
    check("E3 4 -> V+right", "v|right")
    run("[↑ 3 4 5]", "dudu")
    check("E4 after UP: all released", "|")
    run("[↑ 3 4 5]", "dudud")
    check("E5 5 -> B+right", "b|right")
    run("[↑ 3 4 5]", "dududu")
    check("E6 range over -> all released", "|")

    # ---------- F. mixed score ----------
    print("\n=== F. mixed score 1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2] ===")
    score = "1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]"
    steps = [
        (1,  "z|",       "F1  1 normal  -> z"),
        (2,  "|",        "F2  after UP: all released (Task 27A)"),
        (3,  "x|",       "F3  2 normal  -> x"),
        (4,  "|",        "F4  after UP: all released"),
        (5,  "c|right",  "F5  3 sharp   -> c+right"),
        (6,  "|",        "F6  after UP: all released (right not held)"),
        (7,  "v|right",  "F7  4 sharp   -> v+right"),
        (8,  "|",        "F8  after UP: all released"),
        (9,  "b|right",  "F9  5 sharp   -> b+right"),
        (10, "|",        "F10 after UP: all released"),
        (11, "n|",       "F11 6 normal  -> n"),
        (12, "|",        "F12 after UP: all released"),
        (13, "m|middle", "F13 7 half    -> m+middle"),
        (14, "|",        "F14 after UP: all released"),
        (15, ",|middle", "F15 1' half   -> comma+middle"),
        (16, "|",        "F16 after UP: all released"),
        (17, "x|left",   "F17 2 flat    -> x+left"),
        (18, "|",        "F18 finished, all released"),
    ]
    for n, expected, label in steps:
        # Each row is the state after exactly n alternating hook events:
        # d, du, dud, dudu, ... .  The previous construction made 2*n-1
        # events (and an extra UP for row 18), which tested the wrong note.
        actions = "du" * (n // 2) + ("d" if n % 2 else "")
        run(score, actions)
        check(label, expected)

    # ---------- G. after finished ----------
    print("\n=== G. after the score is finished ===")
    full = []
    for i in range(1, 19):
        full.append("d")
        full.append("u")
    run(score, "".join(full))
    check("G1 finished state: all released", "|")
    idx = run(score, "".join(full) + "du")
    check("G2 extra Enter after finish produces no input", "|")
    check("G3 index stays == 9", "index=9", f"index={idx}")

    # ---------- I. repeated DOWN / UP ----------
    print("\n=== I. repeated DOWN / UP ===")
    run("1 2 3", "d")
    for _ in range(4):
        enter_down()
    check("I1 four repeated DOWNs: only Z down", "z|")
    check("I2 index still 0", "index=0", f"index={player.index}")
    enter_up()
    check("I3 after UP: all released (Task 27A)", "|")
    for _ in range(4):
        enter_up()
    check("I4 four repeated UPs: still all released", "|")
    check("I5 index == 1", "index=1", f"index={player.index}")
    enter_down()
    check("I6 next Enter DOWN plays note 2", "x|")
    enter_up()
    check("I7 after UP: all released", "|")

    # ---------- H. shutdown releases everything ----------
    print("\n=== H. shutdown while a note is DOWN (Esc path) ===")
    load("[↑ 3] 4")
    enter_down()
    check("H1 before shutdown: C+right DOWN", "c|right")
    player.shutdown()
    check("H2 after shutdown: everything released", "|")

    # H3/H4: play one note to the end of a single-note score.
    run("[↑ 3]", "du")
    check("H3 after the last note is released: everything up", "|")
    check("H4 index == 1 (score finished)", "index=1", f"index={player.index}")

    # H5/H6: inter-note transition.  Task 27A 起 Enter UP 一律释放全部输出，
    # 因此过渡到下一个音符时不再残留任何键（下一个音符由下一次 DOWN 按下）。
    run("[↑ 3] 4", "du")
    check("H5 after UP: everything released (Task 27A)", "|")
    check("H6 index == 1 (advanced, not finished)", "index=1", f"index={player.index}")
    run("[↑ 3] 4", "dud")
    check("H6b next DOWN plays note 2 with its tuning", "v|")
    run("[↑ 3] 4", "dudu")
    check("H7 after the last note ends: everything released", "|")

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
    exit_code = 1
    try:
        exit_code = main()
    finally:
        # 防卡键：无论成功、异常还是被 Ctrl+C 中断，都确保释放所有模拟输入
        try:
            if player is not None:
                player.shutdown()
        except Exception:
            pass
        io.release_all()
        print("\ncleanup done: all simulated input released", flush=True)
        print(f"final state: {actual_state() or '(nothing held)'}", flush=True)
    sys.exit(exit_code)
