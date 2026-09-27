# TASK 20 REPORT — 谱库管理

## 1. 修改
- production 文件修改：
  - `score_library.py`（新增 `rename_score` / `delete_score` / `rename_folder` / `delete_folder`；`create_folder` 扩展为支持嵌套；`is_safe_relative` 增加尾点/尾空格校验）
  - `app_controller.py`（新增 `library_rename_score` / `library_delete_score` / `library_rename_folder` / `library_delete_folder` + `_path_in_dir`；含 current_path 更新/失效、modified 保护、Playing 安全）
  - `ui.py`（新增「重命名」「删除」按钮与可测试接口；删除前确认）
  - 以上均为 Task 18–20 新增层文件，**非冻结核心**。
- 新增文件：`_verify\task20_library_management.py`（测试）
- Backup 2 是否修改：**否**（仍 97 文件）
- 冻结核心 6 文件是否修改：**否**（0 修改，SHA256 与基线一致）

## 2. Rename 文件
- Rename：**PASS**（`root.txt → root2.txt`，真实文件移动）
- 自动 .txt：**PASS**（`root3 → root3.txt`；已是 `.txt` 不重复补）
- 原文件保护：**PASS**（内容不变，UTF-8 保持；目标已存在时拒绝，源/目标都不变）
- current_path：**PASS**（重命名当前谱时同步更新）
- UTF-8：**PASS**

## 3. Delete 文件
- 删除：**PASS**（真实文件移除；不存在时安全返回 error；目录不作为琴谱删除）
- current_path 清理：**PASS**（删除当前谱后 current_path 置 None、编辑区清空、状态 Ready）
- tree 刷新：**PASS**

## 4. 新建文件夹
- 创建：**PASS**
- 嵌套创建：**PASS**（`A/C` 自动建中间目录）
- tree 刷新：**PASS**

## 5. Rename 文件夹
- Rename：**PASS**（真实文件夹重命名）
- 嵌套路径：**PASS**（`A/B → A/B2`，内部文件跟随）
- 内部文件完整：**PASS**

## 6. Delete 文件夹
- 空文件夹删除：**PASS**
- 非空文件夹保护：**PASS**（非空拒绝，内部谱不丢）
- Scores 根目录保护：**PASS**（根不可重命名、不可删除）

## 7. 安全
- `../`：**PASS**　- `..\`：**PASS**　- 绝对路径：**PASS**（C:、D:、C:/ 均覆盖）
- Scores 外路径：**PASS**（含 `..\outside.txt` 真实外部路径）
- symlink 逃逸：**PASS**（见第 12 节方法说明）
- Windows 保留设备名：**PASS**（CON/PRN/AUX/NUL/COM1/LPT1 对 rename/new/create_folder 全拒绝）
- 覆盖已有目标：**PASS**（rename 到已存在目标拒绝，源/目标内容均不变）

## 8. 状态安全
- modified 未保存保护：**PASS**（删除当前谱且未保存 → 拒绝，文件与 current_path 不变；重命名允许且 modified 保留）
- current_path 更新：**PASS**（重命名当前谱 / 重命名其所在文件夹均正确更新）
- current_path 失效处理：**PASS**（删除当前谱后失效并清空编辑区）
- Playing 安全：**PASS**（Playing 中 Rename 保持既有语义不打断；Playing 中 Delete 当前谱先安全结束）
- 键鼠全部释放：**PASS**（Delete 后无残留、Hook 卸载、不自动恢复 Playing）

## 9. 嵌套谱库
- 加载嵌套谱：**PASS**（`A/B/2.txt`）
- Rename 嵌套谱：**PASS**（`A/1.txt → A/1x.txt`）
- 删除嵌套谱：**PASS**
- 创建嵌套文件夹：**PASS**（`A/C`）

## 10. 测试
```
Task 8 ：40/40     Task 9 ：55/55     Task 10：26/26
Task 11：66/66 + 57/57                Task 12：56/56 + 29/29
Task 13：60/60 + 33/33                Task 14：37/37
Task 15：45/45     Task 16：51/51     Task 18：31/31
Task 19：64/64     Task 20：79/79
```
15 个测试，OK 15，FAIL 0，TIMEOUT 0。
总 PASS：**729**
总 FAIL：**0**
TIMEOUT：**0**

## 11. 编译与清理
- py_compile：**PASS**（9 模块，exit=0）
- 键鼠全部 UP：**PASS**（14 项 VK 全 UP）
- python/pythonw 残留：**无**
- 测试临时文件：**PASS**（task20_tmp/task19_tmp/task18_tmp/__pycache__ 已删）
- Scores 是否恢复干净：**是**（0 文件）

## 12. 问题
- production bug：**无**（本轮 Task 20 未发现 production bug）。
- 测试脚本问题：**无未解决**（自测中发现 1 处恒真断言 `… or True`，已改为真实断言「Rename 保持既有语义：仍在 Playing 且输入保持」，非产品问题）。
- 方法说明（如实声明）：**symlink 逃逸**——本机 `os.symlink` 因权限/开发者模式限制无法创建真实符号链接，故按任务书「自动化无法可靠验证就如实报告」原则，改用 `_is_within` 的 `realpath` 语义直接验证同一防线（load/delete/rename/save 全部走该防线），未伪造成功。

## 13. 最终状态
- 是否修改 Backup 2：**否**
- 是否重新打包 EXE：**否**
- 是否实现 Task 21：**否**

## 14. 最终结论

**Task 20：PASS**

Task 20 谱库管理完成，可以进入 Task 21。

然后停止：未实现 Task 21，未重新打包 EXE，未修改 Backup 2。
