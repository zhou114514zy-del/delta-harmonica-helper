# TASK 19 REPORT — 谱库编辑与保存

## 1. 修改
- production 文件修改：
  - `score_library.py`（新增 `normalize_score_name` / `save_score` / `new_score`；`is_safe_relative` 增加 Windows 保留设备名校验）
  - `app_controller.py`（新增 `modified` 状态、`library_save_as` / `library_new_score`；open/save/load 成功后清 modified）
  - `ui.py`（新增「新建琴谱」「另存为」按钮与可测试接口；「当前琴谱」标签显示 `名称 *` 修改标记）
  - 以上均为 Task 18/19 的新增层文件，**非冻结核心**。
- 新增文件：`_verify\task19_save.py`（测试）
- Backup 2 是否修改：**否**（仍 97 文件）
- 冻结核心 6 文件是否修改：**否**（0 修改，SHA256 与基线一致）

## 2. 已有谱编辑
- 加载已有谱：**PASS**（`Loaded: Existing.txt`，内容进入 Score 区）
- 修改内容：**PASS**
- modified 状态：**PASS**（编辑后 `modified=True`，UI 显示 `Existing.txt *`）
- Save：**PASS**（写回原 .txt，`Saved: Existing.txt`，current_path 保持）
- 重新读取验证：**PASS**（文件内容与编辑框一致）
- UTF-8：**PASS**

## 3. Save As
- Save As：**PASS**（`Saved As: Copy.txt`，只写 Scores 内）
- 新文件创建：**PASS**（真实存在、内容正确）
- 原文件保护：**PASS**（原文件内容未被改写）
- current_path：**PASS**（更新为新文件）
- UTF-8：**PASS**；自动补 `.txt`（输入 `Copy` → `Copy.txt`）；已是 `.txt` 不产生 `.txt.txt`

## 4. 新建琴谱
- 新建：**PASS**（`New score: Song.txt`，排他创建，真实空文件）
- 编辑：**PASS**（空内容直接可输入）
- Save：**PASS**（写回新文件）
- 文件内容：**PASS**（`5 6 7`）
- current_path：**PASS**（指向新文件）

## 5. 取消
- 新建取消：**PASS**（显示「新建琴谱已取消」）
- Save As 取消：**PASS**（显示「另存为已取消」）
- 状态保持：**PASS**（内容/状态不变）
- current_path 保持：**PASS**（不被错误修改）

## 6. 安全
- `../`：**PASS**　- `..\`：**PASS**　- 绝对路径：**PASS**　- Scores 外路径：**PASS**
- symlink 逃逸：**PASS**（见第 11 节方法说明）
- 非法文件名：**PASS**（含 Windows 保留设备名 CON/PRN/…）
- 覆盖已有文件：**PASS**（新建时目标已存在 → 拒绝，原文件内容不变）

## 7. Playing 安全
- Playing → Open：**PASS**（安全停止 + 全部输入释放 + Hook 卸载 + Ready）
- Playing → Save：**PASS**（保存成功；按 Task 16 语义不打断播放——第七节兼容要求优先，详见第 11 节说明）
- Playing → 新建：**PASS**（全部输入释放 + Hook 卸载 + Ready）
- 输入全部释放：**PASS**
- 不会自动恢复 Playing：**PASS**

## 8. 谱面格式
- 普通音符自由换行：**PASS**（`1 2 3\n4 5 6\n7` 解析 7 个音符）
- 单行/多行解析一致：**PASS**（note/key/modifier 序列完全相同）
- 同一行调音组：**PASS**（`[↑ 3 4 5]` → 3 个 sharp）
- 调音组跨行处理：**PASS**（`[↑ 3 4\n5]` 按当前 score.py 规则报 `unclosed '['` 解析错误，与既有行为一致）

## 9. 测试
```
Task 8 ：40/40     Task 9 ：55/55     Task 10：26/26
Task 11：66/66 + 57/57                Task 12：56/56 + 29/29
Task 13：60/60 + 33/33                Task 14：37/37
Task 15：45/45     Task 16：51/51     Task 18：31/31
Task 19：64/64
```
14 个测试，OK 14，FAIL 0，TIMEOUT 0。
总 PASS：**650**（含历史回归 555 + Task 18 的 31 + Task 19 的 64）
总 FAIL：**0**
TIMEOUT：**0**

## 10. 最终状态
- py_compile：**PASS**（9 模块，exit=0）
- 键鼠全部 UP：**PASS**（14 项 VK 全 UP）
- python/pythonw 残留：**无**
- 测试临时文件清理：**PASS**（task19_tmp/task18_tmp/__pycache__ 已删；真实 Scores 目录 0 文件、无污染）

## 11. 问题
- production bug：**发现并修复 1 个（均为 Task 19 新增代码自身，非冻结核心）**：
  - 问题：`new_score("CON")` 未拒绝 Windows 保留设备名。实测这台 Win11 上 `open("CON.txt","x")` 竟然能成功创建文件，因此不能依赖 OS 层报错。
  - 修复：把保留设备名（CON/PRN/AUX/NUL/COM1-9/LPT1-9，含 `CON.txt` 形式）校验放进 `is_safe_relative` 统一防线，load/save/new 全部生效。
  - 修复后测试：Task 19 重跑 64/64 PASS；Task 18 回归 31/31 PASS。
- 测试脚本问题：无未解决。
- 方法说明（如实声明）：
  1. **symlink 逃逸**：本机 `os.symlink` 因权限/开发者模式限制无法创建真实符号链接，故按任务书「自动化无法可靠完成就报告」的原则，改用 `_is_within` 的 `realpath` 语义直接验证（路径经 realpath 归一化逃出 Scores 即拒绝），load/save 均走该防线。
  2. **Playing → Save 语义**：任务书第七节要求不破坏 Task 16（其测试明确断言「Playing 时 Save 不改变播放器位置与状态」），故 `save_file` 保持「保存不打断播放」；第 7 节 G 组「所有输入释放 / 不自动恢复 Playing」在 Open、新建两组场景中直接验证，Save 场景验证保存成功后经 Stop 全部释放。

## 12. 最终结论

**Task 19：PASS**

Task 19 谱库编辑与保存完成，可以进入 Task 20。

然后停止：未实现 Task 20，未重新打包 EXE，未修改 Backup 2。
