"""UI ↔ 播放器核心 的连接层（Task 15）。

把 Task 14 的 GUI 外壳接到已经过 CORE BIG TEST / Backup 1 验证的核心上。

**不重新实现任何播放逻辑**，全部复用现有模块：
    score.py              解析琴谱文本（UI 里的琴谱由它解析）
    harmonica_app.py      FixedScorePlayer（播放器状态机、min_hold_ms、Timer、index 推进）
    input.py              真实键鼠输入 + Enter Hook（Enter / Esc / R 由它负责，本层不重做）

本层只做"翻译"：
    UI 按钮  -> 调用核心已有方法（start / pause / resume / stop / reset）
    核心状态 -> 提供给 UI 显示（status_text / current_note_text）

涉及的核心方法（全部已存在，未修改）：
    FixedScorePlayer.index / current_note() / note_count() / shutdown()
    FixedScorePlayer.emergency_stop()   <- Stop：安全停止 + release_all，index 不变
    FixedScorePlayer.reset()            <- Reset：清理输入并把 index 归零
    input.release_all() / start_enter_listener() / stop_enter_listener() / is_listening()
    input.set_enter_callbacks() / set_escape_callback() / set_reset_callback()

注意：实际的"播放推进"仍然由核心的 Enter DOWN/UP 触发（这是既有设计）。
     本层的 start() 负责装载琴谱、重置到开头、把控制权交给核心并让 Enter Hook 就绪；
     pause()/stop() 会卸载 Hook，避免程序闲置时仍然全局吞掉用户的 Enter。
"""

import os
import time

DEFAULT_SCORE_TEXT = "1 2 [\u2191 3 4 5] 6 [~ 7 1'] [\u2193 2]"

STATE_IDLE = "Idle"
STATE_PLAYING = "Playing"
STATE_PAUSED = "Paused"
STATE_STOPPED = "Stopped"
STATE_RESET = "Ready"
# 与 STATE_RESET 同一个显示值："就绪"状态（Reset 之后、以及 Open 新琴谱之后）
STATE_READY = "Ready"

# Task 22：内部状态值保持不变（逻辑用），这里只做"显示文字"的中文映射。
_STATE_DISPLAY = {
    STATE_IDLE: "就绪",
    STATE_PLAYING: "播放中",
    STATE_PAUSED: "已暂停",
    STATE_STOPPED: "已停止",
    STATE_RESET: "就绪",
    STATE_READY: "就绪",
}

# UI 需要弹文件对话框（controller 自己不碰对话框）
NEED_DIALOG = "NEED_DIALOG"

# 文件对话框过滤条件（由 UI 传给 tkinter.filedialog）
FILE_TYPES = [("Text files", "*.txt"), ("All files", "*.*")]
DEFAULT_EXTENSION = ".txt"

# UI 轮询间隔（毫秒）。只用 tkinter.after()，不做任何阻塞式循环。
POLL_INTERVAL_MS = 150


