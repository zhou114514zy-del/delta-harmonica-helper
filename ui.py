"""极简 GUI 外壳（Task 14 建立，Task 15 接入播放器核心）。

这是一个"薄 UI"：只负责显示和接收用户操作，**不实现任何播放逻辑**。

刻意不做的事情（全部由核心负责）：
    - 音符解析（score.py）
    - 音符 / 调音映射（playback.py）
    - 键盘 / 鼠标模拟（input.py）
    - Enter Hook、min_hold_ms、Timer、index 推进、release_all
    - 播放器状态机（harmonica_app.FixedScorePlayer）

本模块只使用 Python 标准库 tkinter，没有第三方依赖。

Task 15 的连接方式：**依赖注入**。
    本模块只调用注入进来的 controller，且只使用下面这组接口（不使用 isinstance 检查）：
        controller.status_text         -> 状态文字（字符串）
        controller.current_note_text   -> 当前音符文字（字符串，没有时 "-"）
        controller.score_text          -> 琴谱文本
        controller.score_modified(text) -> 用户编辑了琴谱
        controller.start() / pause() / resume() / stop() / reset()
        controller.open_file() / save_file()   -> 返回要显示的状态文字（Task 16 才真正实现）
        controller.refresh()           -> 返回 (status_text, current_note_text) 或 None
        controller.shutdown()          -> 关闭窗口时的收尾
    controller 为 None 时退化为纯占位按钮（Task 14 的行为）。

用法：
    import tkinter as tk
    from ui import HarmonicaUI
    root = tk.Tk()
    app = HarmonicaUI(root, controller=my_controller)   # controller 可省略
    root.mainloop()
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

WINDOW_TITLE = "Delta Harmonica Helper"
# Task 24：按控件实际自然高度实测（约 607px + 编辑区外部 pady 8px ≈ 615px）取 620，
# 使谱库管理按钮行与快捷键提示在默认尺寸下完整可见（此前 500 会裁掉它们）。
WINDOW_SIZE = "700x620"

# 界面上可见的各种状态文字（Task 22 中文化）
STATUS_READY = "就绪"
STATUS_PLAYING = "播放中"
STATUS_PAUSED = "已暂停"
STATUS_STOPPED = "已停止"
STATUS_RESET = "就绪"
STATUS_OPEN_CANCELLED = "已取消打开"
STATUS_SAVE_CANCELLED = "已取消保存"

# 没有 controller 时的占位状态（Task 14 行为）
STATUS_OPEN_PLACEHOLDER = "打开"
STATUS_SAVE_PLACEHOLDER = "保存"

# 文件对话框过滤条件
FILE_TYPES = [("Text files", "*.txt"), ("All files", "*.*")]
DEFAULT_EXTENSION = ".txt"

NEED_DIALOG = "NEED_DIALOG"

PLACEHOLDER_NOTE = "-"
PLACEHOLDER_SCORE = "1 2 [\u2191 3 4 5] 6 [~ 7 1'] [\u2193 2]"

SHORTCUT_LINES = (
    "Enter = 弹奏 / 保持",
    "Esc = 紧急停止",
    "R = 重置",
)

# Task 23：谱面格式说明（只读展示，不参与解析；内容与 score.py 现有规则一致）
FORMAT_HELP_TEXT = """谱面格式说明

一、普通音符
普通音符可以自由换行。
换行只影响显示，不影响播放顺序。
单行：1 2 3 4 5 6 7 1'
多行：1 2 3
      4 5 6
      7 1'
两者播放顺序相同。

二、调音组
调音组必须保持在同一行。
[↑ 3 4 5]   升调
[↓ 2]       降调
[~ 6 7 1']  半音
[normal 1 2]

三、混合写法
1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]

四、注释
# 开头表示注释。
# 这是我的第一段谱子
1 2 3 4 5

五、键位映射
1 → Z    2 → X    3 → C    4 → V
5 → B    6 → N    7 → M    1' → ,
↑ → 右键
↓ → 左键
~ → 中键

六、调音组不能跨行
正确：[↑ 3 4 5]
错误：[↑ 3
      4 5]
