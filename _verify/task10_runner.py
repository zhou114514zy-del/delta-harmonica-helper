"""Task 10 真实输入测试的"协议运行器"。

从 stdin 读取命令，通过 playback_executor -> input.py 的正式 API 执行真实输入：

    apply <keys> <buttons>
        keys     用 "+" 分隔，"-" 表示空      例: z  z+x  ,  -
        buttons  用 "/" 分隔，"-" 表示空      例: right  left/right  -
        （刻意不用逗号做分隔符，因为 "," 本身就是合法音符键）
    release_all
    quit

每执行一步，用 GetAsyncKeyState 读回真实状态打印出来（交叉验证）。
不使用 keybd_event / SendInput / mouse_event，也不安装任何 Hook、不 import pynput 的 Listener，
真实输入全部来自 input.py 的正式 API。
"""
import sys
import os
import ctypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import input as io  # noqa: E402
from playback import PlaybackState  # noqa: E402
from playback_executor import PlaybackExecutor  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)

KEY_VKS = {
    "z": 0x5A, "x": 0x58, "c": 0x43, "v": 0x56, "b": 0x42,
    "n": 0x4E, "m": 0x4D, ",": 0xBC,
}
MOUSE_VKS = {"left": 0x01, "right": 0x02, "middle": 0x04}

KEY_SEP = "+"
BUTTON_SEP = "/"


def down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def snapshot():
    return (
        {name: down(vk) for name, vk in KEY_VKS.items()},
        {name: down(vk) for name, vk in MOUSE_VKS.items()},
    )


def fmt(keys, buttons):
    k = "+".join(sorted(n for n, v in keys.items() if v)) or "-"
    b = "/".join(sorted(n for n, v in buttons.items() if v)) or "-"
    return f"keys=[{k}] mouse=[{b}]"


def parse_field(field, separator):
    if field in ("-", ""):
        return set()
    return set(field.split(separator))


def main():
    executor = PlaybackExecutor()
    print("runner ready", flush=True)

    for line in sys.stdin:
        parts = line.strip().split()
        if not parts:
            continue
        command = parts[0]

        if command == "apply":
            keys = parse_field(parts[1] if len(parts) > 1 else "-", KEY_SEP)
            buttons = parse_field(parts[2] if len(parts) > 2 else "-", BUTTON_SEP)
            executor.apply(PlaybackState(frozenset(keys), frozenset(buttons)))
            keys_state, buttons_state = snapshot()
            print(f"applied {sorted(keys)} {sorted(buttons)} -> {fmt(keys_state, buttons_state)}", flush=True)

        elif command == "release_all":
            executor.release_all()
            keys_state, buttons_state = snapshot()
            print(f"released_all -> {fmt(keys_state, buttons_state)}", flush=True)

        elif command == "quit":
            executor.release_all()
            keys_state, buttons_state = snapshot()
            print(f"quit -> {fmt(keys_state, buttons_state)}", flush=True)
            break

    # 无论怎么结束，都确保不留卡键
    executor.release_all()
    io.release_all()


if __name__ == "__main__":
    main()
