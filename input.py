"""输入相关模块。

当前阶段（Task 5）：只拦截 Enter，其他按键正常放行。

提供（接口与 Task 4 保持兼容）：
    press_key(key) / release_key(key)                    -- 键盘按下 / 释放（Task 2，模拟输入）
    press_mouse(button) / release_mouse(button)           -- 鼠标按下 / 释放（Task 3，模拟输入）
    move_mouse(x, y)                                      -- 移动指针（Task 3）
    set_enter_callbacks(on_down, on_up)                   -- 注册 Enter 回调（Task 4）
    start_enter_listener() / stop_enter_listener()        -- 开始 / 停止监听（Task 4/5）
    is_listening() / enter_is_down()                      -- 状态查询（Task 4）
    set_escape_callback(on_escape)                        -- 注册 Esc 回调（Task 4，仅用于退出）

拦截方式：用 ctypes 自己安装用户态低级键盘钩子 WH_KEYBOARD_LL。
    - 只对 VK_RETURN（Enter）返回 1，表示"吞掉这个事件"，它不会再传给获得焦点的程序；
    - 其他所有按键一律 CallNextHookEx 放行（A / Z / Space / Shift / Tab ...）；
    - 停止监听时会卸载钩子，键盘立即恢复正常。
不使用 pynput 的全局 suppress（那是整体拦截，会影响所有按键）。

注意：钩子回调运行在系统投递键盘事件的线程上，里面绝不能阻塞或做慢操作，
否则会拖慢整个系统的键盘响应。因此回调里只做状态判断，用户回调交给独立工作线程执行。
"""

import ctypes
import os
import threading
import time
from ctypes import wintypes

from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Button, Controller as MouseController

# 控制器实例：复用同一个对象，避免重复创建。
_keyboard = KeyboardController()
_mouse = MouseController()

# 对外暴露 left / middle / right 三个名称，其余按键不作为当前阶段的接口。
_MOUSE_BUTTONS = {
    "left": Button.left,
    "middle": Button.middle,
    "right": Button.right,
}

# ---- Win32 常量 ----
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_R = 0x52

_KEY_DOWN_MESSAGES = (WM_KEYDOWN, WM_SYSKEYDOWN)
_KEY_UP_MESSAGES = (WM_KEYUP, WM_SYSKEYUP)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = wintypes.WPARAM


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = ctypes.c_ssize_t
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostThreadMessageW.restype = wintypes.BOOL
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD

# ---- Task 4/5：全局 Enter 检测 + 选择性拦截的内部状态 ----
_hook = None                     # 钩子句柄，非 None 表示正在监听
_hook_proc = None                # 必须保留引用，否则回调可能被回收
_hook_thread = None
_hook_thread_id = None
_hook_ready = threading.Event()

_listener = None                 # 兼容 Task 4 的返回对象语义
_enter_down = False              # Enter 当前的逻辑状态：True = 已按下且尚未松开
_escape_down = False
_r_down = False
_on_enter_down = None
_on_enter_up = None
_on_escape = None
_on_reset = None

_callback_queue = []
_callback_lock = threading.Lock()
_callback_worker = None
_callback_worker_wake = threading.Event()
_callback_worker_stop = threading.Event()

# 诊断用：记录钩子看到过的原始 vkCode（仅当设置了 DSH_ENTER_TEST_VK_REPORT 时启用）
_seen_vk = []
_seen_vk_enabled = bool(os.environ.get("DSH_ENTER_TEST_VK_REPORT"))

# 由本程序按下、尚未释放的按键（release_all() 用它兜底，避免卡键）
_held_keys = set()
# 由本程序按下、尚未释放的鼠标键（单独追踪，避免误释放用户自己按住的鼠标键）
_held_mouse_buttons = set()

# 已入队但还没执行完的用户回调数量（_drain_callbacks 用它等待回调跑完）
_pending_callbacks = 0


