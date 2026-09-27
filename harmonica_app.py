"""Enter -> 演奏 的接线（Task 11 / Task 12）。

把已经验证过的几个模块接起来：

    input.py（Enter Hook）
        -> PlaybackController（当前播放哪个音符）
        -> PlaybackExecutor（差分成真实的 press / release）
        -> input.py（真实键盘 / 鼠标）

这里只做"接线 + 状态判断"，不重新实现任何已有逻辑：
    - 音符顺序、调音状态由 score.py + playback.py 决定
    - 按下 / 释放的实际差异由 playback_executor.py 决定
    - 真实输入由 input.py 负责

Task 12 增加 min_hold_ms（最小音符持续时间）：
    Enter UP 时如果当前音符还没播够 min_hold_ms，就**不立即释放**，而是挂一个
    threading.Timer 等待剩余时间；到点后再释放并推进 index。
    Timer 回调里只用 generation 守卫做判断，**不阻塞、不 sleep**（钩子回调同样不阻塞）。
    如果期间又按下了 Enter，或者发生了 shutdown/release_all，旧 timer 会被 generation
    失效掉，绝不会去释放"新的音符"。

main.py 和测试脚本都用这一个类，避免测试里复制一份接线逻辑。
"""

import json
import threading
import time
from typing import Optional, Sequence

import input as io
from playback import PlaybackController, PlaybackState
from playback_executor import PlaybackExecutor
from score import Note

# min_hold_ms 默认值（config.json 里没有或读不到时使用）
DEFAULT_MIN_HOLD_MS = 50
CONFIG_PATH = "config.json"


