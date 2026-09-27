"""Task 9 纯逻辑测试：只检查 Python 对象状态，不发送任何真实键盘/鼠标输入。

断言方式：对每个音符打印 expected / actual，并逐项精确比对。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from score import (  # noqa: E402
    MODIFIER_FLAT,
    MODIFIER_HALF,
    MODIFIER_NORMAL,
    MODIFIER_SHARP,
    Note,
    parse_score,
    parse_score_notes,
)
from playback import PlaybackController, PlaybackState, state_for_note  # noqa: E402

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def show(label, keys, mouse):
    return f"{label}: keys={sorted(keys)} mouse={sorted(mouse)}"


def play_all(controller):
    """完整走一遍：start -> 记录 -> stop，返回 [(note_name, keys, mouse), ...]"""
    played = []
    while not controller.is_finished():
        state = controller.start_current()
        played.append((controller.current_note().note, sorted(state.keys), sorted(state.mouse_buttons)))
        controller.stop_current_and_advance()
    return played


print("================ 测试 1：单音 ================")
c = PlaybackController(parse_score_notes("1"))
check("初始 index == 0", c.index == 0, f"index={c.index}")
check("初始没有正在播放的音符", not c.has_current(), f"playing={c.is_playing}")
check("初始输入状态为空", c.current_state().keys == frozenset() and c.current_state().mouse_buttons == frozenset(),
      f"state={c.current_state().as_dict()}")
st = c.start_current()
check("1 -> z + 无鼠标", st.keys == {"z"} and st.mouse_buttons == set(),
      show("actual", st.keys, st.mouse_buttons) + " | expected: keys=['z'] mouse=[]")
c.stop_current_and_advance()
check("stop 之后 index == 1 且状态清空",
      c.index == 1 and c.current_state().keys == frozenset() and not c.has_current(),
      f"index={c.index} state={c.current_state().as_dict()} playing={c.is_playing}")

print("\n================ 测试 2：普通连续音符 1 2 3 ================")
c = PlaybackController(parse_score_notes("1 2 3"))
expected2 = [("1", ["z"], []), ("2", ["x"], []), ("3", ["c"], [])]
played = []
while not c.is_finished():
    st = c.start_current()
    played.append((c.current_note().note, sorted(st.keys), sorted(st.mouse_buttons)))
    c.stop_current_and_advance()
for got, exp in zip(played, expected2):
    check(f"{exp[0]} -> {exp[1]} (expected) == {got[1]} (actual)", got == exp, f"got={got} exp={exp}")
check("最终 index == 3", c.index == 3, f"index={c.index}")
check("最终状态为空", c.current_state().keys == frozenset() and c.current_state().mouse_buttons == frozenset(),
      f"state={c.current_state().as_dict()}")

print("\n================ 测试 3：升调连续音 [↑ 3 4 5] ================")
c = PlaybackController(parse_score_notes("[↑ 3 4 5]"))
expected3 = [("3", ["c"], ["right"]), ("4", ["v"], ["right"]), ("5", ["b"], ["right"])]
played = []
while not c.is_finished():
    st = c.start_current()
    played.append((c.current_note().note, sorted(st.keys), sorted(st.mouse_buttons)))
    c.stop_current_and_advance()
for got, exp in zip(played, expected3):
    check(f"{exp[0]} -> {exp[1]} + {exp[2]}", got == exp, f"got={got} exp={exp}")

print("\n================ 测试 4：调音切换 [↑ 3 4] 5 [↓ 6 7] ================")
c = PlaybackController(parse_score_notes("[↑ 3 4] 5 [↓ 6 7]"))
expected4 = [("3", ["c"], ["right"]), ("4", ["v"], ["right"]),
             ("5", ["b"], []),
             ("6", ["n"], ["left"]), ("7", ["m"], ["left"])]
played = []
states = []
while not c.is_finished():
    st = c.start_current()
    played.append((c.current_note().note, sorted(st.keys), sorted(st.mouse_buttons)))
    states.append(st)
    c.stop_current_and_advance()
for got, exp in zip(played, expected4):
    check(f"{exp[0]} -> {exp[1]} + {exp[2]}", got == exp, f"got={got} exp={exp}")
check("4 -> 5 时 right 消失（4 有 right，5 没有）",
      "right" in states[1].mouse_buttons and "right" not in states[2].mouse_buttons,
      f"4.mouse={sorted(states[1].mouse_buttons)} 5.mouse={sorted(states[2].mouse_buttons)}")
check("5 -> 6 时变成 left",
      states[2].mouse_buttons == frozenset() and states[3].mouse_buttons == frozenset({"left"}),
      f"5.mouse={sorted(states[2].mouse_buttons)} 6.mouse={sorted(states[3].mouse_buttons)}")

print("\n================ 测试 5：半音 [~ 1 2] ================")
c = PlaybackController(parse_score_notes("[~ 1 2]"))
expected5 = [("1", ["z"], ["middle"]), ("2", ["x"], ["middle"])]
played = []
while not c.is_finished():
    st = c.start_current()
    played.append((c.current_note().note, sorted(st.keys), sorted(st.mouse_buttons)))
    c.stop_current_and_advance()
for got, exp in zip(played, expected5):
    check(f"{exp[0]} -> {exp[1]} + {exp[2]}", got == exp, f"got={got} exp={exp}")

print("\n================ 测试 6：空谱 ================")
notes = parse_score_notes("")
check("parse_score_notes('') 得到空列表", notes == [], f"notes={notes}")
c = PlaybackController(notes)
check("空谱构造不崩溃", c is not None, f"repr={c!r}")
check("空谱初始 index == 0", c.index == 0, f"index={c.index}")
check("空谱初始就是 finished", c.is_finished(), f"is_finished={c.is_finished()}")
check("空谱 current_note() 返回 None", c.current_note() is None, f"note={c.current_note()}")
st = c.start_current()
check("空谱 start_current() 不报错且状态为空",
      st.keys == frozenset() and st.mouse_buttons == frozenset(),
      f"state={st.as_dict()}")
c.stop_current_and_advance()
check("空谱 stop_current_and_advance() 不推进 index（仍无 current）",
      c.index == 0 and not c.has_current(), f"index={c.index} playing={c.is_playing}")

print("\n================ 测试 7：重复 start_current ================")
c = PlaybackController(parse_score_notes("1 2"))
s1 = c.start_current()
idx1 = c.index
s2 = c.start_current()
idx2 = c.index
s3 = c.start_current()
check("重复 start 不推进 index", idx1 == idx2 == c.index == 0, f"index after 1st={idx1} after 2nd={idx2} after 3rd={c.index}")
check("重复 start 状态完全一致", s1 == s2 == s3 == PlaybackState(frozenset({"z"}), frozenset()),
      f"s1={s1.as_dict()} s2={s2.as_dict()} s3={s3.as_dict()}")
check("重复 start 后仍在播放且 current_note 不变",
      c.has_current() and c.current_note().note == "1",
      f"playing={c.is_playing} note={c.current_note()}")
c.stop_current_and_advance()
check("只推进一次（index == 1）", c.index == 1, f"index={c.index}")
c.start_current()
check("停止后再次 start 拿到第二个音符 2 -> x", c.current_state().keys == {"x"}, f"state={c.current_state().as_dict()}")

print("\n================ 测试 8：reset ================")
c = PlaybackController(parse_score_notes("1 2 [↑ 3] 4"))
c.start_current(); c.stop_current_and_advance()
c.start_current(); c.stop_current_and_advance()
c.start_current()
check("播放到第 3 个音符时 playing=True, index=2",
      c.has_current() and c.index == 2 and c.current_state().keys == {"c"},
      f"index={c.index} state={c.current_state().as_dict()} playing={c.is_playing}")
c.reset()
check("reset 后 index == 0", c.index == 0, f"index={c.index}")
check("reset 后没有正在播放的音符", not c.has_current() and not c.is_playing, f"playing={c.is_playing}")
check("reset 后输入状态为空", c.current_state().keys == frozenset() and c.current_state().mouse_buttons == frozenset(),
      f"state={c.current_state().as_dict()}")
st = c.start_current()
check("reset 后可以重新从头播放（又回到 1 -> z）",
      st.keys == {"z"} and c.index == 0, f"state={st.as_dict()} index={c.index}")

print("\n================ 测试 9：末尾行为 ================")
c = PlaybackController(parse_score_notes("1 2"))
c.start_current(); c.stop_current_and_advance()
c.start_current(); c.stop_current_and_advance()
check("完整播放后 index == len(notes)", c.index == len(c.notes) == 2, f"index={c.index} len={len(c.notes)}")
check("末尾 is_finished() == True", c.is_finished(), f"is_finished={c.is_finished()}")
check("末尾 current_note() == None", c.current_note() is None, f"note={c.current_note()}")
st = c.start_current()
check("末尾再次 start_current() 不报错且状态为空",
      st.keys == frozenset() and st.mouse_buttons == frozenset(),
      f"state={st.as_dict()}")
check("末尾再次 start 不改变 index", c.index == 2, f"index={c.index}")
c.stop_current_and_advance()
check("末尾 stop 不越界增加 index（没有 current 时不动）", c.index == 2, f"index={c.index}")

print("\n================ 额外：调音键是持续状态（不抖动） ================")
# 3 → 4 → 5 都在 sharp 区间内，三次 start 的 mouse 状态必须始终是 {right}
c = PlaybackController(parse_score_notes("1 2 [↑ 3 4 5] 6"))
seq = []
while not c.is_finished():
    st = c.start_current()
    seq.append((c.current_note().note, set(st.mouse_buttons)))
    c.stop_current_and_advance()
check("区间内 3/4/5 每一步都是 right（不出现 UP->DOWN 抖动）",
      seq[2] == ("3", {"right"}) and seq[3] == ("4", {"right"}) and seq[4] == ("5", {"right"}),
      f"sequence={[(n, sorted(m)) for n, m in seq]}")
check("区间外 2/6 都是无鼠标键",
      seq[1] == ("2", set()) and seq[5] == ("6", set()),
      f"2.mouse={sorted(seq[1][1])} 6.mouse={sorted(seq[5][1])}")

print("\n================ 额外：state_for_note 直接映射 ================")
mapping = [
    (("1", "z", MODIFIER_NORMAL), {"z"}, set()),
    (("3", "c", MODIFIER_SHARP), {"c"}, {"right"}),
    (("4", "v", MODIFIER_FLAT), {"v"}, {"left"}),
    (("6", "n", MODIFIER_HALF), {"n"}, {"middle"}),
]
for (note, key, modifier), exp_keys, exp_mouse in mapping:
    st = state_for_note(Note(note, key, modifier))
    check(f"state_for_note({note}, {key}, {modifier}) -> keys={sorted(exp_keys)} mouse={sorted(exp_mouse)}",
          st.keys == exp_keys and st.mouse_buttons == exp_mouse,
          f"actual keys={sorted(st.keys)} mouse={sorted(st.mouse_buttons)}")

print("\n================ 额外：非 Note 输入会被拒绝 ================")
try:
    PlaybackController([{"note": "1", "key": "z", "modifier": "normal"}])
    check("传入 dict 列表应报 TypeError", False, "no exception raised")
except TypeError as exc:
    check("传入 dict 列表报 TypeError（不静默接受）", True, f"TypeError: {exc}")
except Exception as exc:  # noqa: BLE001
    check("传入 dict 列表应报 TypeError", False, f"wrong exception: {type(exc).__name__}")

print("\n================ 额外：用 parse_score (dict) 转 Note 也能用 ================")
dict_notes = parse_score("1 [↑ 2]")
notes_from_dicts = [Note(n["note"], n["key"], n["modifier"]) for n in dict_notes]
c = PlaybackController(notes_from_dicts)
played = play_all(c)
check("从 parse_score 的 dict 转成 Note 后播放结果正确",
      played == [("1", ["z"], []), ("2", ["x"], ["right"])],
      f"played={played}")

print("\n================ 额外：完整走一遍混合谱（回归） ================")
c = PlaybackController(parse_score_notes("1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]"))
played = play_all(c)
# 1 2 = normal；3 4 5 = sharp(right)；6 = normal；7 1' = half(middle)；2 = flat(left)
expected_all = [("1", ["z"], []), ("2", ["x"], []),
                ("3", ["c"], ["right"]), ("4", ["v"], ["right"]), ("5", ["b"], ["right"]),
                ("6", ["n"], []),
                ("7", ["m"], ["middle"]), ("1'", [","], ["middle"]),
                ("2", ["x"], ["left"])]
check("混合谱 9 个音符全部正确", played == expected_all, f"played={played}")
check("混合谱结束后 index == 9 且状态为空",
      c.index == 9 and c.current_state().keys == frozenset(),
      f"index={c.index} state={c.current_state().as_dict()}")

print()
failed = [name for name, ok in results if not ok]
print(f"总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过")
