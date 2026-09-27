"""Task 27A 测试：Enter Up → 本次音符的全部输出必须立即释放。

覆盖任务书 A–F：
  A. Enter Down → 音符键 DOWN；Enter Up → 音符键 UP
  B. Enter Down → 鼠标调音键 DOWN；Enter Up → 鼠标键 UP
  C. Down/Up 重复 20 次：每次都是 DOWN → UP
  D. Enter Up 后立即检查：所有程序产生的键与鼠标键都必须为空
  E. 连续快速 Down/Up 50 次
  F. timer / generation 场景：旧 timer 不能阻止本次 Enter Up 的释放
  G. 真实 config 的 min_hold_ms 下，正常长按松开立即释放
  H. 真实 input.py 钩子回调路径（不注入任何真实按键，IO 用记录器替身）

安全：全部使用记录器 IO 替身，不产生任何真实键鼠输入。
"""

import ctypes
import os
import sys
import time
from ctypes import wintypes

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import harmonica_app  # noqa: E402
import input as real_input  # noqa: E402
from input import KBDLLHOOKSTRUCT  # noqa: E402
from score import parse_score_notes  # noqa: E402

VK_ENTER = 0x0D
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  " + str(detail)) if detail else ""))


class RecorderIO:
    """input.py 替身：只记录 press/release，不产生任何真实输入。"""

    def __init__(self):
        self.events = []
        self._held = set()
        self._mouse = set()

    def press_key(self, k):
        self.events.append(("press_key", str(k)))
        self._held.add(str(k))

    def release_key(self, k):
        self.events.append(("release_key", str(k)))
        self._held.discard(str(k))

    def press_mouse(self, b):
        self.events.append(("press_mouse", str(b)))
        self._mouse.add(str(b))

    def release_mouse(self, b):
        self.events.append(("release_mouse", str(b)))
        self._mouse.discard(str(b))

    def move_mouse(self, x, y):
        pass

    def release_all(self):
        self.events.append(("release_all",))
        self._held.clear()
        self._mouse.clear()

    def held_keys(self):
        return set(self._held)

    def held_mouse_buttons(self):
        return set(self._mouse)


def make_player(score, min_hold_ms=0):
    io = RecorderIO()
    player = harmonica_app.FixedScorePlayer(
        parse_score_notes(score), io_module=io, min_hold_ms=min_hold_ms)
    return io, player


print("=" * 70)
print("Task 27A - Enter Up -> 全部输出释放 测试")
print("=" * 70)

# ---------------- A. 键盘 ----------------
print("--- A. Enter Down/Up -> 音符键 DOWN/UP ---")
io, player = make_player("1 2 3", min_hold_ms=0)
check("A0 初始无输入", player.current_state_text() == "keys=[-] mouse=[-]",
      player.current_state_text())
player.enter_down()
check("A1 Enter Down -> 当前音符键 DOWN", player.current_state_text() == "keys=[z] mouse=[-]",
      player.current_state_text())
check("A2 键盘确实记录了按下", io.held_keys() == {"z"}, io.held_keys())
player.enter_up()
check("A3 Enter Up -> 音符键 UP", player.current_state_text() == "keys=[-] mouse=[-]",
      player.current_state_text())
check("A4 键盘 held 为空", io.held_keys() == set(), io.held_keys())
check("A5 不依赖下一次 Enter（松开后立刻为空）", io._mouse == set())

# ---------------- B. 鼠标调音键 ----------------
print("--- B. Enter Down/Up -> 鼠标调音键 DOWN/UP ---")
io, player = make_player("[\u2191 1 2] 3", min_hold_ms=0)
player.enter_down()
check("B1 Enter Down -> 键+右键 DOWN",
      player.current_state_text() == "keys=[z] mouse=[right]", player.current_state_text())
check("B2 鼠标确实记录了按下", io.held_mouse_buttons() == {"right"}, io.held_mouse_buttons())
player.enter_up()
check("B3 Enter Up -> 鼠标键 UP", player.current_state_text() == "keys=[-] mouse=[-]",
      player.current_state_text())
