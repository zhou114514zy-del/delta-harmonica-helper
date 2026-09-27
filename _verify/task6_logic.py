"""Task 6 纯逻辑测试：不向系统发送任何真实按键。

做法：把 input.py 里的模拟按键器换成一个"记录器"（假的），
再直接调用钩子回调（自己构造事件结构体），观察逻辑层面的 press/release 行为。
全程不调用 keybd_event / SendInput，普通字符不会进入系统输入流。
"""
import ctypes
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import input as io  # noqa: E402
from input import KBDLLHOOKSTRUCT  # noqa: E402

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK_RETURN, VK_ESCAPE = 0x0D, 0x1B


class FakeKeyboard:
    """记录器：代替真实的 pynput 键盘控制器，不产生任何系统输入。"""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def press(self, key):
        with self.lock:
            self.calls.append(f"press:{key}")

    def release(self, key):
        with self.lock:
            self.calls.append(f"release:{key}")

    def snapshot(self):
        with self.lock:
            return list(self.calls)

    def clear(self):
        with self.lock:
            self.calls.clear()


fake = FakeKeyboard()
io._keyboard = fake          # 关键：整个测试期间都用记录器

# 注册与 main.py 一致的接线：Enter DOWN -> press_key("z")，Enter UP -> release_key("z")
io.set_enter_callbacks(
    on_down=lambda: io.press_key("z"),
    on_up=lambda: io.release_key("z"),
)

_keep_alive = {}


def key_event(vk, message):
    """构造一个低级键盘钩子事件并直接调用回调（不经过系统输入流）。"""
    info = KBDLLHOOKSTRUCT()
    info.vkCode = vk
    info.scanCode = 0
    info.flags = 0
    info.time = 0
    info.dwExtraInfo = 0
    _keep_alive["info"] = info   # 保住对象，避免地址失效
    addr = ctypes.cast(ctypes.pointer(info), ctypes.c_void_p).value
    return io._hook_callback(0, message, addr)


def sync():
    """等异步用户回调执行完。"""
    while not io._drain_callbacks(timeout=1.0):
        time.sleep(0.01)


def reset():
    sync()
    fake.clear()
    io._enter_down = False
    io._escape_down = False
    io._held_keys.clear()


results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}  {name}  {detail}")


# ---------- 1) 长按 Enter：30 次自动重复的 key-down ----------
reset()
returns = [key_event(VK_RETURN, WM_KEYDOWN)]          # 第一次真实按下
for _ in range(29):                                    # 自动重复
    returns.append(key_event(VK_RETURN, WM_KEYDOWN))
sync()
after_repeats = fake.snapshot()
check("长按期间 30 次 key-down 只产生 1 次 Z DOWN",
      after_repeats == ["press:z"], f"calls={after_repeats}")

key_event(VK_RETURN, WM_KEYUP)
sync()
after_release = fake.snapshot()
check("松开后只补 1 次 Z UP",
      after_release == ["press:z", "release:z"], f"calls={after_release}")
check("所有 Enter 事件都被拦截（回调返回 1）",
      set(returns) == {1}, f"returns={set(returns)}")

# ---------- 2) 连续三次独立按放 ----------
reset()
for _ in range(3):
    key_event(VK_RETURN, WM_KEYDOWN)
    key_event(VK_RETURN, WM_KEYUP)
sync()
calls = fake.snapshot()
check("三次独立按放 = 三次 Z DOWN/UP 循环",
      calls == ["press:z", "release:z"] * 3, f"calls={calls}")

# ---------- 3) 只有 key-up（异常序列）不应产生 release ----------
reset()
key_event(VK_RETURN, WM_KEYUP)
sync()
calls = fake.snapshot()
check("没有按下过的 UP 不产生 release", calls == [], f"calls={calls}")

# ---------- 4) Enter 仍按住时程序停止：必须补 Z UP ----------
reset()
key_event(VK_RETURN, WM_KEYDOWN)
sync()
check("按住期间 _held_keys 记录到 z", "z" in io._held_keys, f"held={io._held_keys}")
io.release_all()
calls = fake.snapshot()
check("release_all() 在仍按住时补了一次 Z UP",
      calls == ["press:z", "release:z"], f"calls={calls}")
check("release_all() 之后不再记录为按住", io._held_keys == set(), f"held={io._held_keys}")

# ---------- 5) 没有按住时 release_all 不应乱释放 ----------
reset()
io.release_all()
calls = fake.snapshot()
check("没有按住任何键时 release_all() 不产生 release", calls == [], f"calls={calls}")

# ---------- 6) release_all 不重复释放已经松开的键 ----------
reset()
key_event(VK_RETURN, WM_KEYDOWN)
key_event(VK_RETURN, WM_KEYUP)
sync()
io.release_all()
calls = fake.snapshot()
check("已正常松开的键不会被 release_all 重复释放",
      calls == ["press:z", "release:z"], f"calls={calls}")

# ---------- 7) 其他按键不被拦截、不触发模拟输入 ----------
reset()
other = [0x41, 0x5A, 0x20, 0x09, 0x10]   # A Z Space Tab Shift
rv = [key_event(vk, WM_KEYDOWN) for vk in other]
rv += [key_event(vk, WM_KEYUP) for vk in other]
sync()
check("A/Z/Space/Tab/Shift 全部放行（返回 0）", set(rv) == {0}, f"returns={set(rv)}")
check("其他按键不触发任何模拟输入", fake.snapshot() == [], f"calls={fake.snapshot()}")

# ---------- 8) Esc 在 Enter 按住期间仍能被识别 ----------
reset()
key_event(VK_RETURN, WM_KEYDOWN)
sync()
rv_esc = key_event(VK_ESCAPE, WM_KEYDOWN)
sync()
check("Enter 按住期间 Esc 仍被识别（返回 0，不拦截）", rv_esc == 0, f"return={rv_esc}")

print()
failed = [name for name, ok in results if not ok]
print(f"总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:", failed)
    sys.exit(1)
print("全部通过")
