"""Task 12 纯逻辑测试：min_hold_ms（最小音符持续时间）。

做法：给 FixedScorePlayer 注入"记录器"输入模块（不产生任何真实输入），
用真实的 threading.Timer + time.monotonic() 验证时序行为。
不向系统发送任何按键。
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonica_app import FixedScorePlayer, load_min_hold_ms  # noqa: E402
from score import parse_score_notes  # noqa: E402

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


class FakeInput:
    """记录调用与其发生时间（单调时钟），并跟踪给 input 模块的 held 状态。"""

    def __init__(self):
        self.calls = []          # [(name, arg, monotonic_time)]
        self._held = set()
        self._mouse = set()
        self.lock = threading.Lock()

    def _record(self, name, arg):
        with self.lock:
            self.calls.append((name, arg, time.monotonic()))

    def press_key(self, key):
        self._record("press_key", key)
        self._held.add(key)

    def release_key(self, key):
        self._record("release_key", key)
        self._held.discard(key)

    def press_mouse(self, button):
        self._record("press_mouse", button)
        self._mouse.add(button)

    def release_mouse(self, button):
        self._record("release_mouse", button)
        self._mouse.discard(button)

    def held_keys(self):
        return set(self._held)

    def held_mouse_buttons(self):
        return set(self._mouse)

    def names(self):
        with self.lock:
            return [c[0] + "(" + str(c[1]) + ")" for c in self.calls]

    def time_of(self, name, arg=None):
        """返回某次调用的时间戳（最后一次匹配）。"""
        with self.lock:
            hits = [c[2] for c in self.calls if c[0] == name and (arg is None or c[1] == arg)]
        return hits[-1] if hits else None

    def clear(self):
        with self.lock:
            self.calls.clear()


def make(score_text, min_hold_ms):
    fake = FakeInput()
    player = FixedScorePlayer(parse_score_notes(score_text), io_module=fake,
                              min_hold_ms=min_hold_ms)
    return fake, player


def wait_for(fake, predicate, timeout=2.0):
    """等到条件成立（轮询，用单调时钟计时）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.002)
    return False


print("================ 配置读取 ================")
check("config.json 里的 min_hold_ms 能读到", load_min_hold_ms() == 50, f"value={load_min_hold_ms()}")
check("配置文件缺失时回退默认值", load_min_hold_ms("不存在的文件.json") == 50, "default=50")