check("B4 鼠标 held 为空", io.held_mouse_buttons() == set(), io.held_mouse_buttons())

# ---------------- C. 20 次 Down/Up ----------------
print("--- C. 20 次 Down/Up ---")
LONG_SCORE = " ".join(["1", "2", "3", "4", "5", "6", "7"] * 12)   # 84 个音符
io, player = make_player(LONG_SCORE, min_hold_ms=0)
ok_down_up = True
bad = ""
for i in range(20):
    player.enter_down()
    if player.current_state_text() == "keys=[-] mouse=[-]":
        ok_down_up = False
        bad = "第%d次 Down 后仍为空" % (i + 1)
        break
    player.enter_up()
    if player.current_state_text() != "keys=[-] mouse=[-]":
        ok_down_up = False
        bad = "第%d次 Up 后仍按着 %s" % (i + 1, player.current_state_text())
        break
check("C1 20 次 Down/Up 每次都 DOWN -> UP", ok_down_up, bad or "20/20 OK")
check("C2 20 次后无残留", io.held_keys() == set() and io.held_mouse_buttons() == set(),
      "keys=%s mouse=%s" % (io.held_keys(), io.held_mouse_buttons()))
# 事件序列不得出现 DOWN -> DOWN（同一个键连续按两次不释放）
seq = [e for e in io.events if e[0] in ("press_key", "release_key")]
dup = any(seq[i][0] == "press_key" and seq[i + 1][0] == "press_key" for i in range(len(seq) - 1))
check("C3 事件序列无 DOWN -> DOWN", not dup, seq[:8])

# ---------------- D. Enter Up 后立即为空 ----------------
print("--- D. Enter Up 后立即检查 ---")
io, player = make_player("1 2 3 4", min_hold_ms=0)
for _ in range(5):
    player.enter_down()
    player.enter_up()
    if not (io.held_keys() == set() and io.held_mouse_buttons() == set()):
        break
check("D1 Enter Up 后立即：程序产生的键全为空", io.held_keys() == set(), io.held_keys())
check("D2 Enter Up 后立即：程序产生的鼠标键全为空",
      io.held_mouse_buttons() == set(), io.held_mouse_buttons())

# ---------------- E. 50 次快速 Down/Up ----------------
print("--- E. 50 次快速 Down/Up ---")
io, player = make_player(LONG_SCORE, min_hold_ms=0)
ok_fast = True
bad_fast = ""
pressed_something = False
t0 = time.monotonic()
for i in range(50):
    player.enter_down()
    if io.held_keys() or io.held_mouse_buttons():
        pressed_something = True
    player.enter_up()
    if io.held_keys() != set() or io.held_mouse_buttons() != set():
        ok_fast = False
        bad_fast = "第%d次后仍按着 keys=%s mouse=%s" % (i + 1, io.held_keys(), io.held_mouse_buttons())
        break
dt = (time.monotonic() - t0) * 1000
check("E1 50 次快速 Down/Up 全部释放干净", ok_fast, bad_fast or ("50/50 OK, %.0fms" % dt))
check("E2 每轮确实按下过音符（不是空转）", pressed_something)

# ---------------- F. timer / generation ----------------
print("--- F. timer / generation 场景 ---")
io, player = make_player("1 2 3 4", min_hold_ms=50)
player.enter_down()
player.enter_up()          # 极短按住 -> 会挂一个 timer
time.sleep(0.15)           # 等 timer 到点
check("F1 极短按住：timer 到点后全部释放",
      player.current_state_text() == "keys=[-] mouse=[-]" and io.held_keys() == set(),
      player.current_state_text())
check("F2 到点后 timer 引用已清空", player._pending_timer is None)

