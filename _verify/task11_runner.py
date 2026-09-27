"""Task 11 真实系统级测试的协议运行器（通过 Hook 按键路径驱动）。

与生产代码使用同一份接线：harmonica_app.FixedScorePlayer
+ main.py 里同样的 Enter / Esc 回调方式。

Enter 事件通过 io._hook_callback 直接投递（低级键盘钩子的正式回调路径），
不使用 keybd_event / SendInput 模拟 Enter。

协议（stdin）：
    score <text>        重新载入琴谱（用 | 代替空格）
    enter_down          投递一次 Enter 按下事件
    enter_down_n <n>    连续投递 n 次 Enter 按下（测重复 DOWN）
    enter_up            投递一次 Enter 松开事件
    enter_up_n <n>      连续投递 n 次 Enter 松开
    info                打印当前 index / 状态
    quit                收尾释放并退出

每一步之后都用 GetAsyncKeyState 读回真实按键状态打印出来（交叉验证）。
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
VK_RETURN, VK_ESCAPE = 0x0D, 0x1B

KEY_VKS = {
    "z": 0x5A, "x": 0x58, "c": 0x43, "v": 0x56, "b": 0x42,
    "n": 0x4E, "m": 0x4D, ",": 0xBC,
}
MOUSE_VKS = {"left": 0x01, "right": 0x02, "middle": 0x04}

_keep_alive = {}


def down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def snapshot_text():
    keys = "+".join(sorted(n for n, vk in KEY_VKS.items() if down(vk))) or "-"
    buttons = "/".join(sorted(n for n, vk in MOUSE_VKS.items() if down(vk))) or "-"
    enter = "True" if down(VK_RETURN) else "False"
    return f"keys=[{keys}] mouse=[{buttons}] enter={enter}"


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


def wait_callbacks():
    """等钩子回调里的用户回调（在工作线程上执行）跑完。"""
    for _ in range(100):
        if io._drain_callbacks(timeout=0.5):
            return
        time.sleep(0.01)


player = None


def build_player(score_text):
    global player
    notes = parse_score_notes(score_text)
    player = FixedScorePlayer(notes)
    io.set_enter_callbacks(
        on_down=player.enter_down,
        on_up=player.enter_up,
    )
    io.set_escape_callback(on_escape)
    return notes


def on_escape():
    print("Esc pressed -> releasing everything and stopping listener", flush=True)
    player.shutdown()
    io.stop_enter_listener()


def main():
    build_player("1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]")
    print("runner ready (score loaded, hook callback path)", flush=True)

    try:
        run_commands()
    finally:
        # 无论正常结束、异常还是被中断，都必须释放所有模拟输入，绝不留卡键。
        try:
            player.shutdown()
        finally:
            io.release_all()
            print("cleanup done (all simulated input released)", flush=True)


def run_commands():
    for line in sys.stdin:
        parts = line.strip().split()
        if not parts:
            continue
        command = parts[0]

        if command == "score":
            text = " ".join(parts[1:]).replace("|", " ")
            notes = build_player(text)
            print(f"score loaded: {[n.note for n in notes]} -> {snapshot_text()}", flush=True)

        elif command == "enter_down":
            post_key(VK_RETURN, WM_KEYDOWN)
            wait_callbacks()
            print(f"enter_down -> index={player.index} {snapshot_text()}", flush=True)

        elif command == "enter_down_n":
            count = int(parts[1])
            for _ in range(count):
                post_key(VK_RETURN, WM_KEYDOWN)
            wait_callbacks()
            print(f"enter_down_n {count} -> index={player.index} {snapshot_text()}", flush=True)

        elif command == "enter_up":
            post_key(VK_RETURN, WM_KEYUP)
            wait_callbacks()
            print(f"enter_up -> index={player.index} {snapshot_text()}", flush=True)

        elif command == "enter_up_n":
            count = int(parts[1])
            for _ in range(count):
                post_key(VK_RETURN, WM_KEYUP)
            wait_callbacks()
            print(f"enter_up_n {count} -> index={player.index} {snapshot_text()}", flush=True)

        elif command == "info":
            print(f"info -> index={player.index} finished={player.is_finished()} "
                  f"{snapshot_text()}", flush=True)

        elif command == "quit":
            break


if __name__ == "__main__":
    main()
