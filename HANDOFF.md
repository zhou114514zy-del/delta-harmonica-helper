# 三角洲口琴自动弹奏辅助工具 — 项目交接文档

> 给接手者（Codex）的完整背景。读这一份就够开工。
> 生成时间：Task 11 进行中。项目路径：`C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\`

---

## 1. 这是什么项目

一个 **Windows 个人使用的小工具**，名字叫「三角洲口琴自动弹奏辅助工具」。

**要解决的问题**：游戏《三角洲行动》里有一件"口琴"道具，玩家需要按固定的键位组合才能吹出音符。手动按很累也不准，所以这个工具要：

1. **全局监听 Enter 键**，并把 Enter **拦截掉**（不让它传给游戏）；
2. 玩家按 Enter（按下 = 开始吹，松开 = 停止）；
3. 工具根据**预先写好的琴谱**，自动模拟出对应的**键盘音符键 + 鼠标调音键**组合；
4. 于是玩家只要按 Enter 的节奏，就能自动吹出曲子。

**游戏内的真实按键映射**（已确认）：

| 音符 | 键盘键 | | 调音 | 鼠标键 |
|---|---|---|---|---|
| 1 | `Z` | | 降调 | 左键 |
| 2 | `X` | | 半音 | 中键 |
| 3 | `C` | | 升调 | 右键 |
| 4 | `V` | | 普通 | 不需要鼠标键 |
| 5 | `B` | | | |
| 6 | `N` | | | |
| 7 | `M` | | | |
| 1' | `,`（逗号） | | | |

**关键机制**：调音键是**持续状态**，不是每个音符重新按一次。例如琴谱 `1 2 [↑ 3 4 5] 6` 里，3→4→5 这个升调区间内，**鼠标右键全程保持按住**，不能出现 `right UP → right DOWN` 的抖动。

---

## 2. 最终目标架构

```
琴谱文本 (score.py 解析)
    │
    ▼
PlaybackController (playback.py)      纯逻辑：当前是第几个音符？该音符要按什么？调音状态是什么？
    │  PlaybackState(keys={"c"}, mouse_buttons={"right"})
    ▼
PlaybackExecutor (playback_executor.py)  差分：只处理新旧状态的差异，调音键相同的部分保持不动
    │  press_key / release_key / press_mouse / release_mouse
    ▼
input.py                              真实输入：pynput 模拟键鼠 + WH_KEYBOARD_LL 全局钩子拦 Enter
    │
    ▼
Windows / 游戏
```

**触发链**：`Enter DOWN → 播放当前音符` → `Enter UP → 停止当前音符 + 前进到下一个`

---

## 3. 已完成的 Task（1–10，全部通过验收）

| Task | 内容 | 交付 | 测试结果 |
|---|---|---|---|
| 1 | 最小项目骨架 | `main.py` `score.py` `config.json` | 通过 |
| 2 | 键盘模拟 `press_key` / `release_key`（pynput） | `input.py` | 通过 |
| 3 | 鼠标模拟 `press_mouse` / `release_mouse` | `input.py` | 通过 |
| 4 | 全局 Enter 按下/松开检测（含长按去重） | `input.py` | 通过 |
| 5 | 改用自装 `WH_KEYBOARD_LL` 低级钩子，**只拦截 Enter，其他键放行** | `input.py` | 通过（40 项，含记事本实测） |
| 6 | Enter → 固定 Z；退出时 `release_all()` 防卡键 | `input.py` `main.py` | 通过 |
| 7 | 真实键鼠组合：Z + 左/中/右键，持续按住 | `input.py` `main.py` | 通过（系统级） |
| 8 | 文本琴谱解析器（音符 + `[↑ ↓ ~]` 调音区间 + `#` 注释 + 错误定位） | `score.py` | 通过（40 项） |
| 9 | 纯逻辑 `PlaybackController`（不碰真实输入） | `playback.py` | 通过（55 项） |
| 10 | `PlaybackExecutor` 状态差分 → 真实输入 | `playback_executor.py` | 通过（26 项纯逻辑 + 36 项系统级） |
| **11** | **Enter → 演奏（当前进行中）** | `harmonica_app.py` `main.py` | **未完成，见第 6 节** |

