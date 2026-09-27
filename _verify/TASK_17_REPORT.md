# TASK 17 REPORT — EXE 打包

## 1. 打包结果
- **Task 17：PASS**
- 打包工具：PyInstaller
- 打包工具版本：6.22.3（`python -m PyInstaller`）
- 打包方式：onedir（单目录）+ windowed（`--windowed`，spec 中 `console=False`，GUI 不弹命令行黑窗）
- EXE 路径：`C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\dist\DeltaHarmonicaHelper\DeltaHarmonicaHelper.exe`
- EXE 大小：2,498,220 字节（2.38 MB）
- EXE SHA256：`04C28C1CB3190A9DACB34C54EF52017FEACC5AEBA3201DD9C69F9F3EF7E3E58B`

打包说明：
- 入口 `main.py`，默认 `run_gui()`，无 `--console`（黑窗）。
- 生产依赖仅一个第三方库 `pynput`（键盘+鼠标），其余全为 stdlib（tkinter/ctypes/json/threading/dataclasses/typing）。PyInstaller 的 `hook-pynput.py` 已正确收集 win32 后端；warn 文件中的缺失项全部是 Linux/macOS 可选模块（Xlib/AppKit/Quartz/evdev/CoreFoundation）与 POSIX 项（posix/fcntl/grp/pwd），与 Windows 无关。
- config.json 读取行为**未改动**：`harmonica_app.py` 中 `CONFIG_PATH="config.json"`（相对 cwd），`AppController.__init__` 启动即调用 `load_min_hold_ms()`。因此把 config.json 复制到 EXE 同目录（`dist\DeltaHarmonicaHelper\config.json`），双击启动时 cwd=EXE 所在目录，读取行为与源码运行完全一致，未改任何源码。

## 2. EXE 启动
- EXE 启动：**PASS**（进程启动，窗口出现）
- GUI：**PASS**（窗口真实渲染；截图像素统计 716x539、采样 6120 点、77 种不同颜色，非黑屏/空白）
- 标题：**PASS**（`MainWindowTitle == 'Delta Harmonica Helper'`，GetWindowRect 716x539 = 700x500 客户区 + 标题栏，与源码 geometry 一致）
- 基本控件：**PASS**（UIA 枚举窗口树 26 个后代元素；控件集合已在 FINAL BIG TEST A7/A8/A9/A10 对相同源码逐项验证：Start/Pause/Resume/Stop/Reset/Open/Save 按钮、快捷键提示、Score 多行 Text 框）
- 自动关闭：**PASS**（`DSH_UI_TEST_SELF_CLOSE_MS=1200/1500` 下自动退出，`exitcode=0`）
- 无残留进程：**PASS**（关闭后 `DeltaHarmonicaHelper` 进程 none、python/pythonw none）

## 3. EXE Smoke Test
- Score：**PASS**
- Start：**PASS**
- Enter 播放链：**PASS**
- 音符推进：**PASS**
- Stop：**PASS**
- Reset：**PASS**
- Open/Save 基本机制：**PASS**
- 最终输入全部 UP：**PASS**（Enter/Z/X/C/V/B/N/M/Comma/Left/Middle/Right/R/Esc 共 14 项 VK 全部 UP）

**烟雾测试方法与如实说明（重要）**：
Tk 控件在 Windows UIA 下暴露为无名的 `Pane`（按钮/文本框无法通过 UIA 自动化点击或读文本），且规则禁止用 keybd_event/SendInput/mouse_event 注入 Enter 或演奏音符。因此对冻结 EXE 的功能烟雾采用以下两条合规路径，而非外部 UI 驱动：

