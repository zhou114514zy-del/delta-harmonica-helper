# Task 28 Report

## 1. 安装器工具
- 工具：**PyInstaller（自建自包含安装器）** — 本机**没有 Inno Setup / NSIS / WiX**，且**当前网络全面不可达**（jrsoftware.org / GitHub / winget 源 / chocolatey 源 / 清华镜像全部连接失败），无法安装 Inno Setup。7-Zip 虽存在但**没有任何 SFX 模块**。因此改用本机已装的 PyInstaller 构建"安装器层"（安装器本身即一个 EXE，内嵌已打包好的 onedir 负载），并配套独立卸载器。
- 版本：PyInstaller **6.22.3** / Python **3.14.7**
- 构建命令：
  `powershell -NoProfile -ExecutionPolicy Bypass -File installer\build_installer.ps1`
  （内部依次：校验源 EXE 哈希 → 提取程序图标 → 暂存 payload → `pyinstaller --onefile --windowed --uac-admin --icon app.ico --name uninstall installer\uninstall_app.py` → `pyinstaller --onefile --windowed --uac-admin --icon app.ico --add-data "<payload>;payload" --name DeltaHarmonicaHelper_Setup installer\setup_app.py`）
- 构建 exit code：**0**（无 error）

## 2. 源 EXE 验证
- 源 EXE 路径：`C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\dist\DeltaHarmonicaHelper\DeltaHarmonicaHelper.exe`
- SHA256：`BCF4D68244723F1ACEAC2073D81D53ED1E89A5AEF0742B6FCCF15B3C7F706644`
- 是否与 Task 27B 一致：**PASS**（构建脚本把它作为硬校验，不一致会直接终止）

## 3. 安装包
- Setup.exe 路径：`C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\release\DeltaHarmonicaHelper_Setup.exe`
- 文件大小：**37,246,098 bytes（35.52 MB）**
- SHA256：**`11B9CFB7F04892980F2800AAD37E5CDA4CC0122E432CA61C9460678FC4880A1A`**
- 构建时间：**2026-09-25 22:25:07**
- 是否成功：**PASS**
- 图标说明：项目**没有自定义正式图标**，故按任务书要求**未临时制作复杂图标**，直接**提取并使用程序 EXE 自带的图标**（PyInstaller 默认图标）用于安装器、卸载器与快捷方式。

## 4. 安装测试
- 安装成功：**PASS**（静默 `Setup.exe /S`，exit code = 0）
- 安装目录正确：**PASS**（`C:\Program Files\Delta Harmonica Helper`，为默认目录；安装器 GUI 亦提供"浏览…"可改目录，并支持 `/D=<目录>`）
- EXE 存在：**PASS**（且安装后 EXE 的 SHA256 与源 EXE **完全一致**）
- _internal 完整：**PASS**（22 个文件；`python314.dll` / `tcl90.dll` / `tcl9tk90.dll` / `_tkinter.pyd` / `base_library.zip` 等关键依赖齐全；安装目录共 25 个文件 = 24 个负载文件 + `uninstall.exe`）

## 5. 快捷方式
- Desktop shortcut：**PASS**（`C:\Users\Public\Desktop\Delta Harmonica Helper.lnk`）
- Start Menu shortcut：**PASS**（`C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Delta Harmonica Helper.lnk`）
- Target 正确：**PASS**（两者 TargetPath 均为 `C:\Program Files\Delta Harmonica Helper\DeltaHarmonicaHelper.exe`，WorkingDirectory 为安装目录；**不指向 Python**）

## 6. 安装后启动
- GUI：**PASS**（从**安装后的 EXE** 启动，非 dist 中的原始 EXE）
- Title：**PASS**（`Delta Harmonica Helper`）
- 700x620：**PASS**（实测客户区 700x620）
- 无 ConsoleWindowClass：**PASS**（可见窗口类仅 `TkTopLevel`）
- 无 traceback：**PASS**
- 正常退出：**PASS**（关闭窗口后进程正常结束）
- requireAdministrator 保留：**PASS**（安装后 EXE 的 manifest 仍含 `requireAdministrator`，无 `asInvoker`；启动时出现正常 UAC）

