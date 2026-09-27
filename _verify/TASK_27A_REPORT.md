# 【Task 27A】Enter 松开后琴键未释放 —— 修复报告

## 1. Bug 根因

**断点在 `harmonica_app.py` 的 `FixedScorePlayer._complete_note()` 的"Enter 已松开"分支。**

修复前该分支是：

```python
self.controller.start_current()                    # 把「下一个音符」设为当前状态
...
else:                                              # Enter 已经松开
    self.executor.apply(self.controller.current_state())   # ← 元凶
```

`PlaybackExecutor.apply()` 只做差分：释放"旧有新没有"、按下"新有旧没有"。而 `start_current()` 刚刚把**下一个音符**设为当前状态，所以这一句实际执行的是：

- `release_key(旧音符键)` —— 当前音符键确实松开了；
- `press_key(下一个音符键)` —— **并在松手后一直按住下一个音符的键**。

又因为"不是最后一个音符"时走的是 `apply` 而不是 `release_all`，这个新按下的键**不会被任何后续逻辑释放**，只能等下一次 Enter（或 R/Stop/退出）才会动它。

于是真实游戏里表现为：松开 Enter → 输出停不下来、琴键一直处于按下、必须再按一次 Enter 才松。**与你描述的现象完全一致。**

**为什么自动化测试没抓到**：Task 11/12 的旧断言**恰好把这个错误行为当成了期望值**，例如

- `"Enter UP -> Z UP"` 之后却断言 `player.current_state_text() == "keys=[x] mouse=[-]"`（下一个音符已按下）；
- 甚至有一条断言直接叫 `"enter_up 的调用序列是先 release 旧键、再 press 新音符键"`。

所以测试全绿，真实链路却是错的。

## 2. 修改文件

**生产代码（1 个文件，仅 1 处核心改动）**

- `harmonica_app.py` → `FixedScorePlayer._complete_note()`：
  把"Enter 已松开"分支的 `self.executor.apply(self.controller.current_state())`
  改为 **`self.executor.release_all()`**，并补注释说明"绝不能在 Enter 松开时按下下一个音符"。
  行为变化：**Enter 松开 → 本次音符产生的全部真实输出（键盘键 + 鼠标调音键）立即释放；下一个音符的键只在下一次真正的 Enter DOWN 时才按下。**

**测试文件（把旧的错误期望改为正确语义，不降低强度）**

- `_verify\task27a_enter_release.py`（**新增**，29 项：A–H 覆盖任务书全部要求）
- `_verify\task11_logic.py`（10 条旧期望 → 正确语义，并新增"下一次 DOWN 才按下下一个音符"的正向验证）
- `_verify\task11_system_selftest.py`（16 条旧期望 → 正确语义）
- `_verify\task12_logic.py`（4 条：A4/E1/E3/E6/F6 → 正确语义）
- `_verify\task12_system_v2.py`（A2/G3 两条旧期望 → 正确语义）
- `_verify\task13_logic.py`（F3 → 正确语义）

**未修改**：`input.py` / `score.py` / `playback.py` / `playback_executor.py` / `config.json`（SHA256 全部未变），以及 UI / 谱库 / 文件读写 / 谱面格式 / 键位映射 / 打包配置。

## 3. 自动化测试

**Task 27A 新测试（`task27a_enter_release.py`）**

- 测试总数：**29**
- PASS：**29**
- FAIL：**0**
- TIMEOUT：**0**

**非真实输入全量回归（17 个文件）**

| 测试 | 结果 | 测试 | 结果 |
|---|---|---|---|
| task8_logic | 40/40 | task16_files | 51/51 |
| task9_logic | 55/55 | task18_library | 31/31 |
| task10_logic | 26/26 | task19_save | 64/64 |
| task11_logic | **70/70** | task20_library_management | 79/79 |
| task12_logic | **56/56** | task21_library_integration | 102/102 |
| task13_logic | **60/60** | task22_ui_chinese | 81/81 |
| task14_gui | 37/37 | task23_format_help | 36/36 |
| task15_bridge | 45/45 | task24_ui_layout | 33/33 |

- 合计：**17 个测试，895 项，PASS 895，FAIL 0，TIMEOUT 0**

**3 个"真实物理按键"system 测试（task11_system_selftest / task12_system_v2 / task13_system）——当前环境无法验证，未伪造 PASS**

原因（实测确认）：当前**前台窗口是 `三角洲行动`（窗口类 `UnrealWindow`）**。这些测试用 `GetAsyncKeyState` 校验真实注入的按键；实测在游戏前台时 `pynput` 注入**不报错但 `GetAsyncKeyState` 不反映**（游戏以 raw input 独占），因此断言必然读不到按下状态：

```
pynput press ok: True (无异常)
VK_Z down while held: False      ← 注入成功但异步键状态不反映
foreground: '三角洲行动'  UnrealWindow
```