class AppController:
    """把 UI 的按钮与显示接到核心播放器上。"""

    def __init__(self, ui_module=None, core_module=None, input_module=None,
                 score_module=None, min_hold_ms=None, score_text=None,
                 ui_thread_after=None, library_module=None,
                 library_project_dir=None):
        # 延迟导入：便于测试注入替身，也让 ui.py 保持与核心解耦
        if core_module is None:
            import harmonica_app as core_module
        if input_module is None:
            import input as input_module
        if score_module is None:
            import score as score_module
        if library_module is None:
            import score_library as library_module

        self.core = core_module
        self.io = input_module
        self.score = score_module
        self.library = library_module
        # Task 18：谱库根目录（None 时由 score_library 按项目位置推导）
        self.library_project_dir = library_project_dir

        if min_hold_ms is None:
            min_hold_ms = core_module.load_min_hold_ms()

        self.min_hold_ms = int(min_hold_ms)
        self.score_text_value = score_text if score_text is not None else DEFAULT_SCORE_TEXT
        # Task 16：当前已打开/已保存的文件路径（没有时为 None）
        self.current_path = None

        self.state = STATE_IDLE
        self.last_error = None
        self.message = None      # 最近一次操作的反馈文字（Opened / Saved / 已取消）
        # Task 19：当前琴谱是否有未保存的修改（UI 显示 "名称 *"）
        self.modified = False
        self._ui_thread_after = ui_thread_after     # 用于把核心回调安全地切回 UI 线程
        self._poll_job = None

        # 解析琴谱（交给 score.py，本层不解析）
        self.player = None
        self._load_player()

    # ---------- 内部 ----------

    def _load_player(self):
        """（重新）解析琴谱文本并创建播放器。解析失败时保留旧播放器并记录错误。

        注意：必须把注入的输入模块传给播放器（io_module=self.io）。
        否则 player 会用默认的真实 input 模块，测试注入的替身就失效了，
        而且会在测试过程中真的去按真实键鼠。
        """
        try:
            notes = self.score.parse_score_notes(self.score_text_value)
        except Exception as exc:  # noqa: BLE001 - 解析错误要显示到界面上
            self.last_error = str(exc)
            return False
        self.last_error = None
        self.player = self.core.FixedScorePlayer(notes, io_module=self.io,
                                                 min_hold_ms=self.min_hold_ms)
        return True

    def _note_text(self):
        if self.player is None:
            return "-"
        note = self.player.current_note()
        if note is None:
            return "-"
        return str(note.note)

    def _marshal(self, func):
        """把核心回调（工作线程）切回 UI 线程；没有提供调度器时直接执行。"""
        if self._ui_thread_after is None:
            func()
        else:
            try:
                self._ui_thread_after(0, func)
            except Exception:  # noqa: BLE001 - 窗口已销毁时忽略
                pass

    # ---------- 核心的键盘回调（由 input.py 的 Hook 调用，跑在工作线程上） ----------

    def on_enter_down(self):
        if self.player is None or self.state != STATE_PLAYING:
            return
        self.player.enter_down()
        self._marshal(self.poll)

    def on_enter_up(self):
        if self.player is None or self.state != STATE_PLAYING:
            return
        self.player.enter_up()
        self._marshal(self.poll)

    def on_escape(self):
        """Esc：核心既有的"紧急停止"（index 不变，释放所有输入）。"""
        if self.player is None:
            return
        self.player.emergency_stop()
        self.state = STATE_STOPPED
        self._marshal(self.poll)

    def on_reset(self):
        """R：核心既有的 reset（清理输入 + index 归零）。"""
        if self.player is None:
            return
        self.player.reset()
        self.state = STATE_RESET
        self._marshal(self.poll)

    # ---------- UI 通过接口调用的部分 ----------

    @property
    def status_text(self):
        """优先显示最近一次操作的反馈，否则显示播放状态（中文化显示文字）。"""
        if self.last_error:
            return "错误"
        if self.message:
            return self.message
        return _STATE_DISPLAY.get(self.state, self.state)

    @property
    def current_note_text(self):
        return self._note_text()

    @property
    def score_text(self):
        return self.score_text_value

    def score_modified(self, text):
        """用户在 UI 里改了琴谱：记录下来，下次 start() 时交给 score.py 重新解析。"""
        self.score_text_value = text
        self.modified = True

    def start(self):
        """Start：装载琴谱 -> 回到开头 -> 交给核心并让 Enter Hook 就绪。"""
        self.message = None
        if not self._load_player():
            self.state = "Error"
            return
        self.player.reset()                     # 核心的 reset：清理输入 + index 归零
        self._register_callbacks()
        self.io.start_enter_listener()          # Enter/Esc/R 仍由核心负责
        self.state = STATE_PLAYING

    def pause(self):
        """Pause：暂停演奏，保留当前位置，卸载 Hook（不产生残留输入）。"""
        self.message = None
        if self.player is not None:
            self.player.emergency_stop()        # 核心既有的安全停止：释放输入，index 不变
        self.io.stop_enter_listener()
        self.state = STATE_PAUSED

    def resume(self):
        """Resume：从暂停位置继续（不重置 index）。"""
        self.message = None
        if self.player is None:
            return
        self._register_callbacks()
        self.io.start_enter_listener()
        self.state = STATE_PLAYING

    def stop(self):
        """Stop：核心既有的安全停止（release_all + index 不变），并卸载 Hook。"""
        self.message = None
        if self.player is not None:
            self.player.emergency_stop()
        self.io.stop_enter_listener()
        self.state = STATE_STOPPED

    def reset(self):
        """Reset：核心既有的 reset（清理输入 + index 归零）。"""
        self.message = None
        if self.player is not None:
            self.player.reset()
        self.state = STATE_RESET

    def open_file(self, path=None):
        """Open（Task 16）：读取 UTF-8 琴谱文本。

        path 为 None 且当前没有已知文件时，返回 NEED_DIALOG 让 UI 弹文件选择框
        （UI 负责调用 tkinter.filedialog，controller 不碰对话框）。

        职责只有"读文本"：**不解析琴谱**，解析仍然由 score.py 在 start() 时进行。
        """
        if path is None:
            path = self.current_path
            if path is None:
                return NEED_DIALOG

        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except Exception as exc:  # noqa: BLE001 - 读取失败要显示成状态，不能崩
            return self._report_error(f"无法打开: {exc}")

        # 正在播放时先安全停止（复用核心的紧急停止：release_all + index 不变）
        if self.state == STATE_PLAYING:
            self._safe_release()

        self.current_path = path
        self.last_error = None
        self.score_modified(text)          # 通知 core 层琴谱已变化
        self.modified = False              # 刚载入，未修改
        self.state = STATE_READY
        self.message = f"已打开: {os.path.basename(path)}"
        return self.message

    def save_file(self, path=None):
        """Save（Task 16）：把当前 Score 文本以 UTF-8 写回 .txt。

        没有已知文件路径时返回 NEED_DIALOG，让 UI 弹"另存为"对话框。
        不改变播放器位置，也不触碰播放状态。
        """
        if path is None:
            path = self.current_path
            if path is None:
                return NEED_DIALOG

        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.score_text_value)
        except Exception as exc:  # noqa: BLE001 - 写入失败要显示成状态，不能崩
            return self._report_error(f"无法保存: {exc}")

        self.current_path = path
        self.last_error = None
        self.modified = False              # 保存成功，未修改状态清除
        self.message = f"已保存: {os.path.basename(path)}"
        return self.message

    # ---------- 谱库（Task 18）----------

    def library_scan(self):
        """扫描真实 Scores 目录，返回条目列表（文件夹 + .txt 琴谱）。"""
        try:
            return self.library.list_scores(self.library_project_dir)
        except Exception:  # noqa: BLE001 - 扫描失败按空列表处理，不崩
            return []

    def library_create_folder(self, name):
        """在当前谱库根目录创建真实文件夹（只允许安全名称）。"""
        result = self.library.create_folder(name, self.library_project_dir)
        if result[0] != "ok":
            return self._report_error(f"创建文件夹失败: {result[1]}")
        self.message = f"已创建文件夹: {result[1]}"
        self.last_error = None
        return self.message

    def library_load_score(self, relpath):
        """从谱库加载一个真实 .txt 琴谱到 Score 编辑区（不自动播放）。

        与 open_file 同一套流程：正在播放时先安全停止 -> 记录路径 ->
        更新琴谱文本 -> 状态 Ready。路径安全校验由 score_library 负责。
        """
        result = self.library.load_score(relpath, self.library_project_dir)
        if result[0] != "ok":
            return self._report_error(f"无法加载: {result[1]}")
        path = self.library.resolve_score_path(relpath, self.library_project_dir)
        return self._adopt_score_text(result[1], path, f"已加载: {relpath}")

    def library_save_as(self, relpath):
        """Task 19：把当前琴谱另存为 Scores 内的新 .txt（只允许 Scores 及其子目录）。

        与 save_file 同样的"不打断播放"语义：只写文件 + 更新 current_path，
        不改变播放器位置与播放状态。成功清 modified。
        """
        result = self.library.save_score(relpath, self.score_text_value,
                                         self.library_project_dir)
        if result[0] != "ok":
            return self._report_error(f"另存为失败: {result[1]}")
        self.current_path = result[1]
        self.last_error = None
        self.modified = False
        self.message = f"已另存为: {relpath}"
        return self.message

    def library_new_score(self, name):
        """Task 19：在 Scores 内新建一个空 .txt 并进入编辑状态（不自动播放）。

        目标已存在时拒绝（不覆盖）；正在播放时先安全停止（释放输入、
        卸载 Hook、进入 Ready），不自动恢复播放。
        """
        result = self.library.new_score(name, self.library_project_dir)
        if result[0] != "ok":
            return self._report_error(f"新建琴谱失败: {result[1]}")
        if self.state == STATE_PLAYING:
            self._safe_release()
        relpath, target = result[1], result[2]
        self.current_path = target
        self.score_text_value = ""         # 新建：内容为空，直接可输入
        self.modified = False
        self.last_error = None
        self.state = STATE_READY
        self.message = f"已新建琴谱: {relpath}"
        return self.message

    @staticmethod
    def _path_in_dir(path, dirpath):
        """path 是否位于 dirpath 内（用于文件夹重命名后更新 current_path）。"""
        try:
            return os.path.abspath(path).startswith(os.path.abspath(dirpath) + os.sep)
        except Exception:  # noqa: BLE001
            return False

    def library_rename_score(self, old_relpath, new_name):
        """Task 20：重命名 Scores 内的 .txt。若重命名的是当前打开的谱，同步更新 current_path。

        重命名不改变内容，因此不打断播放、保留 modified 状态（无内容丢失）。
        """
        result = self.library.rename_score(old_relpath, new_name,
                                           self.library_project_dir)
        if result[0] != "ok":
            return self._report_error(f"重命名失败: {result[1]}")
        _ok, new_relpath, new_path = result
        old_path = self.library.resolve_score_path(old_relpath,
                                                   self.library_project_dir)
        if (self.current_path and old_path
                and os.path.abspath(self.current_path) == os.path.abspath(old_path)):
            self.current_path = new_path
        self.last_error = None
        self.message = f"已重命名: {new_relpath}"
        return self.message

    def library_delete_score(self, relpath):
        """Task 20：删除 Scores 内的 .txt。

        若删除的是当前打开的谱：
            - 有未保存修改 -> 拒绝（保护用户内容，不偷偷丢失）
            - 正在播放 -> 先安全停止（释放输入 + 卸载 Hook）
            - 删除后 current_path 失效、编辑区清空、状态 Ready
        """
        old_path = self.library.resolve_score_path(relpath, self.library_project_dir)
        is_current = bool(self.current_path and old_path
                          and os.path.abspath(self.current_path) == os.path.abspath(old_path))
        if is_current and self.modified:
            return self._report_error("删除失败: 当前琴谱有未保存的修改")
        if is_current and self.state == STATE_PLAYING:
            self._safe_release()
        result = self.library.delete_score(relpath, self.library_project_dir)
        if result[0] != "ok":
            return self._report_error(f"删除失败: {result[1]}")
        if is_current:
            self.current_path = None
            self.score_text_value = ""
            self.modified = False
            self.last_error = None
            self.state = STATE_READY
        self.message = f"已删除: {relpath}"
        return self.message

    def library_rename_folder(self, old_relpath, new_name):
        """Task 20：重命名 Scores 内的文件夹；若当前谱在其内，同步更新 current_path。"""
        result = self.library.rename_folder(old_relpath, new_name,
                                            self.library_project_dir)
        if result[0] != "ok":
            return self._report_error(f"重命名文件夹失败: {result[1]}")
        new_relpath = result[1]
        root = self.library.scores_root(self.library_project_dir)
        old_dir = os.path.join(root, old_relpath.replace("/", os.sep))
        new_dir = os.path.join(root, new_relpath.replace("/", os.sep))
        if self.current_path and self._path_in_dir(self.current_path, old_dir):
            rel = os.path.relpath(self.current_path, old_dir)
            self.current_path = os.path.join(new_dir, rel)
        self.last_error = None
        self.message = f"已重命名文件夹: {new_relpath}"
        return self.message

    def library_delete_folder(self, relpath):
        """Task 20：删除 Scores 内的空文件夹（非空由 score_library 拒绝）。"""
        result = self.library.delete_folder(relpath, self.library_project_dir)
        if result[0] != "ok":
            return self._report_error(f"删除文件夹失败: {result[1]}")
        root = self.library.scores_root(self.library_project_dir)
        old_dir = os.path.join(root, relpath.replace("/", os.sep))
        # 空文件夹内不可能有当前谱，但做防御性失效
        if self.current_path and self._path_in_dir(self.current_path, old_dir):
            self.current_path = None
            self.score_text_value = ""
            self.modified = False
        self.last_error = None
        self.message = f"已删除文件夹: {relpath}"
        return self.message

    def _adopt_score_text(self, text, path, message):
        """把已读到的琴谱文本接入现有流程：安全停止 -> 记录路径 -> 更新 -> Ready。"""
        if self.state == STATE_PLAYING:
            self._safe_release()
        self.current_path = path
        self.last_error = None
        self.score_modified(text)
        self.modified = False              # 刚载入，未修改
        self.state = STATE_READY
        self.message = message
        return self.message

    def report_status(self, message):
        """让 UI 报告一条状态文字（例如 Opened / Saved / 已取消）。"""
        self.message = str(message) if message else None
        return self.status_text

    def _report_error(self, message):
        self.last_error = str(message)
        self.message = None
        return f"错误: {message}"

    def _safe_release(self):
        """复用核心的安全停止机制：释放所有模拟输入并卸载 Hook。"""
        try:
            if self.player is not None:
                self.player.emergency_stop()   # 核心既有：release_all + index 不变
        finally:
            try:
                self.io.stop_enter_listener()
            except Exception:  # noqa: BLE001
                pass
            self.io.release_all()              # 输入模块层面的兜底释放

    def _register_callbacks(self):
        self.io.set_enter_callbacks(on_down=self.on_enter_down, on_up=self.on_enter_up)
        self.io.set_escape_callback(self.on_escape)
        self.io.set_reset_callback(self.on_reset)

    # ---------- 状态显示 ----------

    def refresh(self):
        """返回 (status_text, current_note_text, error_text)。UI 用它更新显示。"""
        return (self.status_text, self.current_note_text, self.last_error or "")

    def poll(self):
        """按固定间隔刷新状态（由 UI 用 after() 驱动，非阻塞）。"""
        self.refresh()

    def schedule_poll(self, widget):
        """用 tkinter.after 定期刷新界面；不使用任何阻塞循环或 sleep。"""
        def _tick():
            try:
                self.refresh()
                widget.after(POLL_INTERVAL_MS, _tick)
            except Exception:  # noqa: BLE001 - 窗口销毁后停止
                pass
        widget.after(POLL_INTERVAL_MS, _tick)

    # ---------- 退出 ----------

    def shutdown(self):
        """关闭窗口时的收尾：释放所有模拟输入、卸载 Hook、停掉轮询。"""
        try:
            if self.player is not None:
                self.player.shutdown()          # 核心既有：失效 timer + release_all
        finally:
            self.io.release_all()               # 输入模块层面的兜底释放
            self.io.stop_enter_listener()       # 卸载 Enter Hook
            self.state = STATE_STOPPED