# 旧 timer 不能阻止/干扰后续 Enter Up 的释放
io, player = make_player("1 2 3 4", min_hold_ms=50)
player.enter_down()
player.enter_up()          # 挂 T1
player.enter_down()        # 让 T1 失效，并按下一个音符
player.enter_up()          # 挂 T2
time.sleep(0.2)
check("F3 旧 timer 失效后不影响：最终全部释放",
      player.current_state_text() == "keys=[-] mouse=[-]" and io.held_keys() == set(),
      player.current_state_text())
check("F4 generation 已推进", player._timer_generation >= 2, player._timer_generation)

# ---------------- G. 真实 config（min_hold_ms）长按 ----------------
print("--- G. 真实 config min_hold_ms 长按松开 ---")
real_mh = harmonica_app.load_min_hold_ms(os.path.join(PROJECT_DIR, "config.json"))
check("G0 读到真实 min_hold_ms", isinstance(real_mh, int) and real_mh >= 0, real_mh)
io, player = make_player("1 2 3", min_hold_ms=real_mh)
player.enter_down()
time.sleep((real_mh + 30) / 1000.0)     # 长按超过最小保持时间
t_up = time.monotonic()
player.enter_up()
dt_up = (time.monotonic() - t_up) * 1000
check("G1 长按松开后立即为空（同步释放，无延迟）",
      player.current_state_text() == "keys=[-] mouse=[-]" and io.held_keys() == set(),
      "耗时 %.1fms  state=%s" % (dt_up, player.current_state_text()))
check("G2 松开后没有挂起 timer", player._pending_timer is None)

# ---------------- H. 真实 input.py 钩子回调路径 ----------------
print("--- H. 真实 input.py 钩子回调路径 ---")
io, player = make_player("1 2 3", min_hold_ms=0)
real_input.set_enter_callbacks(on_down=player.enter_down, on_up=player.enter_up)
real_input.set_escape_callback(lambda: None)
real_input.set_reset_callback(lambda: None)


def post(vk, message):
    info = KBDLLHOOKSTRUCT()
    info.vkCode = vk
    info.scanCode = 0
    info.flags = 0
    info.time = 0
    info.dwExtraInfo = 0
    return real_input._hook_callback(0, message, ctypes.addressof(info))


rv_down = post(VK_ENTER, WM_KEYDOWN)
real_input._drain_callbacks(timeout=1.0)
after_down = player.current_state_text()
rv_up = post(VK_ENTER, WM_KEYUP)
real_input._drain_callbacks(timeout=1.0)
after_up = player.current_state_text()

check("H1 Enter 被吞掉（返回 1/1）", rv_down == 1 and rv_up == 1, (rv_down, rv_up))
check("H2 钩子 Enter DOWN -> 音符键 DOWN", after_down == "keys=[z] mouse=[-]", after_down)
check("H3 钩子 Enter UP -> 全部释放", after_up == "keys=[-] mouse=[-]", after_up)
check("H4 钩子路径下 held 两个集合都为空",
      io.held_keys() == set() and io.held_mouse_buttons() == set(),
      "keys=%s mouse=%s" % (io.held_keys(), io.held_mouse_buttons()))
# 连续 20 次走真实钩子路径
ok_hook = True
bad_hook = ""
for i in range(20):
    post(VK_ENTER, WM_KEYDOWN)
    real_input._drain_callbacks(timeout=1.0)
    post(VK_ENTER, WM_KEYUP)
    real_input._drain_callbacks(timeout=1.0)
    if io.held_keys() != set() or io.held_mouse_buttons() != set():
        ok_hook = False
        bad_hook = "第%d次后 keys=%s mouse=%s" % (i + 1, io.held_keys(), io.held_mouse_buttons())
        break
check("H5 真实钩子路径连续 20 次 Down/Up 每次释放干净", ok_hook, bad_hook or "20/20 OK")
real_input.set_enter_callbacks(on_down=None, on_up=None)

npass = sum(1 for (_n, ok) in results if ok)
nfail = len(results) - npass
print("TOTAL PASS=%d FAIL=%d" % (npass, nfail))
sys.exit(0 if nfail == 0 else 1)