另外**反复运行这三个测试等于持续向正在运行的游戏注入 z/x/c/左右键**，为避免干扰你的游戏与账号安全，我在完成期望值修正（语法已 `py_compile` 通过）后**主动停止继续运行它们**。它们所验证的**逻辑**已由纯逻辑测试（task11_logic 70/70、task12_logic 56/56、task13_logic 60/60、task27a 29/29，全部使用记录器替身、零真实输入）完整覆盖。

## 4. 关键验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| Enter Down → output Down | **PASS** | A1/B1 `keys=[z]`、B1 `keys=[z] mouse=[right]` |
| Enter Up → output Up | **PASS** | A3/B3/D1/D2 `keys=[-] mouse=[-]` |
| keyboard release | **PASS** | A4 `io.held_keys()==set()` |
| mouse release | **PASS** | B4 `io.held_mouse_buttons()==set()` |
| 20 次 Down/Up | **PASS** | C1 20/20 每次 DOWN→UP；C3 事件序列无 DOWN→DOWN |
| 50 次快速 Down/Up | **PASS** | E1 50/50 全部释放干净（E2 确认每轮确有按下） |
| timer / generation 场景 | **PASS** | F1 到点后全释放、F2 timer 清空、F3 旧 timer 失效不影响、F4 generation 推进 |
| 真实 `input.py` 钩子路径 | **PASS** | H1 吞键 1/1、H2 DOWN、H3 UP 全释放、H5 钩子路径连续 20 次干净 |
| 真实 config `min_hold_ms=50` 长按松开 | **PASS** | G1 释放耗时 **0.1ms**（同步、无延迟）、G2 无挂起 timer |

## 5. 开发版启动

- **PASS**
- 实际启动入口：**`python main.py`**（项目当前 GUI 入口，`run_gui()`）
- 实测：exit code **0**、无 traceback、无 console error、窗口正常创建、可正常退出
- 启动命令（仅测试用自动关闭）：`DSH_UI_TEST_SELF_CLOSE_MS=1800 python main.py`

## 6. 是否修改 Backup 4

**NO**（`delta-harmonica-helper_BACKUP_4_FINAL_STABLE` 仍为 **118** 文件，`BACKUP_INFO.txt` SHA256 仍为 `AAB822D5B63EE6BFB7CF8878F6047858`，未做任何写入）

## 7. 是否重新打包 EXE

**NO**。当前 EXE SHA256 仍为 `B439F57BA9402AC29520766324AD3861D62EB042836CF41F490EE5EF5B73EC04`（未改动、未重新打包）。**注意：当前 dist 里的 EXE 仍然是修复前的版本，需要重新打包后才会包含本次修复。**

## 8. 是否发现其他问题（只记录，本 Task 未修）

1. **"调音键跨音符保持（无抖动）"的旧设计被本次修复取代**：按你的要求，Enter 松开时**鼠标调音键也会释放**，因此 `[↑ 3 4 5]` 这类区间内每个音符都会重新按/放一次调音键（不再是全程只按一次）。相关旧断言已按新语义更新。如果你更希望"区间内保持调音键、只释放音符键"，请告知，那是另一种语义（本 Task 按你的要求选了"全部释放"）。
2. **游戏在前台时 `GetAsyncKeyState` 不反映注入的按键**：这是环境的固有行为，不是程序 bug；但它意味着今后所有依赖 `GetAsyncKeyState` 的"真实按键"自动测试都必须**在游戏不在前台时**运行。建议后续把这类测试改为显式要求"非游戏前台"，或改用记录器替身。
3. **`min_hold_ms`（当前 50ms）会让"极短点按"的释放在 0.1ms～50ms 内被延迟**（长按超过 50ms 则完全同步释放，实测 0.1ms）。它不会造成"卡键"（到点一定会释放），但严格来说不属于"按下松开即刻释放"。如需绝对即时，可把 `config.json` 的 `min_hold_ms` 设为 0（本 Task 未擅自改动配置）。
4. **`release_all_on_enter_up` 参数现已冗余**：修复后无论该参数如何，Enter 松开一律释放全部输出；该参数目前只在"延迟完成且 Enter 已被再次按住"的边界分支上还有区别。未做重构（属"顺便修"范畴）。

---

**结论**：根因已定位并修复（Enter 松开不再按下下一个音符，而是释放本次音符的全部输出）；新测试 29/29 通过；非真实输入全量回归 895/895 通过、FAIL 0、TIMEOUT 0；开发版 GUI 正常启动；未修改 Backup 4；未重新打包 EXE。3 个依赖真实物理按键的旧 system 测试在当前"游戏前台"环境下无法验证，已如实说明、未伪造 PASS。已停止，未继续 Task 27B。