### 各模块当前接口

**`input.py`** — 输入层
```python
press_key(key) / release_key(key)              # 键盘模拟（支持 "z"、" " 空格、Key.enter）
press_mouse(btn) / release_mouse(btn)          # 鼠标模拟，btn ∈ {"left","middle","right"}
move_mouse(x, y)
release_all()                                  # 释放所有"由本程序按下"的键鼠（不会碰用户自己按住的）
held_keys() / held_mouse_buttons() / mouse_button_name(btn)
set_enter_callbacks(on_down, on_up)            # 注册 Enter 回调
set_escape_callback(on_escape)                 # 注册 Esc 回调
start_enter_listener() / stop_enter_listener() / is_listening() / enter_is_down()
_hook_callback(n_code, w_param, l_param)       # 低级钩子回调本体（只拦 VK_RETURN=0x0D）
_drain_callbacks(timeout)                      # 等待已排队的用户回调执行完
seen_vk_codes()                                # 诊断用原始 vkCode 记录
```
- **重要**：钩子回调在工作线程上运行，用户回调被丢到 **`enter-callback` 工作线程异步执行**（`_emit` → `_callback_queue`）。
- **重要**：`release_all()` 只释放本程序自己按下过的键，绝不碰用户按住的键。

**`score.py`** — 琴谱解析
```python
Note(note, key, modifier)                      # NamedTuple，modifier ∈ {"normal","sharp","flat","half"}
parse_score(text) -> list[dict]                # [{"note","key","modifier"}, ...]
parse_score_notes(text) -> list[Note]
ScoreParseError                                # .line / .column，str() 形如 "line 1, column 5: ..."
NOTE_KEYS = {"1":"z","2":"x","3":"c","4":"v","5":"b","6":"n","7":"m","1'":","}
MODIFIER_NORMAL/SHARP/FLAT/HALF
```
语法：空格/Tab/换行分隔；`[↑ 1 2 3]` 调音区间，区间结束自动回 normal；`#` 到行尾是注释。

**`playback.py`** — 纯逻辑状态机（**不碰任何真实输入**）
```python
PlaybackState(keys: frozenset, mouse_buttons: frozenset)   # frozen dataclass，有 .as_dict()
PlaybackController(notes)
    .current_note() .current_state() .start_current()
    .stop_current_and_advance() .reset() .is_finished() .has_current() .note_count()
    .index  .is_playing  .state  .notes
MODIFIER_MOUSE_BUTTONS = {normal: None, sharp: "right", flat: "left", half: "middle"}
state_for_note(note) -> PlaybackState
```
- **易踩坑**：`current_state()` 只在 `is_playing=True` 时才有内容；`stop_current_and_advance()` 会把状态清空。**推进之后想拿下一个音符的状态，必须先 `start_current()`。**

**`playback_executor.py`** — 状态差分
```python
PlaybackExecutor()
    .apply(new_state)      # 先释放"旧有新没有"，再按下"新有旧没有"；新旧都有的保持不动
    .release_all()         # 逐个 release_key/release_mouse（刻意不用 input.release_all）
    .current_state() .held_keys() .held_mouse_buttons() .state
```
- **不会**出现公共键（如 right）被重复 press/release —— 这是 Task 10 的核心验收点。

**`harmonica_app.py`** — Task 11 新增的接线层（**有争议，见第 7 节**）
```python
FixedScorePlayer(notes, io_module=input, release_all_on_enter_up=False)
    .enter_down()      # 已按下→忽略；无音符→什么都不做；否则 start_current()+apply()
    .enter_up()        # 无对应按下→忽略；否则 stop_current_and_advance()
                       #   然后：若 is_finished() 或 release_all_on_enter_up → executor.release_all()
                       #   否则 → controller.start_current() + executor.apply(...)  (只换音符键，调音键保持)
    .shutdown()        # executor.release_all()
    .index .current_note() .current_state() .current_state_text() .is_finished() .note_count()
```