跨行的调音组会被拒绝（报错）。
"""


class HarmonicaUI:
    """主窗口。所有控件都挂在这个类的属性上，方便自动化测试直接引用。"""

    def __init__(self, root, controller=None):
        self.root = root
        self.controller = controller

        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)

        # ---- 状态区域 ----
        self.status_var = tk.StringVar(value=self._initial_status())
        status_frame = tk.Frame(root, padx=10, pady=8)
        status_frame.pack(fill="x")
        tk.Label(status_frame, text="状态:", width=12, anchor="w").pack(side="left")
        self.status_label = tk.Label(status_frame, textvariable=self.status_var, anchor="w")
        self.status_label.pack(side="left")

        # ---- 当前音符区域 ----
        self.note_var = tk.StringVar(value=self._initial_note())
        note_frame = tk.Frame(root, padx=10)
        note_frame.pack(fill="x")
        tk.Label(note_frame, text="当前音符:", width=12, anchor="w").pack(side="left")
        self.note_label = tk.Label(note_frame, textvariable=self.note_var, anchor="w")
        self.note_label.pack(side="left")

        # ---- 错误提示行（读取/保存/解析失败时显示，平时为空）----
        self.error_var = tk.StringVar(value="")
        error_frame = tk.Frame(root, padx=10)
        error_frame.pack(fill="x")
        self.error_label = tk.Label(error_frame, textvariable=self.error_var,
                                    anchor="w", fg="#b00020")
        self.error_label.pack(side="left")

        # ---- 琴谱编辑区域（左：编辑框；右：谱面格式说明 Task 23）----
        tk.Label(root, text="琴谱:", anchor="w", padx=10).pack(fill="x")
        editor_frame = tk.Frame(root)
        editor_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # 右侧：谱面格式说明（只读文本，可滚动）。先 pack 右侧以保证拿到固定宽度，
        # 不改变窗口尺寸、不改变既有控件的相对位置。
        help_side = tk.Frame(editor_frame)
        help_side.pack(side="right", fill="y", padx=(8, 0))
        self.format_help_text = tk.Text(help_side, width=30, height=10, wrap="word",
                                        background="#f7f7f7", relief="solid",
                                        borderwidth=1)
        help_scroll = tk.Scrollbar(help_side, orient="vertical",
                                   command=self.format_help_text.yview)
        self.format_help_text.configure(yscrollcommand=help_scroll.set)
        self.format_help_text.pack(side="left", fill="y")
        help_scroll.pack(side="left", fill="y")
        self.format_help_text.insert("1.0", FORMAT_HELP_TEXT)
        self.format_help_text.configure(state="disabled")

        # 左侧：琴谱编辑框（占据剩余空间）
        self.score_text = scrolledtext.ScrolledText(editor_frame, height=10, wrap="word")
        self.score_text.pack(side="left", fill="both", expand=True)
        self.score_text.insert("1.0", self._initial_score())
        self._reset_modified_flag()
        # 用户编辑琴谱时通知 controller（UI 自己不解析琴谱）
        self.score_text.bind("<<Modified>>", self._on_score_modified)

        # ---- 控制按钮 ----
        control_frame = tk.Frame(root, padx=10, pady=4)
        control_frame.pack(fill="x")
        self.start_button = tk.Button(control_frame, text="开始",
                                      command=self.on_start, width=10)
        self.pause_button = tk.Button(control_frame, text="暂停",
                                      command=self.on_pause, width=10)
        self.resume_button = tk.Button(control_frame, text="继续",
                                       command=self.on_resume, width=10)
        self.stop_button = tk.Button(control_frame, text="停止",
                                     command=self.on_stop, width=10)
        self.reset_button = tk.Button(control_frame, text="重置",
                                      command=self.on_reset, width=10)
        for button in (self.start_button, self.pause_button, self.resume_button,
                       self.stop_button, self.reset_button):
            button.pack(side="left", padx=3)

        # ---- 打开 / 保存（Task 16 才实现真实文件操作）----
        file_frame = tk.Frame(root, padx=10, pady=4)
        file_frame.pack(fill="x")
        self.open_button = tk.Button(file_frame, text="打开",
                                     command=self.on_open, width=10)
        self.save_button = tk.Button(file_frame, text="保存",
                                     command=self.on_save, width=10)
        self.open_button.pack(side="left", padx=3)
        self.save_button.pack(side="left", padx=3)

        # ---- 谱库（Task 18）：显示 Scores 目录里的文件夹与 .txt 琴谱 ----
        library_frame = tk.Frame(root, padx=10, pady=4)
        library_frame.pack(fill="x")
        tk.Label(library_frame, text="谱库:", anchor="w").pack(anchor="w")

        self.current_path_label = tk.Label(library_frame, text="", anchor="w",
                                           fg="#555555")
        self.current_path_label.pack(anchor="w")

        tree_frame = tk.Frame(library_frame)
        tree_frame.pack(fill="x")
        self.library_tree = ttk.Treeview(tree_frame, height=6, show="tree")
        self.library_tree.pack(side="left", fill="x", expand=True)
        lib_scroll = ttk.Scrollbar(tree_frame, orient="vertical",
                                   command=self.library_tree.yview)
        lib_scroll.pack(side="left", fill="y")
        self.library_tree.configure(yscrollcommand=lib_scroll.set)
        self.library_tree.tag_configure("folder", foreground="#0066cc")
        self.library_tree.tag_configure("file", foreground="#000000")
        self.library_tree.tag_configure("root", foreground="#000000")
        # 双击 .txt 加载；单击选中（folder 双击不加载）
        self.library_tree.bind("<Double-1>", self.on_library_load)

        lib_btn_frame = tk.Frame(library_frame)
        lib_btn_frame.pack(fill="x")
        self.refresh_library_button = tk.Button(lib_btn_frame, text="刷新谱库",
                                                command=self.on_library_refresh, width=10)
        self.new_folder_button = tk.Button(lib_btn_frame, text="新建文件夹",
                                           command=self.on_library_new_folder, width=10)
        self.new_score_button = tk.Button(lib_btn_frame, text="新建琴谱",
                                          command=self.on_library_new_score, width=9)
        self.save_as_button = tk.Button(lib_btn_frame, text="另存为",
                                        command=self.on_library_save_as, width=9)
        self.rename_button = tk.Button(lib_btn_frame, text="重命名",
                                       command=self.on_rename, width=9)
        self.delete_button = tk.Button(lib_btn_frame, text="删除",
                                       command=self.on_delete, width=9)
        self.refresh_library_button.pack(side="left", padx=3, pady=(4, 0))
        self.new_folder_button.pack(side="left", padx=3, pady=(4, 0))
        self.new_score_button.pack(side="left", padx=3, pady=(4, 0))
        self.save_as_button.pack(side="left", padx=3, pady=(4, 0))
        self.rename_button.pack(side="left", padx=3, pady=(4, 0))
        self.delete_button.pack(side="left", padx=3, pady=(4, 0))

        # ---- 快捷键提示（只显示，快捷键由核心的 Enter Hook 负责）----
        shortcut_frame = tk.Frame(root, padx=10, pady=8)
        shortcut_frame.pack(fill="x")
        self.shortcut_labels = []
        for line in SHORTCUT_LINES:
            label = tk.Label(shortcut_frame, text=line, anchor="w", fg="#555555")
            label.pack(fill="x")
            self.shortcut_labels.append(label)

        # 关闭窗口时走正常退出路径
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 启动时自动扫描谱库，并显示当前琴谱路径
        self.refresh_library()
        self._update_current_path()

    # ---------- 初始值（来自 controller 或占位） ----------

    def _initial_status(self):
        if self.controller is not None:
            return self.controller.status_text
        return STATUS_READY

    def _initial_note(self):
        if self.controller is not None:
            return self.controller.current_note_text
        return PLACEHOLDER_NOTE

    def _initial_score(self):
        if self.controller is not None:
            return self.controller.score_text
        return PLACEHOLDER_SCORE

    # ---------- 小工具 ----------

    def _reset_modified_flag(self):
        try:
            self.score_text.edit_modified(False)
        except tk.TclError:
            pass

    def refresh_from_controller(self, snapshot=None):
        """把 controller 的状态同步到界面（快照可由 controller.refresh() 提供）。"""
        if self.controller is None:
            return
        if snapshot is None:
            snapshot = self.controller.refresh()
        if snapshot is None:
            status = self.controller.status_text
            note = self.controller.current_note_text
            error = ""
        elif len(snapshot) >= 3:
            status, note, error = snapshot[0], snapshot[1], snapshot[2]
        else:
            status, note = snapshot[0], snapshot[1]
            error = ""
        self.status_var.set(str(status))
        self.note_var.set(str(note))
        self.error_var.set(str(error or ""))
        self._update_current_path()

    # ---------- 界面查询（自动化测试用） ----------

    def status_text(self):
        return self.status_var.get()

    def note_text(self):
        return self.note_var.get()

    def score_content(self):
        return self.score_text.get("1.0", "end-1c")

    def button_labels(self):
        return {
            "start": self.start_button.cget("text"),
            "pause": self.pause_button.cget("text"),
            "resume": self.resume_button.cget("text"),
            "stop": self.stop_button.cget("text"),
            "reset": self.reset_button.cget("text"),
            "open": self.open_button.cget("text"),
            "save": self.save_button.cget("text"),
        }

    def shortcut_texts(self):
        return [label.cget("text") for label in self.shortcut_labels]

    # ---------- 按钮行为 ----------

    def _on_score_modified(self, _event=None):
        if not self.score_text.edit_modified():
            return
        self._reset_modified_flag()
        if self.controller is not None:
            self.controller.score_modified(self.score_content())
            self._update_current_path()

    def on_start(self):
        if self.controller is not None:
            self.controller.start()
        else:
            self.status_var.set(STATUS_PLAYING)
        self.refresh_from_controller()

    def on_pause(self):
        if self.controller is not None:
            self.controller.pause()
        else:
            self.status_var.set(STATUS_PAUSED)
        self.refresh_from_controller()

    def on_resume(self):
        if self.controller is not None:
            self.controller.resume()
        else:
            self.status_var.set(STATUS_PLAYING)
        self.refresh_from_controller()

    def on_stop(self):
        if self.controller is not None:
            self.controller.stop()
        else:
            self.status_var.set(STATUS_STOPPED)
        self.refresh_from_controller()

    def on_reset(self):
        if self.controller is not None:
            self.controller.reset()
        else:
            self.status_var.set(STATUS_RESET)
        self.refresh_from_controller()

    def on_open(self):
        """Open：让用户选择 .txt -> 交给 controller 读取（UI 不解析琴谱）。"""
        if self.controller is None:
            self.status_var.set(STATUS_OPEN_PLACEHOLDER)
            return
        path = self._ask_open_path()
        if not path:
            # 用户取消：不动 Score、不动播放状态
            self.status_var.set(STATUS_OPEN_CANCELLED)
            self.controller.report_status(STATUS_OPEN_CANCELLED)
            return
        result = self.controller.open_file(path)
        if not isinstance(result, str):
            result = ""
        if result.startswith("Opened"):
            # Open 成功后把文件内容放进 Score 文本框（controller 已同时记录文本）
            self._set_score_text(self.controller.score_text)
        self._apply_result(result)

    def on_save(self):
        """Save：有已知路径就直接写回；没有则弹出"另存为"（UI 不写文件）。"""
        if self.controller is None:
            self.status_var.set(STATUS_SAVE_PLACEHOLDER)
            return
        result = self.controller.save_file()
        if result == NEED_DIALOG:
            path = self._ask_save_path()
            if not path:
                self.status_var.set(STATUS_SAVE_CANCELLED)
                self.controller.report_status(STATUS_SAVE_CANCELLED)
                return
            result = self.controller.save_file(path)
        if not isinstance(result, str):
            result = ""
        self._apply_result(result)

    # ---------- 谱库（Task 18）----------

    def refresh_library(self):
        """扫描真实 Scores 目录并重建树：文件夹与 .txt 琴谱分开展示。"""
        tree = self.library_tree
        tree.delete(*tree.get_children())
        root_iid = "Scores"
        tree.insert("", "end", iid=root_iid, text="谱库", values=("root", ""),
                    tags=("root",), open=True)
        if self.controller is None:
            return
        entries = self.controller.library_scan() or []

        def iid_of(e):
            return ("D:" if e["type"] == "folder" else "F:") + e["relpath"]

        def parent_of(e):
            p = e["parent"]
            return ("D:" + p) if p else root_iid

        # 先插文件夹，再插文件，保证父目录 iid 已存在
        for e in entries:
            if e["type"] == "folder":
                tree.insert(parent_of(e), "end", iid=iid_of(e), text=e["name"],
                            values=("folder", e["relpath"]), tags=("folder",))
        for e in entries:
            if e["type"] == "file":
                tree.insert(parent_of(e), "end", iid=iid_of(e), text=e["name"],
                            values=("file", e["relpath"]), tags=("file",))

    def on_library_refresh(self):
        self.refresh_library()
        self.status_var.set("谱库已刷新")

    def on_library_load(self, _event=None):
        """双击 .txt 琴谱：经 controller 加载到 Score 区，不自动播放。"""
        if self.controller is None:
            return
        selection = self.library_tree.selection()
        if not selection:
            return
        values = self.library_tree.item(selection[0], "values")
        if not values or values[0] != "file":
            return  # 只加载 .txt 琴谱，文件夹不加载
        relpath = values[1]
        result = self.controller.library_load_score(relpath)
        self._set_score_text(self.controller.score_text)
        self._update_current_path()
        self._apply_result(result)

    def on_library_new_folder(self):
        """新建文件夹：弹出名称输入框（可测试路径见 create_folder_by_name）。"""
        if self.controller is None:
            return
        name = self._ask_folder_name()
        if not name:
            self.status_var.set("新建文件夹已取消")
            return
        self.create_folder_by_name(name)

    def create_folder_by_name(self, name):
        """可测试接口：直接按名称创建文件夹（不弹对话框）。"""
        if self.controller is None:
            return ""
        result = self.controller.library_create_folder(name)
        self.refresh_library()
        self._apply_result(result)
        return result

    def on_library_new_score(self):
        """新建琴谱：弹出名称输入框（可测试路径见 new_score_by_name）。"""
        if self.controller is None:
            return
        name = self._ask_new_score_name()
        if not name:
            self.status_var.set("新建琴谱已取消")
            return
        self.new_score_by_name(name)

    def new_score_by_name(self, name):
        """可测试接口：直接按名称新建琴谱（不弹对话框），进入编辑状态。"""
        if self.controller is None:
            return ""
        result = self.controller.library_new_score(name)
        self._set_score_text(self.controller.score_text)
        self.refresh_library()
        self._update_current_path()
        self._apply_result(result)
        return result

    def on_library_save_as(self):
        """另存为：弹出名称输入框（可测试路径见 save_as_by_path）。"""
        if self.controller is None:
            return
        rel = self._ask_save_as_name()
        if not rel:
            self.status_var.set("另存为已取消")
            return
        self.save_as_by_path(rel)

    def save_as_by_path(self, relpath):
        """可测试接口：直接按相对路径另存为（不弹对话框）。"""
        if self.controller is None:
            return ""
        result = self.controller.library_save_as(relpath)
        self.refresh_library()
        self._update_current_path()
        self._apply_result(result)
        return result

    def selected_library_item(self):
        """返回 (type, relpath, name)；未选中或选中根节点时返回 (None, None, None)。"""
        sel = self.library_tree.selection()
        if not sel:
            return (None, None, None)
        iid = sel[0]
        values = self.library_tree.item(iid, "values")
        if not values or values[0] not in ("file", "folder"):
            return (None, None, None)
        return (values[0], values[1], self.library_tree.item(iid, "text"))

    def on_rename(self):
        """重命名选中项：弹出名称输入框（可测试路径见 rename_selected_by_name）。"""
        if self.controller is None:
            return
        typ, relpath, name = self.selected_library_item()
        if typ is None:
            self.status_var.set("未选中要重命名的项")
            return
        new_name = self._ask_rename_name(name)
        if not new_name:
            self.status_var.set("重命名已取消")
            return
        if new_name == name:
            return
        self.rename_selected_by_name(new_name)

    def rename_selected_by_name(self, new_name):
        """可测试接口：直接对选中项按新名称重命名（不弹对话框）。"""
        if self.controller is None:
            return ""
        typ, relpath, _name = self.selected_library_item()
        if typ is None:
            return ""
        if typ == "file":
            # 重命名保持在原文件夹内，不把文件意外移动到 Scores 根目录
            parent = relpath.rsplit("/", 1)[0] if "/" in relpath else ""
            new_rel = (parent + "/" + new_name) if parent else new_name
            result = self.controller.library_rename_score(relpath, new_rel)
        else:
            result = self.controller.library_rename_folder(relpath, new_name)
        self.refresh_library()
        self._update_current_path()
        self._apply_result(result)
        return result

    def on_delete(self):
        """删除选中项：先确认（可测试路径见 delete_selected_now）。"""
        if self.controller is None:
            return
        typ, relpath, name = self.selected_library_item()
        if typ is None:
            self.status_var.set("未选中要删除的项")
            return
        if not self._confirm_delete(name):
            self.status_var.set("删除已取消")
            return
        self.delete_selected_now()

    def delete_selected_now(self):
        """可测试接口：直接删除选中项（不弹确认）。"""
        if self.controller is None:
            return ""
        typ, relpath, _name = self.selected_library_item()
        if typ is None:
            return ""
        if typ == "file":
            result = self.controller.library_delete_score(relpath)
        else:
            result = self.controller.library_delete_folder(relpath)
        self._set_score_text(self.controller.score_text)   # 删除当前谱时同步清空编辑区
        self.refresh_library()
        self._update_current_path()
        self._apply_result(result)
        return result

    def _ask_rename_name(self, current):
        try:
            from tkinter import simpledialog
            return simpledialog.askstring("重命名", "新名称：",
                                          initialvalue=current, parent=self.root) or ""
        except Exception:  # noqa: BLE001 - 对话框异常不崩溃
            return ""

    def _confirm_delete(self, name):
        try:
            return messagebox.askyesno("删除", "确定删除「" + str(name) + "」吗？",
                                       parent=self.root)
        except Exception:  # noqa: BLE001 - 对话框异常不崩溃
            return False

    def _ask_folder_name(self):
        try:
            from tkinter import simpledialog
            return simpledialog.askstring("新建文件夹", "文件夹名称：",
                                          parent=self.root) or ""
        except Exception:  # noqa: BLE001 - 对话框异常不崩溃
            return ""

    def _ask_new_score_name(self):
        try:
            from tkinter import simpledialog
            return simpledialog.askstring(
                "新建琴谱", "琴谱名称（自动补 .txt，可在已存在子文件夹下）：",
                parent=self.root) or ""
        except Exception:  # noqa: BLE001 - 对话框异常不崩溃
            return ""

    def _ask_save_as_name(self):
        try:
            from tkinter import simpledialog
            return simpledialog.askstring(
                "另存为", "保存到（相对 Scores 目录，可含子文件夹，如 子文件夹/名称）：",
                parent=self.root) or ""
        except Exception:  # noqa: BLE001 - 对话框异常不崩溃
            return ""

    def _update_current_path(self):
        cp = getattr(self.controller, "current_path", None)
        modified = getattr(self.controller, "modified", False)
        name = os.path.basename(cp) if cp else "（未打开）"
        text = "当前琴谱: " + name + "　当前路径: " + (cp or "（无）")
        if modified:
            text += " *"
        self.current_path_label.config(text=text)

    # ---------- 文件对话框（标准库 filedialog，controller 不碰对话框） ----------

    def _ask_open_path(self):
        try:
            return filedialog.askopenfilename(
                parent=self.root, title="打开琴谱",
                filetypes=FILE_TYPES) or ""
        except Exception:  # noqa: BLE001 - 对话框异常不应让程序崩溃
            return ""

    def _ask_save_path(self):
        try:
            return filedialog.asksaveasfilename(
                parent=self.root, title="保存琴谱",
                defaultextension=DEFAULT_EXTENSION,
                filetypes=FILE_TYPES) or ""
        except Exception:  # noqa: BLE001
            return ""

    # ---------- 界面文本工具 ----------

    def _set_score_text(self, text):
        self.score_text.delete("1.0", "end")
        self.score_text.insert("1.0", text)
        self._reset_modified_flag()

    def _apply_result(self, result):
        """把 controller 返回的结果文字显示出来；同时刷新状态/音符/错误。"""
        if result:
            if result.startswith("错误"):
                # 失败：显示明确状态，详细原因放进错误行（不崩溃、不 traceback）
                self.status_var.set("操作失败")
                self.error_var.set(result)
            else:
                self.status_var.set(result)
                self.error_var.set("")
        self.refresh_from_controller()

    # ---------- 退出 ----------

    def on_close(self):
        """关闭窗口：先让 controller 收尾（释放输入 / 停 Hook），再销毁窗口。"""
        if self.controller is not None:
            try:
                self.controller.shutdown()
            except Exception:  # noqa: BLE001 - 退出路径不应因收尾异常而卡住
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main(controller=None, self_close_ms=None):
    """启动 GUI。

    参数:
        controller:    注入的播放器连接对象（Task 15）。None 时为纯占位 UI。
        self_close_ms: 仅自动化测试使用。给定毫秒数时自动关闭窗口，
                       便于在没有人工点击的情况下验证"启动 -> 建窗 -> 正常关闭"。
    """
    root = tk.Tk()
    app = HarmonicaUI(root, controller=controller)
    if self_close_ms is not None:
        root.after(int(self_close_ms), app.on_close)
    root.mainloop()
    return app
