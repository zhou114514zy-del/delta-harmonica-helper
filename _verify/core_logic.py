"""CORE BIG TEST —— 纯逻辑部分。

不修改任何生产代码；只调用现有 API（FixedScorePlayer / score / playback / executor）。
使用**最终 config.json 的真实 min_hold_ms（50）**，不使用 0。
真实 threading.Timer + time.monotonic() 验证时序。
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonica_app import FixedScorePlayer, load_min_hold_ms  # noqa: E402
from score import parse_score, parse_score_notes  # noqa: E402

MIN_HOLD = load_min_hold_ms()
assert MIN_HOLD == 50, f"必须使用真实配置值 50，实际读到 {MIN_HOLD}"
settle_s = MIN_HOLD / 1000.0 + 0.10

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


class Fake:
    """记录 press/release 调用序列与时间，便于检查"是否有过 UP->DOWN 抖动"。"""

    def __init__(self):
        self.calls = []          # (name, arg, monotonic)
        self._held = set()
        self._mouse = set()
        self.lock = threading.Lock()

    def _rec(self, name, arg):
        with self.lock:
            self.calls.append((name, arg, time.monotonic()))

    def press_key(self, k):
        self._rec("press_key", k); self._held.add(k)

    def release_key(self, k):
        self._rec("release_key", k); self._held.discard(k)

    def press_mouse(self, b):
        self._rec("press_mouse", b); self._mouse.add(b)

    def release_mouse(self, b):
        self._rec("release_mouse", b); self._mouse.discard(b)

    def held_keys(self): return set(self._held)
    def held_mouse_buttons(self): return set(self._mouse)
    def names(self): return [f"{n}({a})" for n, a, _ in self.calls]
    def count(self, name, arg): return sum(1 for n, a, _ in self.calls if n == name and a == arg)
    def clear(self): self.calls.clear()


def make(score_text):
    fake = Fake()
    player = FixedScorePlayer(parse_score_notes(score_text), io_module=fake,
                              min_hold_ms=MIN_HOLD)
    return fake, player


def tap(player, hold_s=None):
    """一次完整按放，并等 min_hold_ms 落地。"""
    player.enter_down()
    time.sleep(0.005 if hold_s is None else hold_s)
    player.enter_up()
    time.sleep(settle_s)


print("=" * 70)
print(f"CORE BIG TEST — 纯逻辑（min_hold_ms = {MIN_HOLD}）")
print("=" * 70)

print("\n########## 二、基础音符映射 1 2 3 4 5 6 7 1' ##########")
expected_map = [("1", "z"), ("2", "x"), ("3", "c"), ("4", "v"),
                ("5", "b"), ("6", "n"), ("7", "m"), ("1'", ",")]
score_all = " ".join(n for n, _ in expected_map)
fake, player = make(score_all)
seen = []
for note_name, want_key in expected_map:
    player.enter_down()
    state = player.current_state()
    seen.append((note_name, sorted(state.keys), str(player.current_note().note)))
    player.enter_up()
    time.sleep(settle_s)
# 末音符释放后 controller 已 finished
core_ok = all(notes == [k] and cur == n for (n, k), (_, notes, cur) in zip(expected_map, seen))
for (n, k), (_, notes, cur) in zip(expected_map, seen):
    print(f"    {n:>3} -> expected [{k}]   actual {notes}   (current_note={cur})")
check("基础音符 8 个映射全部正确", core_ok, f"seen={[(n, ks) for n, ks, _ in seen]}")

print("\n########## 三、三种调音：↑ / ↓ / ~ ##########")
for modifier, label, want_mouse in [("↑", "Sharp / Right", "right"),
                                    ("↓", "Flat / Left", "left"),
                                    ("~", "Half / Middle", "middle")]:
    fake, player = make(f"[{modifier} 1]")
    player.enter_down()
    st = player.current_state()
    ok = st.keys == {"z"} and st.mouse_buttons == {want_mouse}
    check(f"{label}：1 -> z + {want_mouse}", ok,
          f"state=keys={sorted(st.keys)} mouse={sorted(st.mouse_buttons)}")
    player.shutdown()

# 每个区间内多个音符
for modifier, label, want_mouse in [("↑", "Sharp", "right"), ("↓", "Flat", "left"), ("~", "Half", "middle")]:
    fake, player = make(f"[{modifier} 1 2 3]")
    states = []
    for _ in range(3):
        player.enter_down()
        st = player.current_state()
        states.append((sorted(st.keys), sorted(st.mouse_buttons)))
        player.enter_up()
        time.sleep(settle_s)
    ok = all(m == [want_mouse] and len(k) == 1 for k, m in states)
    check(f"[{modifier} 1 2 3] 三个音符都带 {want_mouse}", ok, f"states={states}")
    player.shutdown()

print("\n########## 四、混合谱 1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2] ##########")
MIXED = "1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]"
expected_mixed = [
    ("1", ["z"], []),
    ("2", ["x"], []),
    ("3", ["c"], ["right"]),
    ("4", ["v"], ["right"]),
    ("5", ["b"], ["right"]),
    ("6", ["n"], []),
    ("7", ["m"], ["middle"]),
    ("1'", [","], ["middle"]),
    ("2", ["x"], ["left"]),
]
fake, player = make(MIXED)
actual_mixed = []
for _ in range(len(expected_mixed)):
    player.enter_down()
    st = player.current_state()
    actual_mixed.append((str(player.current_note().note), sorted(st.keys), sorted(st.mouse_buttons)))
    player.enter_up()
    time.sleep(settle_s)
for exp, got in zip(expected_mixed, actual_mixed):
    mark = "OK " if exp == got else "BAD"
    print(f"    {mark} note={got[0]:>3}  expected keys={exp[1]} mouse={exp[2]}   actual keys={got[1]} mouse={got[2]}")
check("混合谱 9 个音符状态全部正确", actual_mixed == expected_mixed,
      f"actual={actual_mixed}")

print("\n########## 五、连续调音保持（不得 UP->DOWN 抖动） ##########")
# [↑ 3 4 5]：right 只应被按一次、中途不释放
fake, player = make("[↑ 3 4 5]")
for _ in range(3):
    player.enter_down(); player.enter_up(); time.sleep(settle_s)
r_press = fake.count("press_mouse", "right")
r_release = fake.count("release_mouse", "right")
check("↑ 区间内 Right 只按下 1 次", r_press == 1, f"press_mouse(right) x{r_press}")
check("↑ 区间内 Right 中途未释放（无 UP->DOWN 抖动）", r_release <= 1,
      f"release_mouse(right) x{r_release}  calls={fake.names()}")
player.shutdown()

fake, player = make("[~ 7 1']")
for _ in range(2):
    player.enter_down(); player.enter_up(); time.sleep(settle_s)
m_press = fake.count("press_mouse", "middle")
check("~ 区间内 Middle 只按下 1 次", m_press == 1, f"press_mouse(middle) x{m_press}")
player.shutdown()

fake, player = make("[↓ 4 5]")
for _ in range(2):
    player.enter_down(); player.enter_up(); time.sleep(settle_s)
l_press = fake.count("press_mouse", "left")
check("↓ 区间内 Left 只按下 1 次", l_press == 1, f"press_mouse(left) x{l_press}")
player.shutdown()

# 跨区间：↑ -> normal 必须释放 right
fake, player = make("[↑ 3] 4")
player.enter_down(); player.enter_up(); time.sleep(settle_s)
got_right_press = fake.count("press_mouse", "right")
got_right_release = fake.count("release_mouse", "right")
check("跨出 ↑ 区间时 Right 被释放", got_right_release == 1,
      f"press x{got_right_press} release x{got_right_release}")
player.shutdown()

print("\n########## 七、min_hold_ms = 50 边界 ##########")
print("--- A. 极快 Enter DOWN -> UP（不得小于 50ms 就释放）---")
fake, player = make("1 2")
t_down = time.monotonic()
player.enter_down()
time.sleep(0.003)                     # 3ms 就松开
player.enter_up()
check("A1 松开后音符仍保持 DOWN（未提前释放）",
      player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
check("A2 index 未推进", player.index == 0, f"index={player.index}")
check("A3 timer 已挂起", player._pending_timer is not None, "pending")
while player._pending_timer is not None and time.monotonic() - t_down < 1.0:
    time.sleep(0.002)
held_ms = (time.monotonic() - t_down) * 1000
check("A4 实际保持时间 >= min_hold_ms（允许系统调度误差）", held_ms >= MIN_HOLD - 5,
      f"measured {held_ms:.1f}ms (min_hold_ms={MIN_HOLD})")
check("A5 到点后释放且推进", player.index == 1 and player.current_state_text() == "keys=[x] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
player.shutdown()

print("--- B. 正常长按 ---")
fake, player = make("1 2")
player.enter_down()
check("B1 Enter DOWN -> 音符 DOWN", player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
time.sleep(0.15)                      # 明显超过 50ms
check("B2 保持期间仍为 DOWN", player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
t_up = time.monotonic()
player.enter_up()
dt = (time.monotonic() - t_up) * 1000
check("B3 Enter UP 后立即释放（无额外等待）",
      player.current_state_text() == "keys=[x] mouse=[-]",
      f"state={player.current_state_text()}  release 耗时 {dt:.1f}ms")
check("B4 index 推进", player.index == 1, f"index={player.index}")
player.shutdown()

print("--- C. 50ms 附近边界 ---")
for hold_ms, label in [(30, "30ms(<50)"), (70, "70ms(>50)")]:
    fake, player = make("1 2")
    player.enter_down()
    time.sleep(hold_ms / 1000.0)
    player.enter_up()
    immediate = player._pending_timer is None
    if hold_ms < MIN_HOLD:
        ok = (not immediate)         # 应挂 timer
    else:
        ok = immediate               # 应立即完成
    check(f"C {label} 行为正确（{'挂 timer' if hold_ms < MIN_HOLD else '立即完成'}）", ok,
          f"timer_pending={not immediate} index={player.index}")
    time.sleep(settle_s)
    check(f"C {label} 之后正常推进到 1", player.index == 1, f"index={player.index}")
    player.shutdown()

print("--- D. 极快 UP 后 Esc：pending timer 被彻底失效 ---")
fake, player = make("1 2 3")
player.enter_down(); time.sleep(0.003); player.enter_up()
check("D1 timer 挂起、音符保持", player._pending_timer is not None and player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
player.emergency_stop()
calls_snapshot = fake.names()
check("D2 Esc 后输入全释放", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
time.sleep(settle_s + 0.2)            # 等过旧 timer 该到点的时刻
check("D3 旧 timer 之后不再有任何输入", fake.names() == calls_snapshot, f"calls={fake.names()}")
check("D4 旧 timer 之后 index 不变", player.index == 0, f"index={player.index}")
player.shutdown()

print("--- E. 极快 UP 后 R：pending timer 失效且 index=0 ---")
fake, player = make("1 2 3")
player.enter_down(); time.sleep(0.003); player.enter_up()
player.enter_down(); time.sleep(0.003); player.enter_up()
player.reset()
calls_snapshot = fake.names()
check("E1 R 后 index == 0", player.index == 0, f"index={player.index}")
check("E2 R 后输入全释放", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
time.sleep(settle_s + 0.2)
check("E3 旧 timer 之后不再有任何输入", fake.names() == calls_snapshot, f"calls={fake.names()}")
check("E4 index 仍为 0", player.index == 0, f"index={player.index}")
player.shutdown()

print("--- F. 极快 UP 后 shutdown：旧 timer 不会重新按键 ---")
fake, player = make("1 2 3")
player.enter_down(); time.sleep(0.003); player.enter_up()
player.shutdown()
calls_snapshot = fake.names()
time.sleep(settle_s + 0.2)
check("F1 shutdown 后不再有任何输入", fake.names() == calls_snapshot, f"calls={fake.names()}")
check("F2 无残留 timer", player._pending_timer is None, f"timer={player._pending_timer}")

print("\n########## 五、Enter 去重 ##########")
fake, player = make("1 2 3")
player.enter_down()
for _ in range(10):
    player.enter_down()                # 模拟长按自动重复
check("重复 DOWN 只产生一次 press", fake.count("press_key", "z") == 1,
      f"press_key(z) x{fake.count('press_key', 'z')}")
check("重复 DOWN 不推进 index", player.index == 0, f"index={player.index}")
time.sleep(0.15)
player.enter_up()
check("正常长按后推进到 1", player.index == 1, f"index={player.index}")
for _ in range(3):
    player.enter_up()                  # 重复 UP
check("重复 UP 不重复推进（index 仍为 1）", player.index == 1, f"index={player.index}")
check("重复 UP 后无挂起 timer", player._pending_timer is None, f"timer={player._pending_timer}")
player.shutdown()

print("\n########## 六、Esc 紧急停止 ##########")
fake, player = make("1 2 3 4")
tap(player)                            # ->2
tap(player)                            # ->3
player.enter_down()                    # 播放 3
check("Esc 前正在播放 3", player.current_state_text() == "keys=[c] mouse=[-]",
      f"state={player.current_state_text()} index={player.index}")
player.emergency_stop()
check("Esc 后音符 UP", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("Esc 后 index 不变（2）", player.index == 2, f"index={player.index}")
check("Esc 后 current note 仍是 3", str(player.current_note().note) == "3",
      f"note={player.current_note()}")
player.enter_up()                      # 物理释放
player.enter_down()
check("Esc 后重新 Enter 正常播放（C）", player.current_state_text() == "keys=[c] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_up(); time.sleep(settle_s)
check("之后正常推进到 3", player.index == 3, f"index={player.index}")
player.shutdown()

print("--- Esc 时 Enter 仍按住：不制造第二个 Enter DOWN ---")
fake, player = make("1 2")
player.enter_down()
player.emergency_stop()
player.enter_down()                    # 未释放 Enter，应被忽略
check("未释放 Enter 时重复 DOWN 不重播",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("未释放 Enter 时 press 只发生过一次", fake.count("press_key", "z") == 1,
      f"press_key(z) x{fake.count('press_key', 'z')}")
player.enter_up(); player.enter_down()
check("释放后再按则正常播放",
      player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
player.shutdown()

print("\n########## 七、R 重置 ##########")
fake, player = make("1 2 3 4")
tap(player); tap(player)               # index=2
player.enter_down()
check("R 前 index=2 且正在播放", player.index == 2 and player.current_state_text() == "keys=[c] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
player.reset()
check("R 后所有输入 UP", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("R 后 index == 0", player.index == 0, f"index={player.index}")
check("R 后 current note == 1", str(player.current_note().note) == "1",
      f"note={player.current_note()}")
check("R 后无残留 timer", player._pending_timer is None, f"timer={player._pending_timer}")
player.enter_up(); player.enter_down()
check("R 后重新 Enter 从第一个音符开始（Z）",
      player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
player.shutdown()

print("\n########## 八、连续 Esc ×3 / R ×3 ##########")
fake, player = make("1 2 [↑ 3 4 5]")
player.enter_down()
ok = True
try:
    for _ in range(3):
        player.emergency_stop()
except Exception as exc:  # noqa: BLE001
    ok = False
    print("        raised:", repr(exc))
check("Esc ×3 不崩溃", ok, "no exception")
check("Esc ×3 后无输入", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("Esc ×3 后 index 未变", player.index == 0, f"index={player.index}")
check("Esc ×3 后无 timer 残留", player._pending_timer is None, f"timer={player._pending_timer}")
player.shutdown()

fake, player = make("1 2 3 4")
tap(player); player.enter_down()
ok = True
try:
    for _ in range(3):
        player.reset()
except Exception as exc:  # noqa: BLE001
    ok = False
    print("        raised:", repr(exc))
check("R ×3 不崩溃", ok, "no exception")
check("R ×3 后无输入", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("R ×3 后 index == 0", player.index == 0, f"index={player.index}")
check("R ×3 后无 timer 残留", player._pending_timer is None, f"timer={player._pending_timer}")
player.shutdown()

print("\n########## 十、shutdown 清理 + 250ms 后无重新输入 ##########")
fake, player = make("1 2 [↑ 3 4 5]")
player.enter_down(); time.sleep(0.003); player.enter_up()   # timer pending
player.enter_down()                                         # 再次按住
check("shutdown 前有输入被持有", player.current_state_text() != "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.shutdown()
check("shutdown 后所有输入 UP", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("shutdown 后无 timer 残留", player._pending_timer is None, f"timer={player._pending_timer}")
check("shutdown 后 held 为空", fake.held_keys() == set() and fake.held_mouse_buttons() == set(),
      f"held={fake.held_keys()} mouse={fake.held_mouse_buttons()}")
calls_snapshot = fake.names()
time.sleep(0.25)
check("250ms 后没有重新出现任何输入", fake.names() == calls_snapshot, f"calls={fake.names()}")

print("\n########## 补充：parse_score 与 parse_score_notes 一致性 ##########")
dicts = parse_score(MIXED)
notes = parse_score_notes(MIXED)
same = all(d["note"] == n.note and d["key"] == n.key and d["modifier"] == n.modifier
           for d, n in zip(dicts, notes))
check("parse_score 与 parse_score_notes 结果一致", same and len(dicts) == len(notes) == 9,
      f"len={len(dicts)}/{len(notes)}")
check("混合谱在解析层就是 9 个音符", len(notes) == 9, f"len={len(notes)}")

print()
failed = [n for n, ok in results if not ok]
print("=" * 70)
print(f"CORE BIG TEST (logic) 总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for n in failed:
        print("  - " + n)
    sys.exit(1)
print("全部通过")
sys.exit(0)