def load_min_hold_ms(path: str = CONFIG_PATH, default: int = DEFAULT_MIN_HOLD_MS) -> int:
    """从 config.json 读 min_hold_ms；文件缺失或内容非法时回退到默认值。

    配置不是必需的：读不到就用默认值，不让程序因为配置问题启动失败。
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        value = int(data.get("min_hold_ms", default))
    except (OSError, ValueError, TypeError, AttributeError):
        return default
    return max(0, value)


class FixedScorePlayer:
    """固定琴谱的演奏器：Enter DOWN 播放当前音符，Enter UP 释放并前进。

    行为：
        enter_down():
            - 已经在按下状态 -> 忽略（不重复按）
            - 琴谱已播完 / 没有音符 -> 什么都不做
            - 否则 start_current() 取出当前音符的输入状态并 apply 出去
        enter_up():
            - 没有对应的按下 -> 忽略
            - 已经播够 min_hold_ms -> 立即释放并推进
            - 还没播够 -> 保持当前音符，挂一个 Timer 等剩余时间，到点再释放并推进
        shutdown():
            - 让挂起的 Timer 失效，并释放所有由本程序持有的输入
    """

    def __init__(self, notes: Sequence[Note], io_module=io, release_all_on_enter_up=False,
                 min_hold_ms: int = DEFAULT_MIN_HOLD_MS):
        self.notes = list(notes)
        self.io = io_module
        self.controller = PlaybackController(self.notes)
        self.executor = PlaybackExecutor()
        # 为了兼容测试：把 executor 的模拟按键引用也指向同一个输入模块，
        # 这样注入假的输入模块时，executor 也不会碰真实输入。
        self.executor._press_key = io_module.press_key
        self.executor._release_key = io_module.release_key
        self.executor._press_mouse = io_module.press_mouse
        self.executor._release_mouse = io_module.release_mouse
        self.enter_is_down = False
        self.note_is_playing = False
        # Enter UP 的策略：
        #   False（默认）= 只释放当前音符键，调音键跨音符保持按住。
        #       这样 [↑ 3 4 5] 区间内 right 全程只按一次，音符切换时没有多余 UP/DOWN。
        #   True = 每次 Enter UP 都释放全部输入（每次音符都重新按调音键）。
        self.release_all_on_enter_up = release_all_on_enter_up
        # ---- Task 12：最小音符持续时间 ----
        self.min_hold_ms = max(0, int(min_hold_ms))
        # 当前音符是什么时候按下的（单调时钟，不受系统时间调整影响）
        self._note_started_at = None
        self._pending_timer = None
        # generation 守卫：任何会让"旧 timer 失效"的操作都会 +1。
        # Timer 回调先比对自己出生时的 generation，不一致就直接放弃。
        self._timer_generation = 0
        self._last_defer_ms = None      # 诊断/测试用：最近一次延迟了多少毫秒

    # ---------- 查询（测试与调试用） ----------

    @property
    def index(self) -> int:
        return self.controller.index

    def note_count(self) -> int:
        return len(self.notes)

    def is_finished(self) -> bool:
        return self.controller.is_finished()

    def current_note(self) -> Optional[Note]:
        return self.controller.current_note()

    def current_state(self) -> PlaybackState:
        return self.executor.current_state()

    def current_state_text(self) -> str:
        """把当前真实持有的输入打印成 'keys=[z+x] mouse=[right]' 便于比对。"""
        state = self.executor.current_state()
        keys = "+".join(sorted(str(k) for k in state.keys)) or "-"
        buttons = "/".join(sorted(state.mouse_buttons)) or "-"
        return f"keys=[{keys}] mouse=[{buttons}]"

    # ---------- Enter ----------

    def enter_down(self) -> None:
        if self.enter_is_down:
            return  # 已经处于按下状态：不重复播放
        self.enter_is_down = True

        note = self.controller.current_note()
        if note is None:
            return  # 琴谱播完或没有音符：不发出任何输入

        # 新的按下让任何"等着的旧 timer"失效：它绝不能去动即将播放的内容。
        self._invalidate_pending_timer()

        self.controller.start_current()
        self.executor.apply(self.controller.current_state())
        self.note_is_playing = True
        self._note_started_at = time.monotonic()

    def enter_up(self) -> None:
        if not self.enter_is_down:
            return  # 没有对应的按下：不重复处理
        self.enter_is_down = False

        if not self.note_is_playing:
            return  # 这次按下没有真的播放任何音符（例如琴谱已播完）

        remaining_ms = self._remaining_hold_ms()
        if remaining_ms <= 0:
            self._complete_note()          # 已经播够 min_hold_ms：立即释放并推进
        else:
            self._schedule_completion(remaining_ms)   # 还没播够：延迟释放并推进

    # ---------- Task 12：最小持续时间 ----------

    def _elapsed_ms(self) -> float:
        """当前音符已经播放了多久（单调时钟）。"""
        if self._note_started_at is None:
            return float("inf")
        return (time.monotonic() - self._note_started_at) * 1000.0

    def _remaining_hold_ms(self) -> float:
        """距离满足 min_hold_ms 还差多少毫秒；<= 0 表示已经满足。"""
        if self.min_hold_ms <= 0:
            return 0.0
        return self.min_hold_ms - self._elapsed_ms()

    def _invalidate_pending_timer(self) -> None:
        """让挂起的 timer 失效（generation +1），并取消它。

        只做"标记失效 + cancel"，不等待、不阻塞调用方。
        """
        self._timer_generation += 1
        timer = self._pending_timer
        self._pending_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:  # noqa: BLE001 - 取消失败不应影响主流程
                pass

    def _schedule_completion(self, delay_ms: float) -> None:
        """安排一个 Timer，在 delay_ms 之后释放当前音符并推进。"""
        self._last_defer_ms = delay_ms
        generation = self._timer_generation
        timer = threading.Timer(delay_ms / 1000.0, self._on_timer, args=(generation,))
        # 明确设为 daemon：即使程序在等待期间退出，也不会被这个 timer 拖住
        timer.daemon = True
        timer.owner_ref = timer          # 让回调能认出"这个 timer 就是我"
        self._pending_timer = timer
        timer.start()

    def _on_timer(self, generation: int) -> None:
        """Timer 回调（在 Timer 自己的线程上执行，绝不阻塞钩子线程）。

        先无条件把自己的引用清掉：即使这个 timer 已经因为 generation 变化而失效，
        也不能留下一个"永远不会触发"的挂起引用（否则调用方会一直以为还在等待）。

        只有 generation 仍然匹配时才动手：任何后续的 shutdown/release_all 都会让
        generation 失效，因此旧 timer 不可能去动"新的音符"。
        """
        current = threading.current_thread()
        me = getattr(current, "owner_ref", None)
        if getattr(self._pending_timer, "owner_ref", None) is me:
            self._pending_timer = None
        if generation != self._timer_generation:
            return
        if not self.note_is_playing:
            return
        self._pending_timer = None
        self._complete_note()

    def _complete_note(self) -> None:
        """结束当前音符：推进 index 并让真实输入跟上新位置。

        立即完成（Enter UP 时已播够 min_hold_ms）和延迟完成（timer 到点）都走这里，
        因此两条路径的可观察行为完全一致。

        顺序很重要：先把当前音符停止（推进 index），再决定释放多少，
        这样 index 与真实输入始终一致。
        """
        self.note_is_playing = False
        self._note_started_at = None
        self.controller.stop_current_and_advance()

        if self.release_all_on_enter_up or self.controller.is_finished():
            # 已经是最后一个音符（策略上或因为播完）：不留下任何按住的东西。
            # 调音键也在这里释放，避免它的状态比 index 更超前而一直卡住。
            self.executor.release_all()
        else:
            # 让下一个音符进入"就绪"状态，这样 controller.current_state() 才有内容。
            self.controller.start_current()
            if self.enter_is_down:
                # 这一轮是"延迟完成"，而且用户此时已经把 Enter 又按住了：
                # 不能凭空按下下一个音符（那需要一个真正的 Enter DOWN 来做），
                # 所以只把"下一个音符不再需要的输入"释放掉，调音键按需保持。
                held = self.executor.current_state()
                keep_state = PlaybackState(
                    keys=held.keys & self.controller.current_state().keys,
                    mouse_buttons=held.mouse_buttons & self.controller.current_state().mouse_buttons,
                )
                self.executor.apply(keep_state)
            else:
                # Task 27A 修复（真实 bug）：Enter 已经松开时，本次音符产生的
                # **全部**真实输出（键盘键 + 鼠标调音键）都必须在这里立即释放干净，
                # 且**绝不能** apply 下一个音符的状态 —— 否则会把下一个音符的键
                # 按下并一直保持，游戏里就表现为"松开 Enter 后琴键仍然按住、
                # 输出停不下来，必须再按一次 Enter 才松"。
                # 下一个音符的键只会在**下一次真正的 Enter DOWN** 时按下。
                self.executor.release_all()

    # ---------- 退出 / 紧急控制（Task 13） ----------

    def _release_and_prepare_current_note(self) -> None:
        """公共收尾：失效 timer、释放全部真实输入、把当前 index 的音符置为"就绪"。

        index 不动 —— 由调用方决定是保持（Esc）还是归零（R）。

        注意：**刻意不修改 `enter_is_down`**。Esc/R 停止的是"演奏状态"，不是
        "Enter 的物理按键状态"；如果在这里把它清掉，而 input.py 钩子里的
        `_enter_down` 仍是 True，下一次 Enter DOWN 就会被钩子的去重逻辑吞掉，
        导致"Esc 之后按 Enter 没反应"。
        """
        self._invalidate_pending_timer()
        self.executor.release_all()
        self.note_is_playing = False
        self._note_started_at = None
        # 让当前 index 的音符进入"就绪"状态，下一次 Enter DOWN 才会真正按下它。
        if not self.controller.is_finished():
            self.controller.start_current()

    def emergency_stop(self) -> None:
        """Esc 紧急停止：立即停掉当前演奏，但**不修改 index**。

        - 取消/失效挂起的 min_hold timer（旧 timer 之后也不可能再操作）
        - 释放所有由本程序按下的键盘键与鼠标键
        - 回到"等待新的 Enter DOWN"状态；index 保持原值，
          因此下一次 Enter DOWN 会重新播放当前这个音符。
        """
        self._release_and_prepare_current_note()

    def reset(self) -> None:
        """R 重置：停掉当前演奏并把 index 归零，从第一个音符重新开始。"""
        self._release_and_prepare_current_note()
        self.controller.reset()
        if not self.controller.is_finished():
            self.controller.start_current()

    def shutdown(self) -> None:
        """正常退出清理：让挂起的 timer 失效并释放所有由本程序持有的输入。

        - 先让 timer 失效，退出后它不可能再按下或释放任何东西
        - 释放全部真实输入（键盘 + 鼠标）
        - 复位内部状态，避免退出过程中被残留状态影响
        """
        self._invalidate_pending_timer()
        self.executor.release_all()
        self.enter_is_down = False
        self.note_is_playing = False
        self._note_started_at = None
        self.controller.reset()