**`main.py`** — Task 11 程序入口
- 固定测试琴谱 `SCORE_TEXT = "1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]"`（9 个音符）
- 建 player → 注册 `on_enter_down` / `on_enter_up` / `on_escape` → `start_enter_listener()` → 主线程等待 → 退出时 `player.shutdown()`
- Esc：释放全部 + `io.stop_enter_listener()`

---

## 4. Task 11 的目标语义

```
Enter DOWN → 播放当前音符（键盘键 + 调音鼠标键一起按下并保持）
Enter 一直按住 → 当前音符一直保持（自动重复的 DOWN 必须被忽略，不能重复按）
Enter UP  → 停止当前音符，index 前进到下一个
Esc       → 释放所有本程序持有的输入，停止监听，退出
```

**必须验证的行为**（任务书列的 A–J）：

| 测试 | 内容 |
|---|---|
| A | 单音 `1`：DOWN → Z DOWN；UP → Z UP，index=1 |
| B | 连续 `1 2 3`：依次 Z / X / C |
| C | 长按 Enter：当前音符一直保持；松开后释放（不要求 min_hold_ms） |
| D | 调音 `[↑ 3]`：DOWN → C+right；UP → 全释放 |
| E | 调音连续 `[↑ 3 4 5]`：right **只按一次、切换音符时不抖动** |
| F | 混合谱 `1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]`：逐音符验证 |
| G | 播放结束后再按 Enter：**不产生任何输入** |
| H | 当前音符 DOWN 时 Esc：必须释放所有持有的输入 |
| I | 重复 Enter DOWN：不能重复 press 当前音符 |
| J | 测试结束无 python 残留、12 个键全 UP |

**任务书内部冲突（需注意）**：第三节说 Enter UP 时"调用 `executor.release_all()` 或等价的释放逻辑"，但**测试 E 要求调音键在音符切换时不得有 UP/DOWN 抖动**。当前实现选了后者（调音键跨音符保持），并留了 `release_all_on_enter_up` 开关可切回方案 A。**这个取舍需要确认。**

---

## 5. 测试纪律（非常重要，务必遵守）

前两次测试**把用户的键盘/鼠标键卡在了按下状态**，用户已明确抱怨。请严格按以下规则做测试：

### 5.1 绝对禁止

- ❌ **不要复用 `_verify\task11_system_test.ps1`** —— 它就是卡键元凶（PowerShell 长脚本 + 长驻 Python 运行器 + stdin/stdout 管道；脚本被中断时运行器还活着并持有按键；管道填满还会阻塞）。
- ❌ 不要用 `keybd_event` / `SendInput` / `mouse_event` 发送 **Enter 或任何音符键** 作为正式功能测试输入。
- ❌ 不要向未知焦点发送普通字符（A/Z/Space/Tab）。历史上曾因此把 `az` 打进用户的聊天输入框。
- ❌ 不要用 PowerShell 正则批量改脚本文件（会写成 GBK 编码，`powershell.exe` 5.1 按 GBK 读 UTF-8 会解析崩溃）。用文件编辑工具。
- ❌ 不要用长驻进程 + 管道（会死锁、会被中断卡键）。
- ❌ 测试结束不许留下任何按下的键、任何 python/pythonw 残留进程、任何测试窗口。

### 5.2 推荐做法

