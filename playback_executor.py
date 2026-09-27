"""播放状态执行器（Task 10）。

把 playback.py 的纯逻辑状态（PlaybackState）转换成 input.py 的真实按键与鼠标操作。

核心思想：执行器自己维护"上一次已经实际按下的状态"，
每次 apply(new_state) 只处理 old → new 的差异：

    old = {"z"}, {"right"}
    new = {"x"}, {"right"}
    -> release_key("z"); press_key("x")
       right 在新旧状态里都存在，保持按住，不做任何操作

这样调音键（调音区间内的鼠标键）才是"持续状态"，不会出现 UP → DOWN 抖动。

本模块只调用 input.py 已经验证过的正式 API：
    press_key / release_key / press_mouse / release_mouse
不做自动播放、不接 Enter Hook、不管节奏/时值。
"""

from typing import List, Set

import input as io
from playback import PlaybackState

EMPTY_STATE = PlaybackState()


class PlaybackExecutor:
    """把 PlaybackState 的差异落到真实输入上。

    执行顺序（每次 apply）：
        1. 释放"旧有新没有"的键盘键
        2. 释放"旧有新没有"的鼠标键
        3. 按下"新有旧没有"的键盘键
        4. 按下"新有旧没有"的鼠标键
        5. 记录新状态

    先释放再按下，保证过渡瞬间不会出现"新旧两个音符键同时按住"。
    """

    def __init__(self):
        self.state: PlaybackState = EMPTY_STATE
        # 保存 input.py 的函数引用，便于测试时替换（不影响 input.py 本身）
        self._press_key = io.press_key
        self._release_key = io.release_key
        self._press_mouse = io.press_mouse
        self._release_mouse = io.release_mouse

    # ---------- 查询 ----------

    def current_state(self) -> PlaybackState:
        """返回执行器当前"实际按下"的状态。"""
        return self.state

    def held_keys(self) -> Set[str]:
        return set(self.state.keys)

    def held_mouse_buttons(self) -> Set[str]:
        return set(self.state.mouse_buttons)

    # ---------- 状态迁移 ----------

    def apply(self, new_state: PlaybackState) -> None:
        """把真实输入调整到 new_state 描述的状态。"""
        if not isinstance(new_state, PlaybackState):
            raise TypeError(
                f"apply() expects a PlaybackState, got {type(new_state).__name__}"
            )

        old = self.state
        new_keys = frozenset(new_state.keys)
        new_buttons = frozenset(new_state.mouse_buttons)

        keys_to_release = sorted(old.keys - new_keys)
        buttons_to_release = sorted(old.mouse_buttons - new_buttons)
        keys_to_press = sorted(new_keys - old.keys)
        buttons_to_press = sorted(new_buttons - old.mouse_buttons)

        for key in keys_to_release:
            self._release_key(key)
        for button in buttons_to_release:
            self._release_mouse(button)
        for key in keys_to_press:
            self._press_key(key)
        for button in buttons_to_press:
            self._press_mouse(button)

        self.state = PlaybackState(keys=new_keys, mouse_buttons=new_buttons)

    def release_all(self) -> None:
        """释放执行器自己记录为已按下的全部输入，并清空内部状态。

        注意：这里逐个调用 release_key / release_mouse，而不是调用
        input.release_all() —— 输入模块的全局状态由执行器自己负责，
        不使用 input.py 的全局兜底释放来实现差分逻辑。
        """
        keys: List[str] = sorted(self.state.keys)
        buttons: List[str] = sorted(self.state.mouse_buttons)

        for key in keys:
            self._release_key(key)
        for button in buttons:
            self._release_mouse(button)

        self.state = EMPTY_STATE

    # ---------- 便于调试 ----------

    def __repr__(self) -> str:
        return (
            f"PlaybackExecutor(keys={sorted(self.state.keys)}, "
            f"mouse={sorted(self.state.mouse_buttons)})"
        )
