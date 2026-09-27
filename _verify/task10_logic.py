"""Task 10 纯逻辑测试：验证 executor 的差分行为与调用顺序。

做法：把 input.py 的 press_key / release_key / press_mouse / release_mouse
换成记录器（executor 会在构造时保存这些引用），然后检查调用序列。
不产生任何真实输入。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import input as io  # noqa: E402
from playback import PlaybackState  # noqa: E402
from playback_executor import PlaybackExecutor  # noqa: E402
from score import parse_score_notes  # noqa: E402

calls = []


def fake_press_key(key):
    calls.append(f"press_key({key})")


def fake_release_key(key):
    calls.append(f"release_key({key})")


def fake_press_mouse(button):
    calls.append(f"press_mouse({button})")


def fake_release_mouse(button):
    calls.append(f"release_mouse({button})")


# 替换 input.py 的四个 API（executor 构造时会取走这些引用）
io.press_key = fake_press_key
io.release_key = fake_release_key
io.press_mouse = fake_press_mouse
io.release_mouse = fake_release_mouse

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if detail:
        print(f"        {detail}")


def S(keys=(), buttons=()):
    return PlaybackState(frozenset(keys), frozenset(buttons))


def new_executor():
    calls.clear()
    return PlaybackExecutor()


def run_case(name, steps, expected_calls, expected_final):
    """steps: [(new_state), ...]；比较整个调用序列与最终状态。"""
    executor = new_executor()
    for state in steps:
        executor.apply(state)
    ok_calls = calls == expected_calls
    ok_state = executor.current_state() == expected_final
    check(name, ok_calls and ok_state,
          f"calls      = {calls}\n        expected   = {expected_calls}\n        final state= keys={sorted(executor.current_state().keys)} mouse={sorted(executor.current_state().mouse_buttons)}")
    return executor


print("================ 场景 1：空 -> Z ================")
run_case("空 -> {\"z\"}：只按 Z",
         [S(["z"])],
         ["press_key(z)"],
         S(["z"]))

print("\n================ 场景 2：Z -> X ================")
run_case("Z -> X：先放 Z 再按 X",
         [S(["z"]), S(["x"])],
         ["press_key(z)", "release_key(z)", "press_key(x)"],
         S(["x"]))

print("\n================ 场景 3：Z+Right -> X+Right（right 必须保持） ================")
run_case("Z+Right -> X+Right：right 不 release / 不 re-press",
         [S(["z"], ["right"]), S(["x"], ["right"])],
         ["press_key(z)", "press_mouse(right)", "release_key(z)", "press_key(x)"],
         S(["x"], ["right"]))

print("\n================ 场景 4：X+Right -> B ================")
run_case("X+Right -> B：放 X 和 right，按 B",
         [S(["x"], ["right"]), S(["b"])],
         ["press_key(x)", "press_mouse(right)", "release_key(x)", "release_mouse(right)", "press_key(b)"],
         S(["b"]))

print("\n================ 场景 5：normal -> sharp ================")
run_case("C(normal) -> V(sharp)：放 C、按 V、按 right",
         [S(["c"]), S(["v"], ["right"])],
         ["press_key(c)", "release_key(c)", "press_key(v)", "press_mouse(right)"],
         S(["v"], ["right"]))

print("\n================ 场景 6：sharp -> flat ================")
run_case("C+right -> V+left：放 C 和 right，按 V 和 left",
         [S(["c"], ["right"]), S(["v"], ["left"])],
         ["press_key(c)", "press_mouse(right)", "release_key(c)", "release_mouse(right)", "press_key(v)", "press_mouse(left)"],
         S(["v"], ["left"]))

print("\n================ 场景 7：清空状态 ================")
run_case("Z+right -> empty：全部释放",
         [S(["z"], ["right"]), S()],
         ["press_key(z)", "press_mouse(right)", "release_key(z)", "release_mouse(right)"],
         S())

print("\n================ 场景 8：相同状态（不得有任何调用） ================")
executor = new_executor()
executor.apply(S(["z"], ["right"]))
calls.clear()
executor.apply(S(["z"], ["right"]))
executor.apply(S(["z"], ["right"]))
check("相同状态连续 apply：没有任何 press/release",
      calls == [], f"calls={calls}")
check("相同状态后 state 不变",
      executor.current_state() == S(["z"], ["right"]),
      f"state=keys={sorted(executor.current_state().keys)} mouse={sorted(executor.current_state().mouse_buttons)}")
executor.release_all()

print("\n================ 场景 9：调音区间内连续三个音符（right 只按一次） ================")
executor = new_executor()
executor.apply(S(["c"], ["right"]))     # 3 sharp
executor.apply(S(["v"], ["right"]))     # 4 sharp
executor.apply(S(["b"], ["right"]))     # 5 sharp
right_presses = calls.count("press_mouse(right)")
right_releases = calls.count("release_mouse(right)")
check("区间内 right 只被按下一次",
      right_presses == 1, f"press_mouse(right) x{right_presses} in {calls}")
check("区间内 right 从未被释放",
      right_releases == 0, f"release_mouse(right) x{right_releases} in {calls}")
check("区间内三个音符键各自按下/释放正确",
      calls == ["press_key(c)", "press_mouse(right)", "release_key(c)", "press_key(v)",
                "release_key(v)", "press_key(b)"],
      f"calls={calls}")
executor.release_all()

print("\n================ 场景 10：release_all ================")
executor = new_executor()
executor.apply(S(["z"], ["right"]))
calls.clear()
executor.release_all()
check("release_all 释放自己持有的全部输入",
      sorted(calls) == ["release_key(z)", "release_mouse(right)"], f"calls={calls}")
check("release_all 之后内部 state 为空",
      executor.current_state() == S(), f"state={executor.current_state()}")
calls.clear()
executor.release_all()
check("release_all 再次调用不产生任何调用（已无持有）", calls == [], f"calls={calls}")

print("\n================ 场景 11：empty -> empty ================")
executor = new_executor()
executor.apply(S())
check("空 -> 空：没有任何调用", calls == [], f"calls={calls}")
check("空 -> 空：状态为空", executor.current_state() == S(), "state empty")

print("\n================ 场景 12：apply 参数类型检查 ================")
executor = new_executor()
try:
    executor.apply({"keys": {"z"}, "mouse_buttons": set()})
    check("apply(dict) 应报 TypeError", False, "no exception raised")
except TypeError as exc:
    check("apply(dict) 报 TypeError（不静默接受）", True, f"TypeError: {exc}")
except Exception as exc:  # noqa: BLE001
    check("apply(dict) 应报 TypeError", False, f"wrong exception: {type(exc).__name__}")

print("\n================ 场景 13：多键状态同时切换 ================")
run_case("Z+X -> V+B：两个旧键都释放，两个新键都按下",
         [S(["z", "x"]), S(["v", "b"])],
         ["press_key(x)", "press_key(z)", "release_key(x)", "release_key(z)", "press_key(b)", "press_key(v)"],
         S(["v", "b"]))

print("\n================ 场景 14：同时带多个鼠标键 ================")
run_case("left+right -> middle：两个都放，按 middle",
         [S(["z"], ["left", "right"]), S(["z"], ["middle"])],
         ["press_key(z)", "press_mouse(left)", "press_mouse(right)",
          "release_mouse(left)", "release_mouse(right)", "press_mouse(middle)"],
         S(["z"], ["middle"]))

print("\n================ 场景 15：与 playback.py 连接（完整混合谱，纯逻辑） ================")
from playback import PlaybackController  # noqa: E402

controller = PlaybackController(parse_score_notes("1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]"))
executor = new_executor()
trace = []
while not controller.is_finished():
    state = controller.start_current()
    before = executor.current_state()
    executor.apply(state)
    trace.append((controller.current_note().note, sorted(state.keys), sorted(state.mouse_buttons)))
    controller.stop_current_and_advance()

print(f"        trace = {trace}")
check("混合谱逐音符状态正确",
      trace == [("1", ["z"], []), ("2", ["x"], []), ("3", ["c"], ["right"]),
                ("4", ["v"], ["right"]), ("5", ["b"], ["right"]), ("6", ["n"], []),
                ("7", ["m"], ["middle"]), ("1'", [","], ["middle"]), ("2", ["x"], ["left"])],
      f"trace={trace}")
check("混合谱期间 right 只按一次、middle 只按一次、left 只按一次",
      calls.count("press_mouse(right)") == 1
      and calls.count("press_mouse(middle)") == 1
      and calls.count("press_mouse(left)") == 1,
      f"right={calls.count('press_mouse(right)')} middle={calls.count('press_mouse(middle)')} left={calls.count('press_mouse(left)')}")
check("混合谱期间每个鼠标键的 release 次数与 press 次数一致（除 left 外都在切换时释放）",
      calls.count("release_mouse(right)") == 1
      and calls.count("release_mouse(middle)") == 1,
      f"release right={calls.count('release_mouse(right)')} middle={calls.count('release_mouse(middle)')}")
print(f"        full call sequence = {calls}")
executor.release_all()
check("混合谱结束后 release_all 把 left 也释放掉",
      "release_mouse(left)" in calls and executor.current_state() == S(),
      f"tail calls={calls[-3:]}")

print("\n================ 场景 16：executor 不使用 input.release_all ================")
# 行为验证（比字符串搜索可靠）：把 input.release_all 换成"被调用就抛异常"的哨兵，
# 再让 executor.release_all() 工作一次。如果它偷偷调用了那个全局兜底，就会抛异常。
_original_io_release_all = io.release_all


def sentinel_io_release_all():
    raise AssertionError("executor 不应该调用 input.release_all()")


io.release_all = sentinel_io_release_all
executor = new_executor()
executor.apply(S(["z"], ["right"]))
calls.clear()
try:
    executor.release_all()
    sentinel_ok = True
except AssertionError as exc:
    sentinel_ok = False
    print(f"        sentinel tripped: {exc}")
finally:
    io.release_all = _original_io_release_all

check("executor.release_all() 不调用 input.release_all()（哨兵未被触发）",
      sentinel_ok, f"sentinel_ok={sentinel_ok}")
check("executor.release_all() 只做逐个 release",
      calls == ["release_key(z)", "release_mouse(right)"], f"calls={calls}")

print()
failed = [name for name, ok in results if not ok]
print(f"总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过")
