# TASK 23 REPORT — 谱面格式说明

## 1. 修改
- 修改文件：`ui.py`（在琴谱编辑框**右侧**新增只读「谱面格式说明」文本区 + 滚动条；窗口尺寸、既有控件顺序与位置均未改变）
- 新增测试文件：`_verify\task23_format_help.py`
- Backup 3 是否修改：**否**（见第 7 节「Backup 3 事件」的如实说明；最终 112 文件、BACKUP_INFO 哈希 `2C0593B3AF2A2889D27C353FC205894C` 与创建时一致，且无任何文件在备份时间后被改动）
- Backup 2 是否修改：**否**（97 文件，BACKUP_INFO 哈希不变）
- 冻结核心 6 文件是否修改：**否**（0 修改，SHA256 与基线一致；`score.py` 未改动）

## 2. 说明 UI
- 标题：**PASS**（「谱面格式说明」）
- 普通音符：**PASS**
- 自由换行：**PASS**（且注明不影响播放顺序）
- 调音组：**PASS**（`[↑ 3 4 5]` / `[↓ 2]` / `[~ 6 7 1']` / `[normal 1 2]`）
- 调音组跨行说明：**PASS**（明确写「调音组不能跨行」，并给出正确/错误示例，注明跨行会被拒绝）
- 混合示例：**PASS**（`1 2 [↑ 3 4 5] 6 [~ 7 1'] [↓ 2]`）
- 注释：**PASS**（`#` 开头到行尾为注释）
- 键位说明：**PASS**

## 3. 映射
1 → Z：**PASS**｜2 → X：**PASS**｜3 → C：**PASS**｜4 → V：**PASS**｜5 → B：**PASS**｜6 → N：**PASS**｜7 → M：**PASS**｜1' → ,：**PASS**｜↑ → 右键：**PASS**｜↓ → 左键：**PASS**｜~ → 中键：**PASS**
（未改变任何映射）

## 4. 功能保持
Open：**PASS**｜Save：**PASS**｜Save As：**PASS**｜New Score：**PASS**｜Rename：**PASS**｜Delete：**PASS**｜Playing：**PASS**｜Stop：**PASS**｜Reset：**PASS**

## 5. 测试
```
Task 8 ：40/40     Task 9 ：55/55     Task 10：26/26
Task 11：66/66 + 57/57                Task 12：56/56 + 29/29
Task 13：60/60 + 33/33                Task 14：37/37
Task 15：45/45     Task 16：51/51     Task 18：31/31
Task 19：64/64     Task 20：79/79     Task 21：102/102
Task 22：81/81     Task 23：36/36
```
18 个测试，OK 18，FAIL 0，TIMEOUT 0。
总 PASS：**948**｜总 FAIL：**0**｜TIMEOUT：**0**

## 6. 清理
py_compile：**PASS**（9 模块，exit=0）｜键盘全部 UP：**PASS**｜鼠标全部 UP：**PASS**｜python/pythonw：**无**｜测试临时文件：**PASS**（已全部清理）｜Scores 是否干净：**是**（0 文件）

## 7. 问题
### production bug
**无。**（本轮只新增只读说明 UI，未改 parser / 播放逻辑 / 功能语义）

### 发现并如实上报：既有 UI 溢出（非 Task 22/23 引入）
- 现象：窗口默认尺寸 `700x500` 装不下当前全部内容——谱库**管理按钮行**（刷新/新建文件夹/新建琴谱/另存为/重命名/删除）与**快捷键提示**在默认尺寸下被裁掉（`winfo_ismapped()=0`，按钮行被压缩到 4px）。
- 证据：用 `winfo_rooty/winfo_height` 实测，`library_frame` 底边正好 500，`lib_btn_frame` 仅剩 4px。
- **对照验证**：用 **Backup 3（Task 21 状态）的 `ui.py`** 做同样测量，结果完全相同（`refresh_btn/new_folder_btn/rename_btn/delete_btn` 与 `shortcut0-2` 均 `mapped=0`）→ 证明该溢出**从 Task 18 加入谱库起就存在**，与 Task 22（中文化）和 Task 23（格式说明）无关；Task 23 未增加纵向高度（编辑区高度保持 134px）。
- 处理：Task 23 明确要求「不要改变 UI 整体布局 / 不要大规模调整 UI」，故**本任务不修改布局**，仅如实上报。建议在后续最终收尾阶段（FINAL REGRESSION 之后、重新打包之前）用最小改动修复（例如把窗口默认高度由 500 调到约 620，或把谱库树高由 6 行减到 3 行）。窗口可手动拉大即可看到被裁控件。

### 测试问题
- 2 处测试侧问题，已修正：
  1. 曾误用 `tk.Frame(root, pady=(0,8))`（Frame 的 pady 不接受元组）→ 改为在 `pack()` 上传 pady。
  2. 测试自建 FakeInput 缺 `held_nothing()`、且过早调用 `update_idletasks()` 导致几何读取为默认值 → 已补齐/调整。

### Backup 3 事件（必须如实说明）
- 在「对照测量既有溢出」时，我用 `importlib` 导入了 Backup 3 的 `ui.py`，Python 因此在 Backup 3 内生成了 `__pycache__\ui.cpython-314.pyc`（112 → 113 文件）。
- 发现后**立即删除**该缓存目录，Backup 3 已恢复原状：文件数 **112**、`BACKUP_INFO.txt` 哈希与创建时**完全一致**、且**没有任何文件在备份时间（23:43）之后被改动**。
- 结论：Backup 3 内容未被实质性修改，但过程中确有一次误写入缓存并已完全回退。后续不再以任何方式加载 Backup 目录中的文件。

## 8. 最终状态
- 是否修改 Backup 3：**否**（已回退误生成的缓存，恢复原状）
- 是否修改 Backup 2：**否**
- 是否重新打包 EXE：**否**

## 9. 最终结论

**Task 23：PASS**

Task 23 谱面格式说明完成，可以进入 FINAL REGRESSION、最终备份和 EXE 重新打包阶段。

然后停止：未进行 FINAL REGRESSION，未创建最终备份，未重新打包 EXE，未修改 Backup 3，未修改 Backup 2。

（附：请在最终收尾阶段决定是否修复第 7 节所述的既有 UI 溢出问题。）
