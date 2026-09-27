"""Task 7 纯逻辑测试：不向系统发送任何真实键盘/鼠标输入。

做法：把 input.py 的键盘/鼠标控制器换成"记录器"，再直接调用钩子回调，
观察逻辑层面的 press/release 行为与 held 状态。
全程不调用 keybd_event / SendInput / mouse_event，也不会真的按下鼠标键。
"""
import ctypes
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import input as io  # noqa: E402
from input import KBDLLHOOKSTRUCT  # noqa: E402
from pynput.mouse import Button  # noqa: E402

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK_RETURN, VK_ESCAPE = 0x0D, 0x1B


class FakeDevice:
    """记录器：代替真实的控制器，不产生任何系统输入。"""

    def __init__(self, label):
        self.label = label
        self.calls = []
        self.lock = threading.Lock()

    def press(self, thing):
        with self.lock:
            self.calls.append(f"{self.label}:press:{io.mouse_button_name(thing) if self.label == 'mouse' else thing}")

    def release(self, thing):
        with self.lock:
            self.calls.append(f"{self.label}:release:{io.mouse_button_name(thing) if self.label == 'mouse' else thing}")

    def snapshot(self):
        with self.lock:
            return list(self.calls)

    def clear(self):
        with self.lock:
            self.calls.clear()


fake_kb = FakeDevice("keyboard")
fake_mouse = FakeDevice("mouse")
io._keyboard = fake_kb
io._mouse = fake_mouse

_keep_alive = {}


def key_event(vk, message):
    info = KBDLLHOOKSTRUCT()
    info.vkCode = vk
    info.scanCode = 0
    info.flags = 0
    info.time = 0
    info.dwExtraInfo = 0
    _keep_alive["info"] = info
    addr = ctypes.cast(ctypes.pointer(info), ctypes.c_void_p).value
    return io._hook_callback(0, message, addr)


def sync():
    while not io._drain_callbacks(timeout=1.0):
        time.sleep(0.01)


def reset():
    sync()
    fake_kb.clear()
    fake_mouse.clear()
    io._enter_down = False
    io._escape_down = False
    io._held_keys.clear()
    io._held_mouse_buttons.clear()


results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}  {name}  {detail}")


# ============ 测试 A（逻辑部分）：三个鼠标键单独按下 / 释放 ============
for name, button in (("left", Button.left), ("middle", Button.middle), ("right", Button.right)):
    reset()
    io.press_mouse(name)
    held_after_press = io.held_mouse_buttons()
    io.release_mouse(name)
    held_after_release = io.held_mouse_buttons()
    calls = fake_mouse.snapshot()
    check(f"A 鼠标 {name} 单独 press/release 正常，held 状态正确变化",
          calls == [f"mouse:press:{name}", f"mouse:release:{name}"]
          and held_after_press == {button} and held_after_release == set(),
          f"calls={calls} held_after_press={held_after_press} held_after_release={held_after_release}")

# 未按住的鼠标键释放时不应抛异常，held 状态保持为空
reset()
no_exception = True
try:
    io.release_mouse("left")
    io.release_mouse("middle")
    io.release_mouse("right")
except Exception as exc:  # noqa: BLE001
    no_exception = False
    print("   release raised:", repr(exc))
check("A 从未按下的鼠标键 release 不抛异常、held 仍为空",
      no_exception and io.held_mouse_buttons() == set(),
      f"no_exception={no_exception} held={io.held_mouse_buttons()}")

# ============ 测试 B/C/D（逻辑部分）：Z + 鼠标键同时按下 / 释放 ============
for name in ("left", "middle", "right"):
    reset()
    io.set_enter_callbacks(
        on_down=lambda n=name: (io.press_mouse(n), io.press_key("z")),
        on_up=lambda n=name: (io.release_mouse(n), io.release_key("z")),
    )
    key_event(VK_RETURN, WM_KEYDOWN)
    sync()
    during_key = fake_kb.snapshot()
    during_mouse = fake_mouse.snapshot()
    held_kb = io.held_keys()
    held_ms = {io.mouse_button_name(b) for b in io.held_mouse_buttons()}
    key_event(VK_RETURN, WM_KEYUP)
    sync()
    after_kb = fake_kb.snapshot()
    after_mouse = fake_mouse.snapshot()
    ok = (during_key == ["keyboard:press:z"] and during_mouse == [f"mouse:press:{name}"]
          and held_kb == {"z"} and held_ms == {name}
          and after_kb == ["keyboard:press:z", "keyboard:release:z"]
          and after_mouse == [f"mouse:press:{name}", f"mouse:release:{name}"]
          and io.held_keys() == set() and io.held_mouse_buttons() == set())
    label = {"left": "B", "middle": "C", "right": "D"}[name]
    check(f"{label} Z + Mouse {name}：按住期间两者都 held，松开后都释放",
          ok, f"during_kb={during_key} during_mouse={during_mouse} held={held_kb}/{held_ms}")