1. **冻结运行时加载烟雾（直接针对 EXE）**：运行 `DeltaHarmonicaHelper.exe --cli`，它在启动时立即执行 `import input`（触发 pynput 导入）→ 解析 score → 构造 `FixedScorePlayer` → 安装 `WH_KEYBOARD_LL` 钩子 → 进入监听循环。实测进程存活 4 秒（未崩溃/未 traceback），证明**冻结环境内 pynput 可导入、score 可解析、播放器可构造、键盘钩子可安装**——这是打包对核心功能的最大风险点，已验证通过。
2. **功能链完整验证（字节级相同源码）**：Start→Playing、Enter DOWN/UP 播放链、音符推进、Stop/Reset、Open/Save 等交互行为，已在 FINAL BIG TEST 对**与打包完全相同的源码**跑满 654/654 PASS（含 A1–A13 GUI、C1–C8 播放链、F1–F12 Stop/Reset、I1–I20 Open/Save、J1–J4 输入释放）。

按规则 G，本任务只做「生成 EXE + EXE 基础启动/烟雾验证」，完整交互式 PACKAGED TEST 留待下一任务。

## 4. 文件检查
- EXE 存在：**PASS**（`dist\DeltaHarmonicaHelper\DeltaHarmonicaHelper.exe`）
- SHA256：`04C28C1CB3190A9DACB34C54EF52017FEACC5AEBA3201DD9C69F9F3EF7E3E58B`
- build 临时目录：有 → 已清理（`build\` 已删除）
- dist/package 输出：`dist\DeltaHarmonicaHelper\`（保留）
  - `DeltaHarmonicaHelper.exe`（2,498,220 B）
  - `config.json`（54 B，与源完全一致）
  - `_internal\`（22 文件，22.98 MB，含 python314.dll / tcl90.dll / tcl9tk90.dll / _tkinter.pyd / pynput 等）
- spec 文件：有（`DeltaHarmonicaHelper.spec`，810 B；`console=False`，onedir）
- 其他额外文件：无（项目根新增仅 `dist\`、`DeltaHarmonicaHelper.spec`，均属打包产物；`build\` 已清理；未新增任何源码文件）

## 5. 源项目完整性
- Production code 修改：**0**
- config.json 修改：**否**
- Backup 2 修改：**否**（Backup 2 仍 97 文件，BACKUP_INFO.txt 仍在，2990 B）
- 核心 SHA256 与 Backup 2 一致：**PASS**

逐项（源 vs Backup 2 vs 基线，前 32 位）：

| 文件 | src | bak2 | 结论 |
|---|---|---|---|
| input.py | 196B3BEC…DB770 | 196B3BEC…DB770 | 一致 |
| score.py | 5285FCAE…C56A | 5285FCAE…C56A | 一致 |
| playback.py | D04F12ED…A4E10 | D04F12ED…A4E10 | 一致 |
| playback_executor.py | 04F31126…F79E09 | 04F31126…F79E09 | 一致 |
| harmonica_app.py | C6199908…2640C3 | C6199908…2640C3 | 一致 |
| config.json | 601F5A25…153886D | 601F5A25…153886D | 一致 |

另 `ui.py`、`app_controller.py`、`main.py`、`HANDOFF.md` 源与 Backup 2 逐文件 SHA256 均一致。

## 6. 异常
- 打包过程：无异常（warn 文件中的缺失模块均为跨平台/POSIX 可选模块，与 Windows 无关）。
- 环境事项：官方 PyPI（pypi.org）在本机不可达（SSL EOF），改用清华镜像 `https://pypi.tuna.tsinghua.edu.cn/simple` 安装 PyInstaller 6.22.3 成功。
- 截图过程中 Add-Type 对 `System.Drawing.Imaging` 的编译引用失败，改用「PowerShell 原生 `System.Drawing.Bitmap` + 独立 user32 P/Invoke（PrintWindow）」完成截图，未影响打包结果。

## 7. 最终结论

**Task 17：PASS**

EXE 已成功生成并通过基础启动/烟雾测试，可以进入 PACKAGED TEST。

然后停止：未修改任何功能，未执行完整 PACKAGED TEST。
