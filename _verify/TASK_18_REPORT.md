# TASK 18 REPORT — 谱库基础

## 1. 修改
- production 文件修改：
  - `ui.py`（新增谱库 Treeview 区域 + 刷新/新建文件夹按钮 + 双击加载）
  - `app_controller.py`（新增谱库接口：library_scan / library_create_folder / library_load_score）
  - 以上两文件属 Task 14–16 的 UI/连接层，**非冻结核心**。
  - 冻结核心 6 文件（input / score / playback / playback_executor / harmonica_app / config.json）**0 修改**（SHA256 与基线一致）。
- 新增文件：`score_library.py`（纯逻辑：Scores 目录管理、扫描、创建文件夹、读取琴谱、路径安全校验）
- Backup 2 是否修改：**否**（仍 97 文件，未加入 score_library.py）

## 2. 谱库
- Scores 自动创建：**PASS**（启动即 `ensure_scores_dir` 创建 `Scores\`，幂等）
- 根目录扫描：**PASS**（根目录 .txt 正确列出）
- `.txt` 扫描：**PASS**
- 非 `.txt` 忽略：**PASS**（`.md` / `.png` 等不显示、不作为琴谱）
- 子文件夹扫描：**PASS**（`Sub/Song1.txt`、`Sub/Song2.txt` 正确挂到子文件夹节点）
- 新建文件夹：**PASS**（真实 Windows 文件夹创建，创建后自动刷新）

## 3. 加载
- 真实 `.txt` 加载：**PASS**（点击/双击 .txt → 内容进入 Score 编辑区）
- UTF-8：**PASS**（中文琴谱内容正确读回）
- 当前文件路径：**PASS**（`current_path` 记录绝对路径；UI 显示「当前琴谱: <路径>」）
- 加载后不自动播放：**PASS**（Playing 时加载会安全释放输入并进入 Ready，不恢复播放）

## 4. 安全
- `../`：**PASS**（create_folder、load_score 均拒绝）
- `..\`：**PASS**（load_score 拒绝）
- 绝对路径：**PASS**（`C:\...` 拒绝，create/load 均覆盖）
- Scores 外路径：**PASS**（`is_safe_relative` + `realpath` 双重校验，符号链接逃逸也拒绝）

## 5. 回归
全部通过，数字与既有基线完全一致：

```
Task 8 ：40/40
Task 9 ：55/55
Task 10：26/26
Task 11：66/66 + 57/57
Task 12：56/56 + 29/29
Task 13：60/60 + 33/33
Task 14：37/37
Task 15：45/45
Task 16：51/51
```
合计 12 个测试 OK，FAIL 0，TIMEOUT 0。Task 18 新测试 `task18_library.py` 31 PASS / 0 FAIL。

## 6. 最终状态
- py_compile：**PASS**（9 个模块，exit=0）
- 键鼠全部 UP：**PASS**（Enter/Z/X/C/V/B/N/M/Comma/Left/Middle/Right/R/Esc 全 UP）
- python/pythonw 残留：**无**
- 测试临时文件清理：**PASS**（`_verify\task18_tmp`、`__pycache__` 已删；真实 Scores 目录 0 文件、无污染）

## 7. 问题
无 production bug（冻结核心 0 修改）。

开发自测中发现并修复 1 处**新增 UI 代码自身**的 bug（与既有冻结核心无关）：谱库 Treeview 顶层文件夹/文件最初被插成 `Scores` 根节点的兄弟而非子节点（因 `Scores` 节点用了自动生成的 iid）。已改为给 `Scores` 固定 iid 并把顶层条目挂到其下，重测 31/31 PASS。

## 8. 最终结论

**Task 18：PASS**

Task 18 谱库基础完成，可以进入 Task 19。

然后停止：未实现 Task 19，未重新打包 EXE。