def seen_vk_codes():
    """返回钩子观察到过的原始 vkCode 列表（诊断用）。"""
    return list(_seen_vk)


def press_key(key):
    """模拟按下指定按键。

    参数:
        key: 单个字符（如 "z"）、空格 " "、或 pynput 的特殊键（如 Key.enter）。
    """
    normalized = _normalize_key(key)
    # 记录"当前处于按下状态"的按键，供 release_all() 兜底释放，避免退出后卡住按键。
    _held_keys.add(normalized)
    try:
        _keyboard.press(normalized)
    except Exception as exc:
        # 解析不了的键不应该让调用方崩掉（例如输入层遇到非法字符）
        _held_keys.discard(normalized)
        print(f"[warn] press_key failed for {key!r}: {exc!r}", flush=True)


def release_key(key):
    """模拟释放指定按键。

    参数与 press_key 相同。释放一个当前并没有按下的键不应该让程序崩掉，
    所以底层异常在这里被吞掉并给出警告，同时清掉 held 记录。
    """
    normalized = _normalize_key(key)
    try:
        _keyboard.release(normalized)
    except Exception as exc:  # noqa: BLE001 - 释放失败不应影响调用方
        print(f"[warn] release_key failed for {normalized!r}: {exc!r}", flush=True)
    _held_keys.discard(normalized)


def held_keys():
    """返回当前"由本程序按下且尚未释放"的键盘按键集合（副本）。"""
    return set(_held_keys)


def held_mouse_buttons():
    """返回当前"由本程序按下且尚未释放"的鼠标按键集合（副本，元素是 Button）。"""
    return set(_held_mouse_buttons)


def mouse_button_name(button):
    """把 Button 转回可读名称（left / middle / right），用于日志与测试。"""
    try:
        normalized = _normalize_button(button)
    except ValueError:
        return str(button)
    for name, candidate in _MOUSE_BUTTONS.items():
        if candidate == normalized:
            return name
    return str(button)


def release_all():
    """释放所有"由本程序按下且尚未释放"的键盘键与鼠标键。

    只动本程序自己按下、且仍在 held 状态里的输入：
      - 用户原本就按住的键或鼠标键不会被碰（它们从来没进过 held 集合）；
      - 已经释放过的不再重复释放；
      - 执行结束后两个 held 集合都为空。

    释放顺序：先鼠标键，再键盘键。
    """
    for button in sorted(_held_mouse_buttons, key=mouse_button_name):
        try:
            _mouse.release(button)
        except Exception as exc:  # noqa: BLE001 - 释放失败不应影响退出流程
            print(f"[warn] release_all failed for mouse {mouse_button_name(button)}: {exc!r}", flush=True)
    _held_mouse_buttons.clear()

    for key in sorted(_held_keys, key=str):
        try:
            _keyboard.release(key)
        except Exception as exc:  # noqa: BLE001 - 释放失败不应影响退出流程
            print(f"[warn] release_all failed for key {key!r}: {exc!r}", flush=True)
    _held_keys.clear()


def press_mouse(button):
    """模拟按下指定鼠标按键。

    参数:
        button: "left" / "middle" / "right"（大小写不敏感，也接受 Button.left 等）。
    """
    normalized = _normalize_button(button)
    # 记录"由本程序按下"的鼠标键，供 release_all() 兜底释放，避免退出后卡住鼠标键
    _held_mouse_buttons.add(normalized)
    _mouse.press(normalized)


def release_mouse(button):
    """模拟释放指定鼠标按键。

    参数与 press_mouse 相同。释放一个当前并没有按下的鼠标键不应该让程序崩掉
    （例如用户已经自己松开、或该键本来就没被按下），所以这里吞掉底层异常并警告。
    """
    normalized = _normalize_button(button)
    try:
        _mouse.release(normalized)
    except Exception as exc:  # noqa: BLE001 - 释放失败不应影响调用方
        print(f"[warn] release_mouse failed for {mouse_button_name(normalized)}: {exc!r}", flush=True)
    _held_mouse_buttons.discard(normalized)