# ============ 测试 E：重复 DOWN / 重复 UP ============
reset()
io.set_enter_callbacks(
    on_down=lambda: (io.press_mouse("left"), io.press_key("z")),
    on_up=lambda: (io.release_mouse("left"), io.release_key("z")),
)
for _ in range(3):
    key_event(VK_RETURN, WM_KEYDOWN)
sync()
down_kb = fake_kb.snapshot()
down_mouse = fake_mouse.snapshot()
for _ in range(3):
    key_event(VK_RETURN, WM_KEYUP)
sync()
up_kb = fake_kb.snapshot()
up_mouse = fake_mouse.snapshot()
check("E 三次 Enter DOWN 只产生一次 Z DOWN 与一次鼠标 DOWN",
      down_kb == ["keyboard:press:z"] and down_mouse == ["mouse:press:left"],
      f"kb={down_kb} mouse={down_mouse}")
check("E 三次 Enter UP 只产生一次 Z UP 与一次鼠标 UP",
      up_kb == ["keyboard:press:z", "keyboard:release:z"]
      and up_mouse == ["mouse:press:left", "mouse:release:left"],
      f"kb={up_kb} mouse={up_mouse}")

# ============ 测试 F：release_all() 覆盖三组组合 ============
for name in ("left", "middle", "right"):
    reset()
    io.press_mouse(name)
    io.press_key("z")
    check(f"F [{name}] release_all 之前两者都在 held",
          io.held_keys() == {"z"} and len(io.held_mouse_buttons()) == 1,
          f"kb={io.held_keys()} mouse={io.held_mouse_buttons()}")
    io.release_all()
    check(f"F [{name}] release_all 之后两个 held 集合都为空",
          io.held_keys() == set() and io.held_mouse_buttons() == set(),
          f"kb={io.held_keys()} mouse={io.held_mouse_buttons()}")
    check(f"F [{name}] 实际发出了鼠标 UP 与键盘 UP",
          fake_mouse.snapshot() == [f"mouse:press:{name}", f"mouse:release:{name}"]
          and fake_kb.snapshot() == ["keyboard:press:z", "keyboard:release:z"],
          f"mouse={fake_mouse.snapshot()} kb={fake_kb.snapshot()}")

# F2：多个鼠标键 + 多个键盘键同时 held 时，全部释放
reset()
io.press_mouse("left")
io.press_mouse("right")
io.press_key("z")
io.press_key("x")
io.release_all()
check("F2 多键组合 release_all 全部释放且 held 清空",
      io.held_keys() == set() and io.held_mouse_buttons() == set()
      and len(fake_mouse.snapshot()) == 4 and len(fake_kb.snapshot()) == 4,
      f"mouse={fake_mouse.snapshot()} kb={fake_kb.snapshot()}")

# ============ 额外：release_all 不释放"用户自己按住"的输入 ============
reset()
# 用户自己按住了右键（程序没有 press 过它），程序只按了 Z + 左键
io.press_mouse("left")
io.press_key("z")
io.release_all()
user_held_preserved = "right" not in [c.split(":")[2] for c in fake_mouse.snapshot() if "release" in c]
check("额外 release_all 不会去释放用户自己按住的鼠标键（右键未被触碰）",
      user_held_preserved, f"mouse calls={fake_mouse.snapshot()}")

# ============ 额外：没有按住任何东西时 release_all 不产生任何事件 ============
reset()
io.release_all()
check("额外 空状态下 release_all 不产生任何 release",
      fake_kb.snapshot() == [] and fake_mouse.snapshot() == [],
      f"kb={fake_kb.snapshot()} mouse={fake_mouse.snapshot()}")

# ============ 额外：Enter 仍按住时被停止 -> release_all 兜底 ============
reset()
io.set_enter_callbacks(
    on_down=lambda: (io.press_mouse("middle"), io.press_key("z")),
    on_up=lambda: (io.release_mouse("middle"), io.release_key("z")),
)
key_event(VK_RETURN, WM_KEYDOWN)
sync()
check("G 异常退出前：Z 与中键都在 held",
      io.held_keys() == {"z"} and len(io.held_mouse_buttons()) == 1,
      f"kb={io.held_keys()} mouse={io.held_mouse_buttons()}")
io.release_all()   # 模拟 stop_enter_listener() 内部的兜底
check("G 异常退出兜底后：Z 与中键都被释放",
      io.held_keys() == set() and io.held_mouse_buttons() == set()
      and fake_mouse.snapshot() == ["mouse:press:middle", "mouse:release:middle"]
      and fake_kb.snapshot() == ["keyboard:press:z", "keyboard:release:z"],
      f"mouse={fake_mouse.snapshot()} kb={fake_kb.snapshot()}")

print()
failed = [name for name, ok in results if not ok]
print(f"总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过")