## 7. 卸载
- 卸载成功：**PASS**（`uninstall.exe /S`，exit code = 0；并已在"程序正在运行"的情况下卸载，卸载器自动 `taskkill` 掉了运行中的程序）
- 安装目录清理：**PASS**（目录整体删除，无残留项）
- Desktop shortcut 删除：**PASS**
- Start Menu shortcut 删除：**PASS**
- 无残留进程：**PASS**（无 DeltaHarmonicaHelper / python / pythonw / consent.exe）
- 卸载入口：**PASS**（`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DeltaHarmonicaHelper`，DisplayName `Delta Harmonica Helper`、DisplayVersion `1.0.0`、InstallLocation、DisplayIcon、UninstallString、EstimatedSize、NoModify/NoRepair 均正确写入，可在"设置 → 应用 / 控制面板 → 程序和功能"中看到并卸载）
- 用户数据：**PASS**（卸载器会先扫描安装目录内**含文件的 Scores 谱库**，存在则先搬到 `%LOCALAPPDATA%\Delta Harmonica Helper\` 再删程序主体，**不删除用户琴谱**；本次测试无用户数据）

## 8. Backup 4
- 文件数量：**118**（基线 118）
- BACKUP_INFO：`AAB822D5B63EE6BFB7CF8878F60478581F4915E3035653D28968A79927FF3C2D`
- 是否完全未修改：**PASS**（与打包前完全一致，未向其写入任何内容）

## 9. 临时文件
- 是否有残留：**无**
- 已清理：`installer\_build`（构建缓存 137.63 MB）、项目 `build`（8.28 MB PyInstaller 缓存）、`__pycache__`、卸载器在 `%TEMP%` 的自副本与清理脚本（本轮实测 **0 个**；上一轮遗留的 1 个也已被新卸载器顺带清除）
- 最终目录划分：
  - **source**：项目根目录下的 `*.py`、`config.json`、`HANDOFF.md`、`使用说明.md/.txt`
  - **dist**：`dist\DeltaHarmonicaHelper\`（PyInstaller onedir 产物）
  - **installer**：`installer\setup_app.py`、`installer\uninstall_app.py`、`installer\build_installer.ps1`、`installer\app.ico`
  - **release**：`release\DeltaHarmonicaHelper_Setup.exe`
  - **test temp**：`_verify\task28_install_test.ps1`、`_verify\task28_cycle_result.txt`（测试资产，非临时垃圾）

### 重要发现（已在构建中处理）
- 打包后的程序会把**用户谱库**建在自己的 `_internal\Scores\` 下（这是既有业务设计，本 Task 未改）。构建时发现该目录里有**你的真实个人琴谱**（`花海.txt`、`flower dance.txt`、`雨爱.txt`、`父亲.txt`）。这属于**用户数据**，构建脚本已将它**从安装包负载中排除**（负载 28 → **24 个文件**），以免私人琴谱被分发给其他玩家；你的原始琴谱仍完好保存在 `dist\...\_internal\Scores\`，未被删除。

### 本次未修改任何生产代码
`harmonica_app.py` / `input.py` / `score.py` / `playback.py` / `playback_executor.py` / `ui.py` / `app_controller.py` / `score_library.py` / `config.json` / `main.py` 的 SHA256 与 Task 27B 时**完全一致**（未改动）；Task 28 只新增了 `installer\` 下的独立安装器脚本。

## 10. 最终结论

**TASK 28：PASS**

补充说明（非阻塞）：
1. 本机**没有 Inno Setup 且网络不可达**，所以没有使用 Inno Setup，而是用本机 PyInstaller 构建了等效的自包含安装器（安装/快捷方式/卸载入口/卸载清理均已自动化实测通过）。若之后网络可用且你希望改用 Inno Setup，可以随时重做这一层，程序本体无需任何改动。
2. 测试收尾状态是**已卸载**。要正式使用，直接双击 `release\DeltaHarmonicaHelper_Setup.exe` 即可（会弹正常 UAC → 点"是" → 装完桌面出现快捷方式）。
3. 安装器的 `uninstall.exe` 需要管理员权限（因为要删 Program Files 与 HKLM），这也符合标准 Windows 安装器做法。

已停止：未执行 Task 29，未做自动更新 / License / 官网 / 付款 / 数字签名等其他功能。