def move_mouse(x, y):
    """把鼠标指针移动到屏幕坐标 (x, y)。"""
    _mouse.position = (x, y)


def set_enter_callbacks(on_down=None, on_up=None):
    """注册 Enter 按下 / 松开时的回调（回调只负责自己要做的事）。"""
    global _on_enter_down, _on_enter_up
    _on_enter_down = on_down
    _on_enter_up = on_up


def set_escape_callback(on_escape=None):
    """注册 Esc 按下时的回调（当前用于紧急停止 / 退出）。"""
    global _on_escape
    _on_escape = on_escape


def set_reset_callback(on_reset=None):
    """注册 R 按下时的回调（Task 13：重置到琴谱开头）。"""
    global _on_reset
    _on_reset = on_reset


def enter_is_down():
    """返回 Enter 目前的逻辑状态（True = 处于按下中）。"""
    return _enter_down


def is_listening():
    """返回全局监听是否仍在运行。"""
    return _hook is not None


def start_enter_listener():
    """安装低级键盘钩子，开始全局监听，并选择性拦截 Enter。

    - 全局生效：本程序不在前台时同样有效；
    - 选择性拦截：只吞掉 Enter，其他按键全部放行；
    - 去重：按住 Enter 时的重复 key-down 只对应一次 DOWN。
    """
    global _hook, _hook_thread, _hook_thread_id, _listener

    if _hook is not None:
        return _listener

    _hook_ready.clear()
    _hook_thread = threading.Thread(target=_hook_loop, name="enter-hook", daemon=True)
    _hook_thread.start()
    if not _hook_ready.wait(timeout=5.0):
        raise RuntimeError("安装键盘钩子超时")
    if _hook is None:
        raise ctypes.WinError(ctypes.get_last_error())

    _listener = _ListenerHandle()
    return _listener


def stop_enter_listener():
    """卸载钩子，停止监听与拦截，并兜底释放已经模拟按下的按键。

    顺序很重要：
      1. 先摘掉钩子（不再拦截新事件，也不再产生新回调）；
      2. 等已经排队的回调跑完（例如刚触发的 Enter UP -> Z UP）；
      3. 最后无条件 release_all()，确保任何情况下都不留下卡住的 Z。
    """
    global _hook, _hook_thread, _hook_thread_id, _listener

    if _hook is None and _hook_thread is None:
        return
    tid = _hook_thread_id
    _hook = None
    _hook_thread_id = None
    _listener = None
    if tid:
        _user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
    if _hook_thread is not None:
        _hook_thread.join(timeout=3.0)
        _hook_thread = None

    _drain_callbacks(timeout=1.0)
    release_all()


class _ListenerHandle:
    """对外的监听句柄：兼容 Task 4 里对监听对象的用法。"""

    @property
    def running(self):
        return _hook is not None


# ---- 钩子线程 ----

def _hook_loop():
    global _hook, _hook_proc, _hook_thread_id

    _hook_thread_id = _kernel32.GetCurrentThreadId()
    _hook_proc = HOOKPROC(_hook_callback)
    _hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, _hook_proc, None, 0)
    if not _hook:
        _hook = None
        _hook_thread_id = None
        _hook_ready.set()
        return

    _hook_ready.set()

    msg = wintypes.MSG()
    while _hook is not None:
        result = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if result == 0:  # WM_QUIT：收到了主动退出
            break
        if result == -1:  # 出错；绝不能因此卸载钩子（会导致拦截静默失效）
            continue
        _user32.TranslateMessage(ctypes.byref(msg))
        _user32.DispatchMessageW(ctypes.byref(msg))

    if _hook is not None:
        _user32.UnhookWindowsHookEx(_hook)
        _hook = None
    _hook_proc = None


