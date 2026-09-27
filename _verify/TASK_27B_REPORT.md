# 【Task 27B】最终 EXE 重新打包 + 默认管理员权限

## 1. 打包结果
- **PASS**
- PyInstaller 版本：**6.22.3**
- Python 版本：**3.14.7**
- onedir：**PASS**
- windowed：**PASS**（spec `console=False`，无控制台窗口）
- 管理员权限：**PASS**（spec `uac_admin=True`，manifest `requireAdministrator`）
- 打包命令：`python -m PyInstaller --noconfirm --clean --windowed --uac-admin --name DeltaHarmonicaHelper --distpath dist --workpath build --specpath . main.py`（exit=0，无 error）

## 2. 最终 EXE
- 完整路径：`C:\Users\16966\Desktop\ds_w\delta-harmonica-helper\dist\DeltaHarmonicaHelper\DeltaHarmonicaHelper.exe`
- 文件大小：**2,541,870 bytes（2.42 MB）**
- SHA256：**`BCF4D68244723F1ACEAC2073D81D53ED1E89A5AEF0742B6FCCF15B3C7F706644`**
- dist 文件数量：**24**（`_internal` 22 个）
- dist 总大小：**25.41 MB**
- 构建时间：**2026-09-24 21:09:29**
- `config.json` 已放在 EXE 同级目录（保持原读取方式）
- 旧 EXE（`B439F57B…`）已被清理后重建，**未复用**

## 3. Task 27A 修复进入最终 EXE
- **PASS**
- 使用什么方法验证（不依赖"能启动就算通过"）：
  1. **解包 EXE 内嵌 PYZ**（`pyi-archive` 的 CArchive → `PYZ.pyz` → ZlibArchive），取出 `harmonica_app` 的**实际字节码对象**；
  2. 在其中定位函数 `_complete_note` 并**反汇编**，统计调用：
     - `release_all` = **2** 次（第一分支 + "Enter 已松开"分支）
     - `apply` = **1** 次（仅 `enter_is_down` 的边界分支）
     - 指令总数 = **81**
     - 反汇编里 **不存在** 旧的 `apply(self.controller.current_state())` 分支
  3. **对照实验**：用当前工作目录源码现场 `compile()` 出 `_complete_note`，统计结果为 **完全相同**（release_all=2 / apply=1 / 81 条指令）。
  → 结论：打包进 EXE 的 `_complete_note` 与当前 Task 27A 源码**逐指令一致**，旧 bug 代码已不在 EXE 内。

## 4. 管理员权限
- **requireAdministrator manifest：PASS**
  - 直接从 EXE 的 **RT_MANIFEST 资源**读出（`FindResource/SizeofResource/LoadResource`，1304 字节），内容为：
    `<requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>`
  - 同时确认 EXE 字节中 **无** `asInvoker`
- **UAC 请求：PASS**
  - 实测启动时出现 **`consent.exe`（Windows 正常 UAC 授权框）** 并阻塞等待授权；授权后程序才启动
  - 另有 OS 层确定性证据：非提权上下文直接 `CreateProcessW` 该 EXE 返回 **错误码 740 = ERROR_ELEVATION_REQUIRED**
  - 未使用任何绕过/隐藏/静默提权手段，也未在 Python 代码里自行重启提权
- **管理员启动 GUI：PASS**
  - 提权后进程正常启动，窗口标题 `Delta Harmonica Helper`，可见窗口类 `TkTopLevel`，客户区 **700x620**

## 5. GUI 启动（管理员身份下实测）
- GUI：**PASS**
- title：**PASS**（`Delta Harmonica Helper`）
- 默认窗口尺寸：**PASS**（客户区 **700x620**）
- 无 ConsoleWindowClass：**PASS**（可见窗口类仅 `TkTopLevel`）
- 无 traceback：**PASS**（启动过程无异常输出）
- 正常退出：**PASS**（窗口关闭后进程正常消失；见第 9 节关于数值退出码的说明）

## 6. 清理
- Python 残留：**PASS**（无 python / pythonw）
- EXE 残留：**PASS**（无 DeltaHarmonicaHelper.exe 残留；无 consent.exe 残留）
- crash dump：**PASS**（无 .dmp / hs_err）
- traceback：**PASS**（无）
- 临时文件：**PASS**（无 `__pycache__`、无临时 `_fail_*.txt`；Scores 未被改动，仍 0 文件）

## 7. Backup 4
- 是否修改：**NO**
- 文件数量：**118**（与基线一致）
- BACKUP_INFO：`AAB822D5B63EE6BFB7CF8878F60478581F4915E3035653D28968A79927FF3C2D`
- 是否与打包前一致：**PASS**（哈希与打包前完全相同；B4 内无 dist，未向其写入任何文件）

## 8. 源码生产逻辑
- 是否修改 Task 27A 之外的生产逻辑：**NO**
- 关键源码 SHA256（前 32 位，与打包前完全一致）：
  `harmonica_app.py 91F650737CB3D9DE110D193BC91C57C7`、`main.py 4670ACF48726FE9864B5CFF97484C39A`、
  `ui.py 91954561B31C732F6D16EDD2784ECF55`、`app_controller.py 16B151755BDE542FB5B04315D57DF3E7`、
  `score_library.py 95092B227E20EB669342678790EDA236`、`input.py 196B3BEC60BB4FD0DBF597ED607DB770`、
  `score.py 5285FCAE1688A66959CFB2D32744C56A`、`playback.py D04F12ED43C6649F146A2059758A4E10`、
  `playback_executor.py 04F31126851B5DA550A87D33C3F79E09`、`config.json 601F5A25EFA92E1CBC8671B1A153886D`
- 本次唯一新增的构建相关改动：`DeltaHarmonicaHelper.spec` 中的 `uac_admin=True`（未改任何 .py）

## 9. 其他发现（只记录，未修）
1. **提权后进程不继承启动方环境变量**：因此我用于自动关闭的测试变量 `DSH_UI_TEST_SELF_CLOSE_MS` 无法传进管理员进程，导致管理员实例不会自动关闭（只能人工关窗口）。这是 Windows UAC 的固有行为，不是程序 bug。
2. **数值退出码未能在管理员下采集**：非提权上下文向提权窗口 `PostMessage(WM_CLOSE)` 会被 UIPI 拦截；而自动关闭变量又传不进去。已改为通过"关闭窗口后进程正常消失"确认正常退出路径可用（该路径代码与 Task 26 已实测 exit code 0 的版本相同，本次只多了 manifest）。
3. **桌面快捷方式无需改动**：`C:\Users\16966\Desktop\Delta Harmonica Helper.lnk` 指向的路径没变，因此它现在**直接启动的就是这次的修复版 + 管理员版**（双击会弹正常 UAC）。
4. 项目根目录里还留着上一轮我建的开发版启动器 `run_dev.lnk`（指向 `pythonw main.py`，非管理员）。如不需要可删除；本 Task 未删。

---

**完成，已停止。** 未执行 Task 28，未再修改任何功能。
