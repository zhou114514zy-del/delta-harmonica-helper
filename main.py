"""三角洲口琴自动弹奏辅助工具 - 程序入口

当前阶段（Task 14）：默认启动极简 GUI 外壳（ui.py）。

入口约定：
    python main.py          启动 GUI（本 Task 的目标）
    python main.py --cli    启动原来的命令行演奏模式（Task 11-13 的行为，保留不变）

GUI 只是"薄外壳"：显示界面并接收点击，**不接任何核心逻辑**。
音符解析、映射、键鼠模拟、Enter Hook、min_hold_ms、Timer、index 推进、release_all
全部仍然由已有模块负责（Task 15 才做 UI 与核心的连接）。

命令行模式（run_cli）就是 Task 11-13 验证过的行为，原样保留：
    Enter 按下 -> 播放当前音符；Enter 松开 -> 满足 min_hold_ms 后释放并前进
    Esc 一次   -> 紧急停止（index 不变）；Esc 连按两次 -> 正常退出
    R          -> 重置到琴谱开头

测试专用环境变量（不设置时程序行为不受影响）：
    DSH_ENTER_TEST_AUTOSTART_MS  启动前等待毫秒数（给自动化脚本留准备时间）
    DSH_ENTER_TEST_VK_REPORT     把钩子看到的原始 vkCode 写到该路径（诊断用）
    DSH_UI_TEST_SELF_CLOSE_MS    仅测试用：GUI 启动后多少毫秒自动关闭
"""

import os
import sys
import time

# 固定测试琴谱（命令行模式使用）
SCORE_TEXT = "1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]"
# Task 13：两次 Esc 之间的间隔在这个时间内算"连按两次" -> 退出
ESC_QUIT_WINDOW_S = 0.8


def run_cli():
    """命令行演奏模式（Task 11-13 的行为，原样保留）。"""
    import input as io
    from harmonica_app import FixedScorePlayer, load_min_hold_ms
    from score import parse_score_notes

    # Task 12：最小音符持续时间（来自 config.json，读不到就用默认值 50ms）
    min_hold_ms = load_min_hold_ms()

    print("Delta Harmonica Helper - CLI mode")
    print(f"Score: {SCORE_TEXT}")
    print(f"min_hold_ms = {min_hold_ms}")
    print("Press Enter to play the current note, release to advance.")
    print("Press Esc once to stop (emergency stop), twice quickly to quit.")
    print("Press R to reset to the beginning of the score.")

    # 测试脚本以隐藏窗口方式启动本程序时，用这个环境变量留出准备时间。
    _test_delay_ms = os.environ.get("DSH_ENTER_TEST_AUTOSTART_MS")
    if _test_delay_ms:
        time.sleep(int(_test_delay_ms) / 1000)

    notes = parse_score_notes(SCORE_TEXT)
    player = FixedScorePlayer(notes, min_hold_ms=min_hold_ms)
    print(f"Loaded {player.note_count()} notes.")
    print(f"Next note: {player.current_note()}")

    _last_escape_at = 0.0

    def on_enter_down():
        player.enter_down()
        print(f"Enter DOWN -> note={player.current_note()} {player.current_state_text()}", flush=True)

    def on_enter_up():
        player.enter_up()
        print(f"Enter UP   -> index={player.index}/{player.note_count()} {player.current_state_text()}", flush=True)

    def on_escape():
        """Esc：第一次紧急停止；在窗口期内再按一次则退出。

        这里跑在 input.py 的回调工作线程上，不做任何阻塞操作。
        """
        nonlocal _last_escape_at
        now = time.monotonic()
        double_press = (now - _last_escape_at) <= ESC_QUIT_WINDOW_S
        _last_escape_at = now

        if double_press:
            print("Esc x2 -> quitting.", flush=True)
            player.shutdown()          # 失效 timer + 释放全部输入
            io.stop_enter_listener()   # 主循环随即退出
            return

        player.emergency_stop()
        print(f"Esc -> emergency stop. index={player.index}/{player.note_count()} "
              f"{player.current_state_text()}", flush=True)

    def on_reset():
        """R：重置到琴谱开头。"""
        player.reset()
        print(f"R -> reset. index={player.index}/{player.note_count()} "
              f"next={player.current_note()} {player.current_state_text()}", flush=True)

    io.set_enter_callbacks(on_down=on_enter_down, on_up=on_enter_up)
    io.set_escape_callback(on_escape=on_escape)
    io.set_reset_callback(on_reset)

    io.start_enter_listener()

    # 一直等待，直到 Esc 连按两次触发 on_escape 把钩子卸掉。
    while io.is_listening():
        time.sleep(0.1)

    # ---- 正常退出清理（Task 13）----
    io._drain_callbacks()        # 等已经排队的回调跑完
    player.shutdown()            # 失效 timer + 释放全部模拟输入（二次兜底）
    io.release_all()             # 输入模块层面的兜底释放

    # 测试脚本可选：把钩子观察到的原始 vkCode 写到文件（诊断用）。
    _vk_report = os.environ.get("DSH_ENTER_TEST_VK_REPORT")
    if _vk_report:
        names = {
            0x0D: "Enter", 0x1B: "Esc", 0x52: "R", 0x41: "A", 0x5A: "Z", 0x20: "Space",
            0x09: "Tab", 0x10: "Shift", 0x11: "Ctrl", 0x2E: "Delete",
        }
        with open(_vk_report, "w", encoding="utf-8") as fh:
            fh.write("raw vkCode down sequence:\n")
            for code in io.seen_vk_codes():
                fh.write(f"  {code} (0x{code:02X}) = {names.get(code, '?')}\n")

    print("Listener stopped.", flush=True)
    return 0


def run_gui():
    """启动 GUI 外壳（Task 14），并把它接到播放器核心上（Task 15）。"""
    import tkinter as tk

    from app_controller import AppController
    from ui import HarmonicaUI

    root = tk.Tk()
    # 核心回调跑在工作线程上，用 root.after 把它们切回 UI 线程再更新界面
    controller = AppController(ui_thread_after=root.after)
    app = HarmonicaUI(root, controller=controller)
    controller.schedule_poll(root)          # 用 after() 定时刷新，不阻塞 UI

    self_close_ms = os.environ.get("DSH_UI_TEST_SELF_CLOSE_MS")
    if self_close_ms:
        root.after(int(self_close_ms), app.on_close)

    root.mainloop()
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--cli" in argv:
        return run_cli()
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
