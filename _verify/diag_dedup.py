"""Temporary: deterministic test of the Enter dedup logic.

Synthetic keystrokes (keybd_event / SendInput) do NOT trigger Windows auto-repeat,
so this drives the same handler path with the event sequence that Windows really
produces while a key is physically held: repeated key-downs, then one key-up.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pynput.keyboard import Key  # noqa: E402
import input as io  # noqa: E402

out = []
io.set_enter_callbacks(on_down=lambda: out.append("Enter DOWN"), on_up=lambda: out.append("Enter UP"))


def hold(name, seconds, repeats):
    """Simulate: 1 real press + (repeats-1) auto-repeat key-downs, then 1 release."""
    out.clear()
    for _ in range(repeats):
        io._on_press(Key.enter)
    for _ in range(repeats):
        io._on_release(Key.enter)
    downs = out.count("Enter DOWN")
    ups = out.count("Enter UP")
    print(f"{name}: 底层事件 = {repeats} 次 key-down + {repeats} 次 key-up")
    print(f"  逻辑输出 = {out}")
    print(f"  DOWN={downs} UP={ups}  -> {'PASS' if downs == 1 and ups == 1 else 'FAIL'}")
    return downs == 1 and ups == 1


ok = True

# Windows 自动重复：按住期间约每 33ms 一个 key-down
ok &= hold("A. 按住约 1 秒 (约 30 次自动重复)", 1.0, 30)
ok &= hold("B. 按住约 3 秒 (约 90 次自动重复)", 3.0, 90)

# 连续三次独立按下 / 松开
out.clear()
for _ in range(3):
    io._on_press(Key.enter)
    io._on_release(Key.enter)
print(f"C. 三次独立按放: 逻辑输出 = {out}  -> {'PASS' if out == ['Enter DOWN', 'Enter UP'] * 3 else 'FAIL'}")
ok &= out == ["Enter DOWN", "Enter UP"] * 3

# 只有松开、没有按下（异常的重复 UP）不应输出
out.clear()
io._on_release(Key.enter)
print(f"D. 无对应按下的 UP: 逻辑输出 = {out}  -> {'PASS' if out == [] else 'FAIL'}")
ok &= out == []

# 其他按键不得被当成 Enter
out.clear()
for k in ("a", "z", Key.space, Key.shift, Key.tab):
    io._on_press(k)
    io._on_release(k)
print(f"E. 其他按键 (a/z/space/shift/tab): 逻辑输出 = {out}  -> {'PASS' if out == [] else 'FAIL'}")
ok &= out == []

print(f"\n去重逻辑总体: {'PASS' if ok else 'FAIL'}")