- ✅ **纯逻辑测试优先**：给 `FixedScorePlayer` 注入假的输入模块（记录 press/release 调用序列），完全不碰系统。`_verify\task11_logic.py` 就是这种（66/66 通过）。
- ✅ **真实系统级测试用单个自包含 Python 进程**，`try/finally` 保证 `release_all()`，`from __future__` 不要用管道。参考 `_verify\task11_system_selftest.py`。
- ✅ Enter 事件可以通过 `input._hook_callback(0, WM_KEYDOWN/WM_KEYUP, 指向 KBDLLHOOKSTRUCT 的整数地址)` 走**真实的钩子回调路径**投递，这样不违反"不用 keybd_event 发 Enter"。
- ✅ 真实按键状态用**只读** `GetAsyncKeyState` 校验。
- ✅ 真实输入只允许经过 `PlaybackExecutor → input.py`。
- ✅ 测试用**专用测试窗口**（`_verify\test_window.ps1`，WinForms，固定位置置顶，只记录事件不做任何操作），并确认它是前台窗口。
- ✅ 每次真实测试结束后，独立确认 12 个键的状态：
  `Enter/Z/X/C/V/B/N/M/Comma(0xBC)/Left/Middle/Right` 全部为 `False`。

---

## 6. 当前问题（Task 11 未完成）

### 6.1 纯逻辑测试：**66/66 通过** ✅
`python _verify\task11_logic.py` → exit 0。覆盖 A/B/C/D/E/F/G/H/I 全部逻辑，包括"调音键零抖动"。

### 6.2 真实系统级自测：**31 PASS / 23 FAIL** ❌
`python _verify\task11_system_selftest.py` → exit 1。

**失败模式（高度规律）**：

1. **所有"Enter UP 之后"的检查成批失败**：
   - `A3 index == 1` 实得 `index=0`
   - `B2 after UP, X ready` 期望 `x|` 实得 `|`
   - `B4 after UP, C ready` 期望 `c|` 实得 `x|`
   - `B6 finished, all released` 期望 `|` 实得 `c|`
   - `B7 index == 3` 实得 `index=2`
   - `E2/E4/E6` 同类
   - `H4 index == 1` 实得 `index=0`
2. **F 组（逐步累加按键序列）整体"慢一拍"**：F5 期望 `c|right` 实得 `v|right`（那是 F7 的值）、F7 实得 `c+n|`、F10 实得 `x|left`……

**注意规律**：F 组里凡是 `enter_down` 的检查都 PASS，凡是要经过 `enter_up` 才该出现的状态都 FAIL。这强烈指向 **`enter_up` 完成的时机** 或 **测试读取时机**。

### 6.3 我（前一个 agent）的判断 —— **不确定，需要独立验证**

我怀疑是**测试驱动的时序问题**，不是生产逻辑 bug，理由：

1. `input._hook_callback` 里 `_emit()` 把用户回调丢到**工作线程异步执行**；我在 `enter_up()` 之后调了 `_drain_callbacks()`，但**需要确认它是否真的等到了回调执行完**，以及 `enter_up` 内部连续的 `stop_current_and_advance()` + `start_current()` + `apply()` 是否在回调线程上原子完成。
2. `A3 index == 1` 实得 `index=0`，而 `_drain_callbacks` 应该保证回调跑完了……如果确实等到了，那**就可能是真 bug**（比如 `player.enter_up()` 抛异常被 `_emit` 吞掉，日志里有 `[warn] callback failed`）。
3. F 组的"慢一拍"**也可能是我测试脚本构造按键序列时数错了**（我按 `n` 生成 `d/u` 交错序列，`n==18` 时多补了一个 `u`，那段逻辑很绕，很可能写错）。

**我没有改生产代码**，因为无法区分"实现 bug"和"测试 bug"，不该瞎改。

### 6.4 建议的排查手段

不要用 `GetAsyncKeyState` 异步轮询（有竞态）。**改成在 `input.py` 层面记录调用序列**，例如临时给 `press_key/release_key/press_mouse/release_mouse` 包一层记录器，然后：

1. 跑一次 `enter_down()` → 打印记录到的调用序列（期望 `['press_key(z)']`）和 `player.index`；
2. 跑一次 `enter_up()` → 打印序列（期望 `['release_key(z)', 'press_key(x)']`）和 `player.index`；
3. 这样能**直接看出** `enter_up` 到底发没发对、`index` 到底推没推进，不存在时序竞态。