print("\n================ A. 正常长按（播够 min_hold_ms 后松开） ================")
fake, player = make("1 2", 80)
player.enter_down()
check("A1 按下后 Z DOWN", player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
time.sleep(0.12)                      # 按住 120ms > min_hold_ms(80)
up_at = time.monotonic()
player.enter_up()
release_at = fake.time_of("release_key", "z")
check("A2 松开时立即释放（没有额外等待）",
      release_at is not None and (release_at - up_at) < 0.03,
      f"release 延迟 {(release_at - up_at) * 1000:.1f}ms" if release_at else "no release")
check("A3 index 前进到 1", player.index == 1, f"index={player.index}")
check("A4 松开后全部释放（Task 27A：不再预先按下下一个音符）",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("A5 没有挂起的 timer", player._pending_timer is None, f"timer={player._pending_timer}")
player.shutdown()

print("\n================ B. 快速点击（远小于 min_hold_ms） ================")
fake, player = make("1 2", 100)
down_at = time.monotonic()
player.enter_down()
time.sleep(0.01)                      # 只按住 10ms
player.enter_up()
check("B1 松开后当前音符仍保持 DOWN（还没播够）",
      player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
check("B2 index 还没推进", player.index == 0, f"index={player.index}")
check("B3 确实挂了一个 timer", player._pending_timer is not None, "timer pending")
released = wait_for(fake, lambda: fake.time_of("release_key", "z") is not None)
check("B4 timer 到点后释放了 Z", released, f"calls={fake.names()}")
release_at = fake.time_of("release_key", "z")
held_ms = (release_at - down_at) * 1000 if release_at else -1
check("B5 音符实际保持了约 min_hold_ms（100ms，允许 ±40ms）",
      60 <= held_ms <= 150, f"实测保持 {held_ms:.1f}ms")
check("B6 释放后 index 前进到 1", player.index == 1, f"index={player.index}")
player.shutdown()

print("\n================ C. min_hold_ms 边界 ================")
fake, player = make("1 2", 60)
player.enter_down()
time.sleep(0.075)                     # 75ms > 60ms：应当立即完成，不挂 timer
player.enter_up()
check("C1 刚好超过边界 -> 立即释放，不挂 timer",
      player._pending_timer is None and player.index == 1,
      f"timer={player._pending_timer} index={player.index}")
player.shutdown()

fake, player = make("1 2", 60)
player.enter_down()
time.sleep(0.02)                      # 20ms < 60ms：必须挂 timer
player.enter_up()
check("C2 低于边界 -> 挂 timer 等待",
      player._pending_timer is not None and player.index == 0,
      f"timer_pending={player._pending_timer is not None} index={player.index}")
wait_for(fake, lambda: player.index == 1)
check("C3 到点后推进", player.index == 1, f"index={player.index}")
player.shutdown()

fake, player = make("1 2", 0)         # min_hold_ms = 0 等价于关闭该特性
player.enter_down()
player.enter_up()
check("C4 min_hold_ms=0 时行为与 Task 11 一致（立即释放）",
      player._pending_timer is None and player.index == 1,
      f"timer={player._pending_timer} index={player.index}")
player.shutdown()

print("\n================ D. 连续快速音符 1 2 3 4 ================")
fake, player = make("1 2 3 4", 60)
seq = []
expected_keys = ["z", "x", "c", "v"]
for expected_key in expected_keys:
    player.enter_down()
    during = player.current_state_text()
    time.sleep(0.01)                  # 快速点击
    player.enter_up()
    seq.append((expected_key, during, player.index))
    # 等这一步的延迟释放完成，再做下一个（模拟人按节奏敲）
    wait_for(fake, lambda p=player: p._pending_timer is None, timeout=1.0)
check("D1 四个音符都按正确顺序按下",
      all(during == f"keys=[{k}] mouse=[-]" for k, during, _ in seq),
      f"seq={[(k, d) for k, d, _ in seq]}")
indexes = [i for _, _, i in seq]
check("D2 每次推进恰好 1 步（不跳号）", indexes == [0, 1, 2, 3], f"indexes={indexes}")
check("D3 最终 index == 4（不重复推进）", player.index == 4, f"index={player.index}")
check("D4 没有漏音符（Z/X/C/V 都被按下过）",
      all(f"press_key({k})" in fake.names() for k in expected_keys),
      f"calls={fake.names()}")
check("D5 每个音符都被释放过",
      all(f"release_key({k})" in fake.names() for k in expected_keys),
      f"calls={fake.names()}")
player.shutdown()

print("\n================ E. 快速连续调音音符 [↑ 3 4 5] ================")
fake, player = make("[↑ 3 4 5]", 70)
for key in ["c", "v", "b"]:
    player.enter_down()
    time.sleep(0.01)
    player.enter_up()
    wait_for(fake, lambda p=player: p._pending_timer is None, timeout=1.0)
right_presses = fake.names().count("press_mouse(right)")
right_releases = fake.names().count("release_mouse(right)")
check("E1 每个音符都按下 right（3 个音符 -> 3 次，Task 27A）",
      right_presses == 3, f"press_mouse(right) x{right_presses} calls={fake.names()}")
check("E2 三个音符键各按一次",
      all(fake.names().count(f"press_key({k})") == 1 for k in ["c", "v", "b"]),
      f"calls={fake.names()}")
check("E3 right 每次都成对 press/release（3 按 3 放）",
      right_presses == 3 and right_releases == 3,
      f"press x{right_presses} release x{right_releases}")
check("E4 最终 index == 3 且全部释放",
      player.index == 3 and player.current_state_text() == "keys=[-] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")

fake, player = make("[~ 7 1']", 70)
for _ in range(2):
    player.enter_down()
    time.sleep(0.01)
    player.enter_up()
    wait_for(fake, lambda p=player: p._pending_timer is None, timeout=1.0)
check("E6 [~ 7 1'] 每个音符都按下 middle（2 个音符 -> 2 次），两个音符都播出",
      fake.names().count("press_mouse(middle)") == 2
      and fake.names().count("press_key(m)") == 1
      and fake.names().count("press_key(,)") == 1
      and fake.names().count("release_mouse(middle)") == 2,
      f"calls={fake.names()}")
player.shutdown()

fake, player = make("[↓ 2]", 70)
player.enter_down()
time.sleep(0.01)
player.enter_up()
wait_for(fake, lambda p=player: p._pending_timer is None, timeout=1.0)
check("E7 [↓ 2] left 与 x 都正确",
      fake.names().count("press_mouse(left)") == 1
      and fake.names().count("press_key(x)") == 1
      and player.index == 1,
      f"calls={fake.names()} index={player.index}")
player.shutdown()

print("\n================ F. 旧 timer 不会动新音符 ================")
# F1-F6：延迟窗口内再次按下 -> 旧 timer 必须失效，不能替用户开始/释放任何东西
fake, player = make("1 2", 200)
player.enter_down()
time.sleep(0.005)                     # 远小于 200ms
player.enter_up()                     # 挂 timer
gen_after_first_up = player._timer_generation
check("F1 快速点击后：音符 1 保持、timer 挂起、index 未推进",
      player._pending_timer is not None and player.index == 0
      and player.current_state_text() == "keys=[z] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
time.sleep(0.02)
player.enter_down()                   # 延迟窗口内又按下
check("F2 再次按下让 generation 增加（旧 timer 失效）",
      player._timer_generation > gen_after_first_up,
      f"gen {gen_after_first_up} -> {player._timer_generation}")
check("F3 旧 timer 已被丢弃（不再是挂起状态）",
      player._pending_timer is None, f"timer={player._pending_timer}")
time.sleep(0.25)                      # 等过旧 timer 原本该到点的时刻
check("F4 旧 timer 到点后没有凭空开始新音符（index 仍 0）",
      player.index == 0 and player.current_state_text() == "keys=[z] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
player.enter_up()
time.sleep(0.25)
check("F5 这一次的延迟完成由自己的 timer 处理（index=1）",
      player.index == 1, f"index={player.index}")
check("F6 完成后全部释放（Task 27A：下一个音符由下一次 DOWN 按下）",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.shutdown()

# F7-F9：timer 到点时 Enter 正被按住 -> 不得凭空按下下一个音符
fake, player = make("1 2", 80)
player.enter_down()
time.sleep(0.005)
player.enter_up()                     # 挂 timer（约 75ms）
time.sleep(0.01)
player.enter_down()                   # 在 timer 到点前又按住，并一直按住
check("F7 再次按住时仍在音符 1（index=0）",
      player.index == 0 and player.current_state_text() == "keys=[z] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
time.sleep(0.3)                       # 等过所有可能的 timer
check("F8 Enter 一直按住期间：不会凭空按下下一个音符（index 仍为 0，只保留音符 1 的键）",
      player.index == 0 and player.current_state_text() == "keys=[z] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
player.enter_up()
wait_for(fake, lambda p=player: p.index == 1, timeout=1.0)
check("F9 松开后才完成并推进（index=1）", player.index == 1, f"index={player.index}")
player.shutdown()

print("\n================ G. Esc 取消 timer ================")
fake, player = make("1 2 3", 200)
player.enter_down()
time.sleep(0.01)
player.enter_up()                     # 挂 timer
check("G1 timer 已挂起", player._pending_timer is not None, "pending")
gen_before = player._timer_generation
player.shutdown()                     # 等价于 Esc 路径
check("G2 shutdown 让 timer 失效", player._timer_generation > gen_before,
      f"gen {gen_before} -> {player._timer_generation}")
check("G3 shutdown 后输入全部释放", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
calls_after_shutdown = fake.names()
time.sleep(0.3)                       # 等过旧 timer 该到点的时刻
check("G4 旧 timer 到点后没有再产生任何输入",
      fake.names() == calls_after_shutdown,
      f"after={fake.names()}")

print("\n================ H. shutdown 取消 timer（同 G，另有进行中音符） ================")
fake, player = make("[↑ 3] 4", 200)
player.enter_down()
time.sleep(0.01)
player.enter_up()
check("H1 C+right 仍持有、timer 挂起",
      player.current_state_text() == "keys=[c] mouse=[right]" and player._pending_timer is not None,
      f"state={player.current_state_text()}")
player.shutdown()
check("H2 shutdown 立即释放全部输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
snapshot = fake.names()
time.sleep(0.3)
check("H3 旧 timer 到点后不再产生输入、index 不变",
      fake.names() == snapshot and player.index == 0,
      f"index={player.index}")

print("\n================ I. 播放结束 ================")
fake, player = make("1", 100)
player.enter_down()
time.sleep(0.01)
player.enter_up()                     # 最后一个音符也要满足 min_hold_ms
check("I1 最后一个音符也保持住（timer 挂起）",
      player.current_state_text() == "keys=[z] mouse=[-]", f"state={player.current_state_text()}")
released = wait_for(fake, lambda: player.index == 1)
check("I2 到点后释放并播完", released and player.index == 1, f"index={player.index}")
check("I3 播完后没有任何残留输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_down()                   # 播完后再按
check("I4 播完后按下 Enter 不产生任何输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_up()
player.shutdown()

print("\n================ J. 重复 Enter DOWN ================")
fake, player = make("1 2", 100)
player.enter_down()
for _ in range(5):
    player.enter_down()               # 长按自动重复
check("J1 重复 DOWN 不重复按当前音符",
      fake.names().count("press_key(z)") == 1, f"calls={fake.names()}")
check("J2 重复 DOWN 不推进 index", player.index == 0, f"index={player.index}")
time.sleep(0.12)
player.enter_up()
check("J3 长按后松开立即完成", player.index == 1 and player._pending_timer is None,
      f"index={player.index} timer={player._pending_timer}")
# 延迟窗口内的重复 DOWN
player.enter_down()
time.sleep(0.005)
player.enter_up()                     # 挂 timer
for _ in range(3):
    player.enter_up()                 # 重复 UP 不应重复处理
check("J4 延迟窗口内重复 UP 不会重复推进", player.index == 1, f"index={player.index}")
wait_for(fake, lambda: player.index == 2, timeout=1.0)
check("J5 到点后正常完成", player.index == 2, f"index={player.index}")
player.shutdown()

print("\n================ K. 最终全部释放 ================")
fake, player = make("1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]", 40)
for _ in range(9):
    player.enter_down()
    time.sleep(0.005)
    player.enter_up()
    wait_for(fake, lambda p=player: p._pending_timer is None, timeout=1.0)
check("K1 九个音符全部播完", player.index == 9, f"index={player.index}")
check("K2 播完后没有任何残留输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("K3 假输入模块的 held 状态也为空",
      fake.held_keys() == set() and fake.held_mouse_buttons() == set(),
      f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
player.shutdown()

print()
failed = [name for name, ok in results if not ok]
print(f"总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过")