def _hook_callback(n_code, w_param, l_param):
    """低级键盘钩子回调。返回 1 = 吞掉该事件，不再传给其他程序。"""
    global _enter_down, _escape_down, _r_down

    if n_code != 0:  # HC_ACTION 以外的值必须直接传下去
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    try:
        info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = int(info.vkCode)
        message = int(w_param)

        if message in _KEY_DOWN_MESSAGES and _seen_vk_enabled:
            _seen_vk.append(vk)

        if vk == VK_RETURN:
            if message in _KEY_DOWN_MESSAGES:
                if not _enter_down:  # 长按自动重复产生的 key-down 在这里被丢掉
                    _enter_down = True
                    _emit(_on_enter_down)
            elif message in _KEY_UP_MESSAGES:
                if _enter_down:
                    _enter_down = False
                    _emit(_on_enter_up)
            return 1  # 吞掉 Enter

        if vk == VK_ESCAPE:
            if message in _KEY_DOWN_MESSAGES:
                if not _escape_down:
                    _escape_down = True
                    _emit(_on_escape)
            elif message in _KEY_UP_MESSAGES:
                _escape_down = False
            # Esc 不拦截，正常放行

        elif vk == VK_R:
            if message in _KEY_DOWN_MESSAGES:
                if not _r_down:
                    _r_down = True
                    _emit(_on_reset)
            elif message in _KEY_UP_MESSAGES:
                _r_down = False
            # R 不拦截，正常放行
    except Exception:  # 回调里绝不能抛异常，否则会影响系统键盘
        pass

    return _user32.CallNextHookEx(None, n_code, w_param, l_param)


# ---- 用户回调的执行 ----
# 钩子回调必须立刻返回，所以用户回调交给独立工作线程串行执行。

def _emit(callback):
    global _pending_callbacks
    if callback is None:
        return
    _ensure_callback_worker()
    with _callback_lock:
        _callback_queue.append(callback)
        _pending_callbacks += 1
    _callback_worker_wake.set()


def _ensure_callback_worker():
    global _callback_worker
    if _callback_worker is not None and _callback_worker.is_alive():
        return
    _callback_worker_stop.clear()
    _callback_worker = threading.Thread(
        target=_callback_worker_loop, name="enter-callback", daemon=True
    )
    _callback_worker.start()


def _callback_worker_loop():
    global _pending_callbacks
    while not _callback_worker_stop.is_set():
        _callback_worker_wake.wait(timeout=0.2)
        _callback_worker_wake.clear()
        while True:
            with _callback_lock:
                if not _callback_queue:
                    break
                callback = _callback_queue.pop(0)
            try:
                callback()
            except Exception as exc:  # noqa: BLE001 - 回调出错不能影响监听
                print(f"[warn] callback failed: {exc!r}", flush=True)
            finally:
                with _callback_lock:
                    _pending_callbacks -= 1


def _drain_callbacks(timeout=1.0):
    """等待已经排队的用户回调执行完（收尾/停止监听时用）。

    计数在回调执行完之后才减，所以这里等待是可靠的：钩子已经先被停掉，
    不会再有新的回调进来，等它归零即可。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _callback_lock:
            if _pending_callbacks <= 0:
                return True
        time.sleep(0.01)
    return False


def _normalize_key(key):
    """把单字符按键统一成小写字符，其他类型原样返回。

    空格必须特殊处理：pynput 会把字符串 strip()，单独的 " " 会被它变成空字符串
    从而解析失败（ValueError）。所以空格统一交给 pynput 的 Key.space。
    """
    if isinstance(key, str) and len(key) == 1:
        if key == " ":
            return Key.space
        return key.lower()
    return key


def _normalize_button(button):
    """把 "left" / "middle" / "right" 名称转换成 pynput 的 Button。"""
    if isinstance(button, Button):
        return button
    if isinstance(button, str):
        name = button.strip().lower()
        if name in _MOUSE_BUTTONS:
            return _MOUSE_BUTTONS[name]
    raise ValueError(f"不支持的鼠标按键: {button!r}（只支持 'left' / 'middle' / 'right'）")