同时检查 stderr / stdout 里有没有 `[warn] callback failed:` —— 那说明回调抛异常被吞了。

---

## 7. 需要接管者注意/决策的点

1. **`harmonica_app.py` 是前一个 agent 自作主张新增的**。任务书只说"可以修改 main.py"，抽这一层的目的是让**生产代码和测试共用同一份接线**（避免测试里复制一份逻辑）。请你决定：保留，还是把接线放回 `main.py`（测试改为导入 `main`）。
2. **`input.py` 被改过**（超出该 Task 授权）：`_normalize_key` 把空格映射为 `Key.space`（pynput 对空格会抛 `ValueError`）；`press_key/release_key` 加了异常防护。起因是 Task 10 发现的真实缺陷。
3. **调音键语义的取舍**（见第 4 节末尾）：调音键跨音符保持 vs 每次 Enter UP 全释放。当前是前者（为满足测试 E），有开关可切。
4. **验收要求**：不要重构整个项目；`score.py` / `playback.py` / `config.json` 原则上不要改；发现 bug 先定位原因再做**最小修复**，然后回归：
   - `python _verify\task8_logic.py`（期望 40/40）
   - `python _verify\task9_logic.py`（期望 55/55）
   - `python _verify\task10_logic.py`（期望 26/26）
   - `python _verify\task11_logic.py`（期望 66/66）
   - `python -m py_compile main.py input.py score.py playback.py playback_executor.py`（期望 exit 0，stderr 空）
5. **不要继续实现 Task 12 及以后**：UI、JSON 琴谱、BPM/时值/节奏、循环播放、`min_hold_ms`、游戏窗口检测、失焦处理、打包 EXE、反作弊相关 —— 全部不在 Task 11 范围内。

---

## 8. 环境要点（踩过的坑）

- **Python 3.14.7**；`pynput 1.8.2` 已装在用户 site-packages。
- **`powershell.exe` 是 5.1**，且**按 GBK 读取 .ps1 文件**：UTF-8 无 BOM 的脚本里如果有中文或 `↑↓~` 等字符，会被解析成乱码导致语法错误（甚至把字符串引号吞掉）。**测试脚本一律写纯 ASCII**，需要 `↑` 时用 `[string][char]0x2191` 运行时构造。
- **Windows 控制台是 GBK**，Python `print` 中文会显示乱码（不影响逻辑，但看起来像坏了）。脚本内提示信息建议用 ASCII。
- **Win11 记事本是 Store 版**：`Start-Process notepad` 只启一个立刻退出的启动器；要 `Start-Process "shell:AppsFolder\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"` 才有真窗口。
- **前台锁定**：后台进程用 `SetForegroundWindow` 抢焦点会被 Win11 拒绝。给记事本设焦点要用 UI Automation：找 `ControlType.Document` 元素并 `element.SetFocus()`。
- **Store 记事本**窗口树：`NotepadTextBox` / `RichEditD2PPDT`（编辑区）。
- **`GetAsyncKeyState` 只读校验**的键码：`Enter=0x0D, Z=0x5A, X=0x58, C=0x43, V=0x56, B=0x42, N=0x4E, M=0x4D, Comma=0xBC, Left=0x01, Right=0x02, Middle=0x04`。
- 合成按键（`keybd_event`）**不会触发 Windows 自动重复**，所以"长按去重"要用纯逻辑测试喂重复事件来验证。

---

## 9. 当前系统状态（截至本文档生成）

- 卡键检查：`Enter/Z/X/C/V/B/N/M/Comma/Left/Middle/Right` **全部 False**，无卡键。
- 残留进程：**无 python / pythonw，无测试窗口**。
- `py_compile main.py input.py score.py playback.py playback_executor.py`：**exit 0，stderr 空**。
- Task 8/9/10 回归：**40/40、55/55、26/26 全通过**。
- Task 11：**纯逻辑 66/66 通过；真实系统级 31/54 未通过**（原因待判定，见第 6 节）。
