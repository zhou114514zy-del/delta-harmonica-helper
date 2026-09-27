"""Task 13 纯逻辑测试：安全控制（Esc / R / shutdown / timer race）。

要点：
    - 使用最终 config.json 的真实 min_hold_ms（通过 load_min_hold_ms() 读取），
      不使用 0 来回避 Task 12 的延迟行为。
    - 注入"记录器"输入模块，不产生任何真实输入。
    - 用真实 threading.Timer + time.monotonic() 验证 race 行为。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonica_app import FixedScorePlayer, load_min_hold_ms  # noqa: E402
from score import parse_score_notes  # noqa: E402

MIN_HOLD = load_min_hold_ms()          # 真实配置值（当前 50）
HOLD_WAIT = MIN_HOLD / 1000.0 + 0.12   # 等过 min_hold_ms 并留余量

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


class FakeInput:
    def __init__(self):
        self.calls = []
        self._held = set()
        self._mouse = set()

    def _rec(self, name, arg):
        self.calls.append(f"{name}({arg})")

    def press_key(self, k):
        self._rec("press_key", k)
        self._held.add(k)

    def release_key(self, k):
        self._rec("release_key", k)
        self._held.discard(k)

    def press_mouse(self, b):
        self._rec("press_mouse", b)
        self._mouse.add(b)

    def release_mouse(self, b):
        self._rec("release_mouse", b)
        self._mouse.discard(b)

    def held_keys(self):
        return set(self._held)

    def held_mouse_buttons(self):
        return set(self._mouse)

    def names(self):
        return list(self.calls)

    def clear(self):
        self.calls.clear()


def make(score_text, min_hold_ms=None):
    fake = FakeInput()
    value = MIN_HOLD if min_hold_ms is None else min_hold_ms
    player = FixedScorePlayer(parse_score_notes(score_text), io_module=fake,
                              min_hold_ms=value)
    return fake, player


print(f"================ 配置 ================")
check(f"使用最终 config.json 的 min_hold_ms（={MIN_HOLD}，不是 0）", MIN_HOLD == 50,
      f"load_min_hold_ms() = {MIN_HOLD}")

print("\n================ 一、Esc 紧急停止 ================")
# 场景：1 2 [↑ 3 4 5] 正在播放 3（C + Right），按 Esc
fake, player = make("1 2 [↑ 3 4 5]")
player.enter_down(); player.enter_up()          # 1 -> 2
time.sleep(HOLD_WAIT)
player.enter_down(); player.enter_up()          # 2 -> 3（就绪）
time.sleep(HOLD_WAIT)
player.enter_down()                             # 开始播放 3
check("Esc 前：正在播放 3 = C + Right",
      player.current_state_text() == "keys=[c] mouse=[right]",
      f"state={player.current_state_text()} index={player.index}")
check("Esc 前 index == 2", player.index == 2, f"index={player.index}")
player.emergency_stop()
check("Esc 后：C = UP", "c" not in player.current_state().keys,
      f"state={player.current_state_text()}")
check("Esc 后：Right = UP", "right" not in player.current_state().mouse_buttons,
      f"state={player.current_state_text()}")
check("Esc 后：没有任何模拟输入被持有",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("Esc 后 index 不变（仍为 2）", player.index == 2, f"index={player.index}")
check("Esc 后没有挂起 timer", player._pending_timer is None,
      f"timer={player._pending_timer}")
check("Esc 后 current_note 仍是 3（等待新的 Enter DOWN）",
      str(player.current_note().note) == "3", f"note={player.current_note()}")
check("Esc 后假输入模块的 held 状态也为空",
      fake.held_keys() == set() and fake.held_mouse_buttons() == set(),
      f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")

print("\n--- Esc 后可重新开始（物理释放 Enter 再按，重播当前音符） ---")
# 注意：Esc 停止的是"演奏状态"，不清除 enter_is_down（否则钩子与 player 会不同步）。
# 真实操作是"松开 Enter -> 按 Esc"，或"Esc 之后再松开再按"。
player.enter_up()                       # 物理释放
player.enter_down()
check("Esc 后 Enter DOWN 正常播放当前音符 3（C+Right）",
      player.current_state_text() == "keys=[c] mouse=[right]",
      f"state={player.current_state_text()}")
player.enter_up()
time.sleep(HOLD_WAIT)
check("松开并满足 min_hold_ms 后推进到 index=3",
      player.index == 3, f"index={player.index}")
player.shutdown()

print("\n--- Esc 时 Enter 仍按住：不释放则不会重播（正确行为） ---")
fake, player = make("1 2 3")
player.enter_down()
player.emergency_stop()
player.enter_down()                     # 没有物理释放，应被忽略
check("Esc 后未释放 Enter 时，重复 DOWN 不重播",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_up()                       # 松开
player.enter_down()                     # 再按
check("释放后再按则正常播放",
      player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
player.shutdown()

print("\n================ 二、R 重置 ================")
fake, player = make("1 2 3 4")
player.enter_down(); player.enter_up(); time.sleep(HOLD_WAIT)   # ->2
player.enter_down(); player.enter_up(); time.sleep(HOLD_WAIT)   # ->3
player.enter_down()                                            # 播放 3
check("R 前：index=2，正在播放 3（C）",
      player.index == 2 and player.current_state_text() == "keys=[c] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
player.reset()
check("R 后：index == 0", player.index == 0, f"index={player.index}")
check("R 后：current note == 1", str(player.current_note().note) == "1",
      f"note={player.current_note()}")
check("R 后：所有实际输入 UP",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("R 后：没有挂起 timer", player._pending_timer is None, f"timer={player._pending_timer}")
check("R 后：假输入模块 held 也为空",
      fake.held_keys() == set() and fake.held_mouse_buttons() == set(),
      f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
player.enter_up()                       # 物理释放（R 不清除 enter_is_down）
player.enter_down()
check("R 后 Enter DOWN 从第一个音符开始（Z）",
      player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_up()
time.sleep(HOLD_WAIT)
check("之后 index 正常推进到 1", player.index == 1, f"index={player.index}")
player.shutdown()

print("\n================ 五、Timer race ================")
print("--- A. Enter DOWN -> 快速 Enter UP（timer pending）-> Esc ---")
fake, player = make("1 2 3")
player.enter_down()
time.sleep(0.005)                       # 远小于 min_hold_ms
player.enter_up()                       # 挂起 timer
check("A1 timer 已挂起、音符仍保持",
      player._pending_timer is not None and player.current_state_text() == "keys=[z] mouse=[-]",
      f"timer={'pending' if player._pending_timer else 'none'} state={player.current_state_text()}")
player.emergency_stop()
calls_after_esc = fake.names()
check("A2 Esc 后立即释放", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
time.sleep(HOLD_WAIT + 0.2)             # 等过旧 timer 该到点的时刻
check("A3 旧 timer 之后没有重新按键",
      fake.names() == calls_after_esc, f"calls={fake.names()}")
check("A4 旧 timer 之后没有推进 index", player.index == 0, f"index={player.index}")
check("A5 旧 timer 之后依然没有任何输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.shutdown()

print("--- B. 快速 UP（timer pending）-> R ---")
fake, player = make("1 2 3")
player.enter_down(); time.sleep(0.005); player.enter_up()
player.enter_down(); time.sleep(0.005); player.enter_up()   # 再走一步（仍在延迟中）
player.reset()
check("B1 R 后 index == 0", player.index == 0, f"index={player.index}")
check("B2 R 后没有任何输入", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
calls_after_reset = fake.names()
time.sleep(HOLD_WAIT + 0.2)
check("B3 旧 timer 之后没有重新按键", fake.names() == calls_after_reset,
      f"calls={fake.names()}")
check("B4 旧 timer 之后 index 仍为 0", player.index == 0, f"index={player.index}")
player.shutdown()

print("--- C. 快速 UP（timer pending）-> shutdown ---")
fake, player = make("1 2 3")
player.enter_down(); time.sleep(0.005); player.enter_up()
check("C1 timer 已挂起", player._pending_timer is not None, "pending")
player.shutdown()
check("C2 shutdown 后立即全释放", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
calls_after_shutdown = fake.names()
time.sleep(HOLD_WAIT + 0.2)
check("C3 旧 timer 之后不再有任何操作", fake.names() == calls_after_shutdown,
      f"calls={fake.names()}")
check("C4 index 未被旧 timer 推进", player.index == 0, f"index={player.index}")

print("--- D. 连续 Esc x3 ---")
fake, player = make("1 2 [↑ 3 4 5]")
player.enter_down()
ok = True
try:
    player.emergency_stop()
    player.emergency_stop()
    player.emergency_stop()
except Exception as exc:  # noqa: BLE001
    ok = False
    print("        raised:", repr(exc))
check("D1 连续三次 Esc 不报错", ok, "no exception")
check("D2 连续三次 Esc 后没有任何输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("D3 连续三次 Esc 后 index 不变", player.index == 0, f"index={player.index}")
check("D4 连续三次 Esc 后 held 为空",
      fake.held_keys() == set() and fake.held_mouse_buttons() == set(),
      f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
player.shutdown()

print("--- E. 连续 R x3 ---")
fake, player = make("1 2 3 4")
player.enter_down(); player.enter_up(); time.sleep(HOLD_WAIT)
player.enter_down()
ok = True
try:
    player.reset()
    player.reset()
    player.reset()
except Exception as exc:  # noqa: BLE001
    ok = False
    print("        raised:", repr(exc))
check("E1 连续三次 R 不报错", ok, "no exception")
check("E2 连续三次 R 后 index == 0", player.index == 0, f"index={player.index}")
check("E3 连续三次 R 后没有任何输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("E4 连续三次 R 后 held 为空",
      fake.held_keys() == set() and fake.held_mouse_buttons() == set(),
      f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
player.shutdown()

print("--- F. Esc 后立即 Enter DOWN/UP ---")
fake, player = make("1 2 3")
player.enter_down()
player.emergency_stop()
player.enter_up()                       # 物理释放（Esc 不清除 enter_is_down）
player.enter_down()
check("F1 Esc 后立即 Enter DOWN 正常播放当前音符",
      player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_up()
time.sleep(HOLD_WAIT)
check("F2 之后正常推进", player.index == 1, f"index={player.index}")
check("F3 推进后全部释放（Task 27A：下一个音符由下一次 DOWN 按下）",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.shutdown()

print("--- G. R 后立即 Enter DOWN/UP ---")
fake, player = make("1 2 3")
player.enter_down(); player.enter_up(); time.sleep(HOLD_WAIT)   # ->2
player.enter_down(); player.enter_up(); time.sleep(HOLD_WAIT)   # ->3
player.reset()
player.enter_up()                       # 物理释放（R 不清除 enter_is_down）
player.enter_down()
check("G1 R 后立即 Enter DOWN 从第一个音符开始（Z）",
      player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_up()
time.sleep(HOLD_WAIT)
check("G2 之后正常推进到 1", player.index == 1, f"index={player.index}")
player.shutdown()

print("\n================ 四、shutdown 清理 ================")
print("--- Enter 正按着 + timer 存在时 shutdown ---")
fake, player = make("1 2 [↑ 3 4 5]")
player.enter_down(); time.sleep(0.005)
player.enter_up()                       # 挂 timer
player.enter_down()                     # 再按住（此时 timer 已被丢弃）
check("shutdown 前：有输入被持有",
      player.current_state_text() != "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.shutdown()
check("shutdown 后：全部 UP",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("shutdown 后：held 为空",
      fake.held_keys() == set() and fake.held_mouse_buttons() == set(),
      f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
check("shutdown 后：没有挂起 timer", player._pending_timer is None,
      f"timer={player._pending_timer}")
check("shutdown 后：controller 已复位（index=0）", player.index == 0, f"index={player.index}")
calls_final = fake.names()
time.sleep(HOLD_WAIT + 0.2)
check("shutdown 后：不会再有新的输入", fake.names() == calls_final, f"calls={fake.names()}")

print("\n--- shutdown 的幂等性 ---")
fake, player = make("1 2")
player.enter_down()
ok = True
try:
    player.shutdown()
    player.shutdown()
    player.shutdown()
except Exception as exc:  # noqa: BLE001
    ok = False
    print("        raised:", repr(exc))
check("重复 shutdown 不报错", ok, "no exception")
check("重复 shutdown 后仍无输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")

print("\n================ 七、Hook 约束（静态检查）================")
import inspect  # noqa: E402
import input as io  # noqa: E402

hook_src = inspect.getsource(io._hook_callback)
check("钩子回调里没有 sleep", "sleep" not in hook_src, "no sleep in _hook_callback")
check("钩子回调里没有等待 timer", "join(" not in hook_src and "wait(" not in hook_src,
      "no join/wait in _hook_callback")
check("Enter 仍然被吞掉（返回 1）", "return 1  # 吞掉 Enter" in hook_src,
      "Enter suppression intact")
check("钩子只拦 Enter，其他键走 CallNextHookEx",
      hook_src.count("CallNextHookEx") >= 1, "passthrough intact")

print()
failed = [name for name, ok in results if not ok]
print(f"总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过")
