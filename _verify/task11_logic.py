"""Task 11 纯逻辑测试：Enter -> 演奏 的控制逻辑。

做法：给 FixedScorePlayer 注入一个"记录器"输入模块（与 main.py 完全相同的接线代码），
再用与 main.py 一样的回调方式驱动 Enter DOWN / UP。
不产生任何真实输入。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harmonica_app import FixedScorePlayer  # noqa: E402
from score import parse_score_notes  # noqa: E402

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


class FakeInput:
    """记录真实输入调用，不碰系统。"""

    def __init__(self):
        self.calls = []
        self._held = set()
        self._mouse = set()

    def press_key(self, key):
        self.calls.append(f"press_key({key})")
        self._held.add(key)

    def release_key(self, key):
        self.calls.append(f"release_key({key})")
        self._held.discard(key)

    def press_mouse(self, button):
        self.calls.append(f"press_mouse({button})")
        self._mouse.add(button)

    def release_mouse(self, button):
        self.calls.append(f"release_mouse({button})")
        self._mouse.discard(button)

    def held_keys(self):
        return set(self._held)

    def held_mouse_buttons(self):
        return set(self._mouse)

    def clear(self):
        self.calls.clear()


def make_player(score_text):
    fake = FakeInput()
    # Task 12 给 FixedScorePlayer 加了默认 min_hold_ms=50。本文件是 Task 11 的回归测试，
    # 验证的是"Enter UP 后立即推进"的同步语义，所以显式关闭 min_hold_ms（=0）。
    # Task 12 的延时行为由 _verify\task12_logic.py 覆盖。
    player = FixedScorePlayer(parse_score_notes(score_text), io_module=fake, min_hold_ms=0)
    # 与 main.py 完全一致的接线方式
    player.on_enter_down_cb = lambda: player.enter_down()
    player.on_enter_up_cb = lambda: player.enter_up()
    return fake, player


def tap(player):
    """一次完整按放，返回按下期间与松开之后的状态文本。"""
    player.enter_down()
    during = player.current_state_text()
    player.enter_up()
    after = player.current_state_text()
    return during, after


print("================ A. 单音 ================")
fake, player = make_player("1")
check("初始 index == 0", player.index == 0, f"index={player.index}")
check("初始状态为空", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_down()
check("Enter DOWN -> Z DOWN", player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
check("Enter DOWN 期间的调用序列", fake.calls == ["press_key(z)"], f"calls={fake.calls}")
player.enter_up()
check("Enter UP -> Z UP", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("Enter UP 之后 index == 1", player.index == 1, f"index={player.index}")
check("Enter UP 的调用序列", fake.calls == ["press_key(z)", "release_key(z)"], f"calls={fake.calls}")

print("\n================ B. 连续音 1 2 3 ================")
fake, player = make_player("1 2 3")
expected = [("1", "keys=[z] mouse=[-]"), ("2", "keys=[x] mouse=[-]"), ("3", "keys=[c] mouse=[-]")]
for i, (note_name, expected_state) in enumerate(expected):
    note = player.current_note()
    player.enter_down()
    during = player.current_state_text()
    player.enter_up()
    check(f"第 {i+1} 次：{note_name} -> {expected_state}",
          during == expected_state and str(note.note) == note_name,
          f"note={note.note} during={during}")
check("最终 index == 3", player.index == 3, f"index={player.index}")
check("最后一个音符松开后不再留下任何按住（调音键也清掉）",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")

print("\n================ C. 长按 Enter（保持期间不松开） ================")
fake, player = make_player("1 2")
player.enter_down()
check("按下后 Z 保持 DOWN", player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
for _ in range(5):  # 模拟按住期间时间流逝（不做 sleep，只重复查询）
    held = player.current_state_text()
    if held != "keys=[z] mouse=[-]":
        break
check("保持期间状态一直是 Z DOWN（没有任何 UP）", held == "keys=[z] mouse=[-]",
      f"state={held}")
check("保持期间只有一次 press_key", fake.calls == ["press_key(z)"], f"calls={fake.calls}")
player.enter_up()
check("松开后当前音符键释放且 index 前进到 1（Task 27A：不再按下下一个音符）",
      player.current_state_text() == "keys=[-] mouse=[-]" and player.index == 1,
      f"state={player.current_state_text()} index={player.index}")
check("松开后只释放，绝不预先按下下一个音符键",
      fake.calls == ["press_key(z)", "release_key(z)"],
      f"calls={fake.calls}")
player.enter_down()
check("下一个音符只在下一次真正的 Enter DOWN 时才按下（X）",
      player.current_state_text() == "keys=[x] mouse=[-]"
      and fake.calls == ["press_key(z)", "release_key(z)", "press_key(x)"],
      f"state={player.current_state_text()} calls={fake.calls}")
player.enter_up()

print("\n================ D. 调音 [↑ 3] ================")
fake, player = make_player("[↑ 3]")
player.enter_down()
check("Enter DOWN -> C + Right DOWN",
      player.current_state_text() == "keys=[c] mouse=[right]",
      f"state={player.current_state_text()}")
player.enter_up()
check("Enter UP -> C 和 Right 全部 UP（这是最后一个音符）",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("实际调用序列正确",
      sorted(fake.calls) == sorted(["press_key(c)", "press_mouse(right)",
                                    "release_key(c)", "release_mouse(right)"]),
      f"calls={fake.calls}")

print("\n================ E. 调音连续 [↑ 3 4 5] ================")
fake, player = make_player("[↑ 3 4 5]")
expected_e = [("3", "c"), ("4", "v"), ("5", "b")]
for note_name, key in expected_e:
    player.enter_down()
    during = player.current_state_text()
    player.enter_up()
    after = player.current_state_text()
    check(f"{note_name} -> {key} + right", during == f"keys=[{key}] mouse=[right]",
          f"during={during}")
    check(f"{note_name} 松开后全部释放（Task 27A）", after == "keys=[-] mouse=[-]",
          f"after={after}")
right_presses = fake.calls.count("press_mouse(right)")
right_releases = fake.calls.count("release_mouse(right)")
check("每次 Enter DOWN 按下 right、每次 Enter UP 释放 right（3 个音符成对 3/3）",
      right_presses == 3 and right_releases == 3,
      f"press_mouse(right) x{right_presses} release_mouse(right) x{right_releases}")
check("区间结束后没有任何残留输入",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")

print("\n================ F. 混合谱 1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2] ================")
score_text = "1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]"
fake, player = make_player(score_text)
expected_f = [
    ("1", "keys=[z] mouse=[-]"),
    ("2", "keys=[x] mouse=[-]"),
    ("3", "keys=[c] mouse=[right]"),
    ("4", "keys=[v] mouse=[right]"),
    ("5", "keys=[b] mouse=[right]"),
    ("6", "keys=[n] mouse=[-]"),
    ("7", "keys=[m] mouse=[middle]"),
    ("1'", "keys=[,] mouse=[middle]"),
    ("2", "keys=[x] mouse=[left]"),
]
trace = []
for i, (note_name, expected_state) in enumerate(expected_f):
    player.enter_down()
    during = player.current_state_text()
    player.enter_up()
    trace.append((note_name, during))
    check(f"第 {i+1} 个音符 {note_name} -> {expected_state}", during == expected_state,
          f"during={during}")
check("混合谱共 9 个音符", len(trace) == 9, f"trace={trace}")
check("调音键按下次数与所在音符数一致（right 3 / middle 2 / left 1）",
      fake.calls.count("press_mouse(right)") == 3
      and fake.calls.count("press_mouse(middle)") == 2
      and fake.calls.count("press_mouse(left)") == 1,
      f"right={fake.calls.count('press_mouse(right)')} "
      f"middle={fake.calls.count('press_mouse(middle)')} "
      f"left={fake.calls.count('press_mouse(left)')}")
player.shutdown()
check("shutdown 后全部释放", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")

print("\n================ G. 播放结束 ================")
fake, player = make_player("1")
player.enter_down(); player.enter_up()
check("播完 index == 1 == len(notes)", player.index == 1 == player.note_count(),
      f"index={player.index} count={player.note_count()}")
check("播完 is_finished()", player.is_finished(), "is_finished=True")
fake.clear()
player.enter_down()
check("播完后 Enter DOWN 不产生任何输入",
      fake.calls == [] and player.current_state_text() == "keys=[-] mouse=[-]",
      f"calls={fake.calls} state={player.current_state_text()}")
player.enter_up()
check("播完后 Enter UP 也不产生任何输入、index 不变",
      fake.calls == [] and player.index == 1, f"calls={fake.calls} index={player.index}")

print("\n================ H. Esc（shutdown） ================")
fake, player = make_player("[↑ 3] 4")
player.enter_down()  # C + right 处于 DOWN
check("Esc 前 C+right 处于 DOWN", player.current_state_text() == "keys=[c] mouse=[right]",
      f"state={player.current_state_text()}")
player.shutdown()
check("shutdown 后全部释放", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
check("shutdown 确实发出了 release", "release_mouse(right)" in fake.calls and "release_key(c)" in fake.calls,
      f"calls={fake.calls}")
check("shutdown 后 enter_is_down 复位", player.enter_is_down is False,
      f"enter_is_down={player.enter_is_down}")

print("\n================ I. 重复 DOWN ================")
fake, player = make_player("1 2")
player.enter_down()
first_calls = list(fake.calls)
for _ in range(3):
    player.enter_down()   # 重复的 Enter DOWN（长按自动重复 / 重复调用）
check("重复 enter_down 不重复 press 当前音符",
      fake.calls == first_calls == ["press_key(z)"], f"calls={fake.calls}")
check("重复 enter_down 不推进 index", player.index == 0, f"index={player.index}")
check("重复 enter_down 后仍然只持有 Z", player.current_state_text() == "keys=[z] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_up()
check("松开后正常释放并前进到下一个音符（Task 27A：下一个音符此刻并未按下）",
      player.index == 1 and player.current_state_text() == "keys=[-] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
player.enter_down()
check("下一次 Enter DOWN 才按下 X",
      player.current_state_text() == "keys=[x] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_up()

print("\n================ 额外：重复 UP ================")
fake, player = make_player("1 2")
player.enter_down()
player.enter_up()   # index 前进到 1（最后一个音符）
calls_after_first_up = list(fake.calls)
player.enter_up()
player.enter_up()
check("重复 enter_up 不重复处理、不推进 index",
      fake.calls == calls_after_first_up and player.index == 1,
      f"calls={fake.calls} index={player.index}")
check("第一次松开后就已经全部释放（不残留）",
      calls_after_first_up == ["press_key(z)", "release_key(z)"],
      f"calls={calls_after_first_up}")
fake.clear()
player.enter_down()   # 播最后一个音符：需要真正按下 X
check("重复 UP 之后仍能正常播放（Enter DOWN 按下 X）",
      player.current_state_text() == "keys=[x] mouse=[-]" and fake.calls == ["press_key(x)"],
      f"state={player.current_state_text()} calls={fake.calls}")
player.enter_up()     # 最后一个音符松开 -> 全部释放
check("最后一个音符松开后播完并清空", player.index == 2 and player.is_finished()
      and player.current_state_text() == "keys=[-] mouse=[-]",
      f"index={player.index} state={player.current_state_text()}")
fake.clear()
player.enter_down()
check("播完之后再按 Enter 不产生任何输入",
      fake.calls == [] and player.current_state_text() == "keys=[-] mouse=[-]",
      f"calls={fake.calls} state={player.current_state_text()}")

print("\n================ 额外：中间音符的重复 UP ================")
fake, player = make_player("1 2 3")
player.enter_down()          # z
player.enter_up()            # 释放 z（Task 27A：不预先按下 x）
calls_after_up = list(fake.calls)
player.enter_up()            # 重复 UP：必须什么都不做
player.enter_up()
check("中间音符处重复 enter_up 不重复处理、不推进 index",
      fake.calls == calls_after_up and player.index == 1,
      f"calls={fake.calls} index={player.index}")
check("重复 UP 之后 executor 仍为空（Task 27A）",
      player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_down()
check("重复 UP 之后 Enter DOWN 正确播放下一个音符（X 被按下一次）",
      player.current_state_text() == "keys=[x] mouse=[-]"
      and fake.calls.count("press_key(x)") == 1,
      f"state={player.current_state_text()} press_key(x)x{fake.calls.count('press_key(x)')}")
player.enter_up()

print("\n================ 额外：空琴谱 ================")
fake, player = make_player("")
check("空琴谱 note_count == 0", player.note_count() == 0, f"count={player.note_count()}")
player.enter_down()
check("空琴谱 Enter DOWN 不产生任何输入",
      fake.calls == [] and player.current_state_text() == "keys=[-] mouse=[-]",
      f"calls={fake.calls}")
player.enter_up()
check("空琴谱 Enter UP 不报错、不推进", fake.calls == [] and player.index == 0,
      f"calls={fake.calls} index={player.index}")
player.shutdown()
check("空琴谱 shutdown 不报错", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")

print("\n================ 额外：release_all_on_enter_up 策略（方案 A 仍然可用） ================")
fake = FakeInput()
player = FixedScorePlayer(parse_score_notes("[↑ 3 4]"), io_module=fake,
                          release_all_on_enter_up=True, min_hold_ms=0)
player.enter_down()
check("策略 A 下 Enter DOWN 仍是 C+right", player.current_state_text() == "keys=[c] mouse=[right]",
      f"state={player.current_state_text()}")
player.enter_up()
check("策略 A 下 Enter UP 释放全部输入", player.current_state_text() == "keys=[-] mouse=[-]",
      f"state={player.current_state_text()}")
player.enter_down()
check("策略 A 下下一个音符会重新按下调音键（right 被按两次）",
      player.current_state_text() == "keys=[v] mouse=[right]"
      and fake.calls.count("press_mouse(right)") == 2,
      f"state={player.current_state_text()} press_mouse(right)x{fake.calls.count('press_mouse(right)')}")
player.shutdown()

print("\n================ 额外：release 必须先于 advance ================")
fake, player = make_player("1 2")
player.enter_down()
fake.clear()
player.enter_up()
calls_during_up = list(fake.calls)
check("enter_up 只释放当前音符的键，不预先按下下一个音符（Task 27A）",
      calls_during_up == ["release_key(z)"] and player.index == 1,
      f"calls={calls_during_up} index_after={player.index}")

print()
failed = [name for name, ok in results if not ok]
print(f"总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过")
