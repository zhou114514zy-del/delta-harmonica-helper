# TASK 21 REPORT — 谱库完整专项测试 + Backup 3

## 1. 测试范围
- Task 18（谱库基础）：31/31 PASS
- Task 19（编辑/保存/新建）：64/64 PASS
- Task 20（谱库管理）：79/79 PASS
- Task 21（独立大型集成测试）：102/102 PASS

## 2. 综合工作流
创建文件夹：**PASS**｜创建谱：**PASS**｜编辑：**PASS**｜Save：**PASS**｜Rename：**PASS**｜Delete：**PASS**｜清理：**PASS**（完整 TestA/Sub/song.txt 工作流闭环，最终结构不存在）

## 3. 嵌套谱库
三级嵌套（A/B/C）：**PASS**｜加载（1/2/3.txt）：**PASS**｜编辑：**PASS**｜Rename：**PASS**｜Delete：**PASS**（逐层删除，最终结构不存在）

## 4. 谱面格式
普通音符自由换行：**PASS**｜单行/多行解析一致：**PASS**｜调音组（↑/↓/~/normal）：**PASS**｜调音组跨行拒绝：**PASS**（`[↑ 3\n4 5]` 按 score.py 规则报错）

## 5. 编辑状态
modified：**PASS**（改→True，Save→False）｜Save：**PASS**｜Save As：**PASS**｜未保存内容保护：**PASS**（Rename 允许且内容不丢；Delete 拒绝且文件/current_path 不变）

## 6. Playing
Open：**PASS**（安全停止、键鼠 UP、Ready、不自动恢复）｜Rename：**PASS**（保持既有语义，无残留）｜Delete：**PASS**（安全结束、current_path 失效、Ready）｜文件夹管理：**PASS**｜键盘全部 UP：**PASS**｜鼠标全部 UP：**PASS**｜Hook 状态：**PASS**（正常卸载）

## 7. 安全
`../`：**PASS**｜`..\`：**PASS**｜绝对路径：**PASS**（C:/D:/ 全拒绝）｜Scores 外路径：**PASS**｜symlink：**PASS**（realpath 语义验证）｜Windows 保留设备名：**PASS**（CON/PRN/AUX/NUL/COM1/COM9/LPT1/LPT9）｜覆盖保护：**PASS**（外部文件未被删/改，未创建外部文件）

## 8. UI
Tree：**PASS**｜嵌套显示：**PASS**｜当前路径：**PASS**｜编辑区：**PASS**｜modified：**PASS**（`*` 标记）｜刷新：**PASS**（Rename/Delete/新建文件夹后 tree 均更新）

## 9. 回归测试
```
Task 8 ：40/40     Task 9 ：55/55     Task 10：26/26
Task 11：66/66 + 57/57                Task 12：56/56 + 29/29
Task 13：60/60 + 33/33                Task 14：37/37
Task 15：45/45     Task 16：51/51     Task 18：31/31
Task 19：64/64     Task 20：79/79     Task 21：102/102
```
16 个测试，OK 16，FAIL 0，TIMEOUT 0。
总 PASS：**831**｜总 FAIL：**0**｜TIMEOUT：**0**

## 10. 清理
py_compile：**PASS**（9 模块，exit=0）｜键盘全部 UP：**PASS**｜鼠标全部 UP：**PASS**｜python/pythonw：**无**｜测试临时文件：**PASS**（task*_tmp/__pycache__ 已删）｜Scores 是否干净：**是**（0 文件、0 目录）｜无 traceback / crash dump：**PASS**

## 11. Backup 3
- Backup 3 路径：`C:\Users\16966\Desktop\ds_w\delta-harmonica-helper_BACKUP_3_LIBRARY_STABLE\`
- Backup 3 创建：**PASS**（112 文件 = 111 源文件 + BACKUP_INFO.txt）
- BACKUP_INFO：**PASS**（含 Backup 名称、日期、Completed Tasks、regression 计数、冻结核心/谱库文件 SHA256）
- 关键文件：**PASS**（冻结核心 6 文件 + score_library/app_controller/ui/main/HANDOFF 齐全，_verify 存在）
- 完整性验证：**PASS**（111/111 源文件 SHA256 一致，0 missing、0 extra、0 不一致；全文件可读；无 dist/spec/__pycache__/pyc/task_tmp 污染）
- Backup 2 是否保持不变：**PASS**（97 文件，BACKUP_INFO 哈希不变）

## 12. 问题
- production bug：**发现并修复 1 个（非冻结核心，属 Task 20/21 UI 层）**：
  - 问题：UI 重命名**嵌套**文件时（`rename_selected_by_name`）未保留父目录，会把文件意外移动到 Scores 根目录。
  - 修复：文件重命名时自动带上原父目录（`parent + "/" + new_name`），重命名保持在原文件夹内。
  - 修复后：Task 21 重跑 102/102 PASS；Task 20 回归 79/79 不受影响。
- 测试问题（均已修正，非产品问题）：
  1. F7 断言把 9 个音符误写成 10（实际 9 是对的）。
  2. U9 未先保存就删除，被「未保存保护」正确拒绝——测试编排问题，改为先 Save 再 Delete。
  3. 误用 `new_folder_button.invoke()` 触发了一次真实「新建文件夹」对话框（违反不弹真实对话框原则）——已删除该行，改用可测试接口。
- symlink 测试限制：本机 `os.symlink` 因权限/开发者模式无法创建真实符号链接，未伪造；改用 `_is_within` 的 realpath 语义验证统一防线（load/delete/rename/save/mkdir 均走该防线）。

## 13. 最终状态
- 是否重新打包 EXE：**否**
- 是否实现后续 UI 中文化：**否**
- 是否加入谱面格式说明：**否**
- 是否修改 Backup 2：**否**

## 14. 最终结论

**Task 21：PASS**

Task 21 谱库专项验收完成，Backup 3 创建完成，可以进入最终 UI 中文化、谱面格式说明和最终重新打包阶段。

然后停止：未实现后续任务，未重新打包 EXE，未修改 Backup 2，未修改 Backup 3。
