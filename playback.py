"""播放控制器（纯逻辑）。

当前阶段（Task 9）：根据 score.py 解析出来的 Note 列表，计算"当前音符需要哪些输入"。

本模块**只做状态计算**：
    - 不 import input.py
    - 不调用任何真实键盘 / 鼠标模拟
    - 不安装 Hook、不读键盘、不做自动播放、不 sleep

调音键的语义：它是"持续状态"，不是每个音符重新按一次。
    1 2 [↑ 3 4 5] 6
时 3 → 4 → 5 之间 right 一直保持需要按下，不会出现 right UP → right DOWN 的抖动。

用法：
    from score import parse_score_notes
    from playback import PlaybackController

    controller = PlaybackController(parse_score_notes("1 2 [↑ 3] 4"))
    while not controller.is_finished():
        state = controller.start_current()
        ...  # 由上层去真正按下 state.keys / state.mouse_buttons（Task 10+）
        controller.stop_current_and_advance()
"""

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional, Sequence

from score import (
    MODIFIER_FLAT,
    MODIFIER_HALF,
    MODIFIER_NORMAL,
    MODIFIER_SHARP,
    Note,
)

# 调音状态 -> 需要持续按住的鼠标键（normal 不需要鼠标键）
MODIFIER_MOUSE_BUTTONS = {
    MODIFIER_NORMAL: None,
    MODIFIER_SHARP: "right",
    MODIFIER_FLAT: "left",
    MODIFIER_HALF: "middle",
}


@dataclass(frozen=True)
class PlaybackState:
    """一个音符对应的输入状态：需要按住的键盘键 + 需要持续按住的鼠标键。"""

    keys: FrozenSet[str] = field(default_factory=frozenset)
    mouse_buttons: FrozenSet[str] = field(default_factory=frozenset)

    def as_dict(self) -> dict:
        """{keys: {...}, mouse_buttons: {...}}，便于打印与断言。"""
        return {
            "keys": set(self.keys),
            "mouse_buttons": set(self.mouse_buttons),
        }


def state_for_note(note: Note) -> PlaybackState:
    """把单个 Note 转成输入状态。

    Note("1", "z", "normal") -> keys={"z"}, mouse_buttons=set()
    Note("3", "c", "sharp")  -> keys={"c"}, mouse_buttons={"right"}
    Note("4", "v", "flat")   -> keys={"v"}, mouse_buttons={"left"}
    Note("6", "n", "half")   -> keys={"n"}, mouse_buttons={"middle"}
    """
    if note.modifier not in MODIFIER_MOUSE_BUTTONS:
        raise ValueError(
            f"unknown modifier {note.modifier!r}; expected one of: "
            f"{', '.join(MODIFIER_MOUSE_BUTTONS)}"
        )
    keys = frozenset({note.key})
    button = MODIFIER_MOUSE_BUTTONS[note.modifier]
    mouse_buttons = frozenset() if button is None else frozenset({button})
    return PlaybackState(keys=keys, mouse_buttons=mouse_buttons)


class PlaybackController:
    """按顺序推进音符列表的状态机（纯逻辑，不产生任何真实输入）。

    语义：
        - 初始：index = 0，没有正在播放的音符，输入状态为空
        - start_current()：计算当前音符的输入状态并标记为"正在播放"；
          已经在播放时重复调用是幂等的，不会推进 index
        - stop_current_and_advance()：结束当前音符并 index += 1；不会自动开始下一个
        - reset()：回到初始状态
        - 播放到末尾后：index == len(notes)，状态为空，再 start_current() 也不报错
    """

    def __init__(self, notes: Sequence[Note]):
        if notes is None:
            raise TypeError("notes must be a sequence of Note, got None")
        wrong = [type(n).__name__ for n in notes if not isinstance(n, Note)]
        if wrong:
            raise TypeError(f"notes must contain score.Note objects, got {sorted(set(wrong))}")
        self.notes: List[Note] = list(notes)
        self.index: int = 0
        self.is_playing: bool = False
        self.state: PlaybackState = PlaybackState()

    # ---------- 查询 ----------

    def current_note(self) -> Optional[Note]:
        """返回当前 index 指向的音符；越界或播放结束时返回 None。"""
        if 0 <= self.index < len(self.notes):
            return self.notes[self.index]
        return None

    def current_state(self) -> PlaybackState:
        """返回当前应该保持 DOWN 的输入集合。"""
        return self.state

    def is_finished(self) -> bool:
        """所有音符都已经停止推进过（index 到达末尾）。"""
        return self.index >= len(self.notes)

    def has_current(self) -> bool:
        """当前是否有正在播放的音符（start 之后、stop 之前为 True）。"""
        return self.is_playing and self.current_note() is not None

    def note_count(self) -> int:
        return len(self.notes)

    # ---------- 状态迁移 ----------

    def start_current(self) -> PlaybackState:
        """开始播放当前音符：计算并保存它的输入状态。

        已经在播放同一个音符时重复调用是幂等的（index 不变、状态不变）。
        没有音符或已经播放到末尾时不报错，保持空状态。
        """
        note = self.current_note()
        if note is None:
            # 空谱或已到末尾：保持空状态，不报错
            self.is_playing = False
            self.state = PlaybackState()
            return self.state

        if self.is_playing:
            # 重复 start：不重新计算、不推进 index，直接返回当前状态
            return self.state

        self.state = state_for_note(note)
        self.is_playing = True
        return self.state

    def stop_current_and_advance(self) -> None:
        """结束当前音符并前进一个位置。不会自动开始下一个音符。"""
        if self.is_playing:
            self.is_playing = False
            self.state = PlaybackState()
            self.index += 1

    def reset(self) -> None:
        """回到初始状态：index = 0，没有正在播放的音符，输入状态为空。"""
        self.index = 0
        self.is_playing = False
        self.state = PlaybackState()

    # ---------- 便于调试的展示 ----------

    def __repr__(self) -> str:
        return (
            f"PlaybackController(index={self.index}/{len(self.notes)}, "
            f"playing={self.is_playing}, keys={sorted(self.state.keys)}, "
            f"mouse={sorted(self.state.mouse_buttons)})"
        )
