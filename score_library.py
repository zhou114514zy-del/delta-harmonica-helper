"""谱库基础（Task 18）。

只做"真实文件系统里的 Scores 目录"的扫描 / 创建文件夹 / 读取琴谱，以及路径安全校验。

刻意不做的事情：
    - 不碰 UI（tkinter）
    - 不碰播放核心（score / playback / input / harmonica_app）
    - 不使用数据库、不做缓存——真实 .txt 文件和真实文件夹就是唯一数据来源
    - 不做删除 / 重命名 / 新建琴谱（留给后续 Task）

安全边界：
    只能访问 Scores 目录及其子目录；
    拒绝绝对路径、盘符、路径穿越（../ 、 ..\\ ）、非 .txt 文件、Windows 非法文件名。
"""

import os
import re

SCORES_DIR_NAME = "Scores"

# Windows 文件名非法字符（\ / 是路径分隔符，单独处理）
_INVALID_CHARS = re.compile(r'[<>:"|?*]')
# Windows 保留设备名
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"}
_RESERVED_RE = re.compile(r"^(COM|LPT)[1-9]$")
_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


def project_dir_of(module_file):
    """由本模块文件位置推出项目根目录（本模块放在项目根目录下）。"""
    return os.path.dirname(os.path.abspath(module_file))


_PROJECT_DIR = project_dir_of(__file__)


def scores_root(project_dir=None):
    """返回 Scores 根目录路径（不创建）。"""
    return os.path.join(project_dir or _PROJECT_DIR, SCORES_DIR_NAME)


def ensure_scores_dir(project_dir=None):
    """确保 Scores 目录存在，返回其路径（幂等，不报错）。"""
    root = scores_root(project_dir)
    os.makedirs(root, exist_ok=True)
    return root


def _is_within(root, target):
    """target 是否位于 root 内（用 realpath 防止符号链接逃逸）。"""
    root_real = os.path.realpath(root)
    target_real = os.path.realpath(target)
    return target_real == root_real or target_real.startswith(root_real + os.sep)


def is_safe_relative(relpath):
    """相对路径安全校验。

    拒绝：绝对路径、盘符（C:）、空字符串、以及任何等于 "" / "." / ".." 的路径段、
    含 Windows 非法字符的路径段、Windows 保留设备名（CON / PRN / AUX / NUL /
    COM1-9 / LPT1-9，含带扩展名的形式，如 CON.txt）。
    """
    if not isinstance(relpath, str) or relpath == "":
        return False
    if os.path.isabs(relpath):
        return False
    if _DRIVE_RE.match(relpath):
        return False
    parts = re.split(r"[\\/]+", relpath)
    if not parts:
        return False
    for part in parts:
        if part in ("", ".", ".."):
            return False
        if part.endswith((".", " ")):
            return False
        if _INVALID_CHARS.search(part):
            return False
        base = part.split(".")[0].upper()
        if base in _RESERVED_NAMES or _RESERVED_RE.match(base):
            return False
    return True


def list_scores(project_dir=None):
    """扫描真实 Scores 目录，返回条目列表（文件夹 + .txt 琴谱），忽略非 .txt 文件。

    每个条目：
        {"type": "folder" | "file", "name": 显示名,
         "relpath": 相对 Scores 根的路径（用 "/" 分隔）, "parent": 父目录 relpath（"" 表示根）}
    """
    root = ensure_scores_dir(project_dir)
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if rel == ".":
            rel = ""
        for d in sorted(dirnames):
            child = os.path.join(rel, d) if rel else d
            entries.append({
                "type": "folder", "name": d,
                "relpath": child.replace(os.sep, "/"),
                "parent": rel.replace(os.sep, "/"),
            })
        for f in sorted(filenames):
            if not f.lower().endswith(".txt"):
                continue
            child = os.path.join(rel, f) if rel else f
            entries.append({
                "type": "file", "name": f,
                "relpath": child.replace(os.sep, "/"),
                "parent": rel.replace(os.sep, "/"),
            })
    return entries


def create_folder(name, project_dir=None):
    """在 Scores 内创建真实 Windows 文件夹（支持嵌套，如 "A/B"）。

    返回 ("ok", name) 或 ("error", 原因)。拒绝非法名 / 路径穿越 / 绝对路径 / 越界。
    """
    root = ensure_scores_dir(project_dir)
    if not isinstance(name, str) or not name.strip():
        return ("error", "文件夹名为空")
    name = name.strip()
    if os.path.isabs(name) or _DRIVE_RE.match(name):
        return ("error", "不允许绝对路径")
    if not is_safe_relative(name):
        return ("error", "文件夹名无效")
    target = os.path.join(root, name.replace("/", os.sep))
    if not _is_within(root, target):
        return ("error", "路径越出谱库范围")
    try:
        os.makedirs(target, exist_ok=False)
    except FileExistsError:
        return ("error", "文件夹已存在")
    except OSError as exc:  # noqa: BLE001 - 系统错误要安全返回，不崩
        return ("error", str(exc))
    return ("ok", name)


def resolve_score_path(relpath, project_dir=None):
    """把安全且为 .txt 的相对路径解析成绝对路径；不合法返回 None。"""
    if not is_safe_relative(relpath):
        return None
    if not relpath.lower().endswith(".txt"):
        return None
    root = ensure_scores_dir(project_dir)
    target = os.path.join(root, relpath.replace("/", os.sep))
    if not _is_within(root, target):
        return None
    return target


def load_score(relpath, project_dir=None):
    """读取 Scores 内一个真实 .txt 琴谱（UTF-8）。

    返回 ("ok", text) 或 ("error", 原因)。
    """
    target = resolve_score_path(relpath, project_dir)
    if target is None:
        return ("error", "琴谱路径无效")
    try:
        with open(target, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:  # noqa: BLE001
        return ("error", str(exc))
    return ("ok", text)


def normalize_score_name(name):
    """把用户输入的琴谱名规范成 .txt 相对路径。

    自动补 .txt（已经是 .txt 时不再补，不会出现 .txt.txt）；
    不合法（绝对路径 / 穿越 / 非法字符 / 空）返回 None。
    """
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    if not name.lower().endswith(".txt"):
        name += ".txt"
    if not is_safe_relative(name):
        return None
    return name


def save_score(relpath, text, project_dir=None):
    """把文本以 UTF-8 保存到 Scores 内的一个 .txt（标准 Save As 语义，覆盖目标）。

    返回 ("ok", 绝对路径) 或 ("error", 原因)。
    """
    relpath = normalize_score_name(relpath)
    if relpath is None:
        return ("error", "琴谱名无效")
    root = ensure_scores_dir(project_dir)
    target = os.path.join(root, relpath.replace("/", os.sep))
    if not _is_within(root, target):
        return ("error", "路径越出谱库范围")
    if not os.path.isdir(os.path.dirname(target)):
        return ("error", "文件夹不存在")
    try:
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:  # noqa: BLE001
        return ("error", str(exc))
    return ("ok", target)


def new_score(name, project_dir=None):
    """在 Scores 内新建一个空 .txt 琴谱（排他创建，绝不覆盖已有文件）。

    返回 ("ok", relpath, 绝对路径) 或 ("error", 原因)。
    """
    relpath = normalize_score_name(name)
    if relpath is None:
        return ("error", "琴谱名无效")
    root = ensure_scores_dir(project_dir)
    target = os.path.join(root, relpath.replace("/", os.sep))
    if not _is_within(root, target):
        return ("error", "路径越出谱库范围")
    if not os.path.isdir(os.path.dirname(target)):
        return ("error", "文件夹不存在")
    if os.path.exists(target):
        return ("error", "文件已存在")
    try:
        with open(target, "x", encoding="utf-8") as fh:
            fh.write("")
    except OSError as exc:  # noqa: BLE001
        return ("error", str(exc))
    return ("ok", relpath, target)


def rename_score(old_relpath, new_name, project_dir=None):
    """重命名 / 移动 Scores 内的一个 .txt 琴谱（不覆盖已有目标）。

    返回 ("ok", 新相对路径, 新绝对路径) 或 ("error", 原因)。
    """
    if not is_safe_relative(old_relpath):
        return ("error", "源路径无效")
    if not old_relpath.lower().endswith(".txt"):
        return ("error", "不是 .txt 琴谱")
    new_relpath = normalize_score_name(new_name)
    if new_relpath is None:
        return ("error", "新名称无效")
    root = ensure_scores_dir(project_dir)
    src = os.path.join(root, old_relpath.replace("/", os.sep))
    dst = os.path.join(root, new_relpath.replace("/", os.sep))
    if not _is_within(root, src) or not _is_within(root, dst):
        return ("error", "路径越出谱库范围")
    if not os.path.isfile(src):
        return ("error", "文件不存在")
    if os.path.exists(dst):
        return ("error", "目标已存在")
    try:
        os.rename(src, dst)
    except OSError as exc:  # noqa: BLE001
        return ("error", str(exc))
    return ("ok", new_relpath, dst)


def delete_score(relpath, project_dir=None):
    """删除 Scores 内的一个 .txt 琴谱（只删文件，不删目录）。

    返回 ("ok", relpath) 或 ("error", 原因)。
    """
    if not is_safe_relative(relpath):
        return ("error", "路径无效")
    if not relpath.lower().endswith(".txt"):
        return ("error", "不是 .txt 琴谱")
    root = ensure_scores_dir(project_dir)
    target = os.path.join(root, relpath.replace("/", os.sep))
    if not _is_within(root, target):
        return ("error", "路径越出谱库范围")
    if not os.path.isfile(target):
        return ("error", "文件不存在")
    try:
        os.remove(target)
    except OSError as exc:  # noqa: BLE001
        return ("error", str(exc))
    return ("ok", relpath)


def rename_folder(old_relpath, new_name, project_dir=None):
    """重命名 Scores 内的一个文件夹（新名称只能是单段名称，同父目录）。

    返回 ("ok", 新相对路径) 或 ("error", 原因)。
    """
    if not is_safe_relative(old_relpath):
        return ("error", "源路径无效")
    if not isinstance(new_name, str) or not new_name.strip():
        return ("error", "文件夹名为空")
    new_name = new_name.strip()
    if os.path.isabs(new_name) or _DRIVE_RE.match(new_name):
        return ("error", "不允许绝对路径")
    if "/" in new_name or "\\" in new_name:
        return ("error", "文件夹名不能包含路径分隔符")
    if not is_safe_relative(new_name):
        return ("error", "文件夹名无效")
    root = ensure_scores_dir(project_dir)
    src = os.path.join(root, old_relpath.replace("/", os.sep))
    if not _is_within(root, src):
        return ("error", "路径越出谱库范围")
    if not os.path.isdir(src):
        return ("error", "文件夹不存在")
    parent = os.path.dirname(src)
    dst = os.path.join(parent, new_name)
    if not _is_within(root, dst):
        return ("error", "路径越出谱库范围")
    if os.path.exists(dst):
        return ("error", "目标已存在")
    try:
        os.rename(src, dst)
    except OSError as exc:  # noqa: BLE001
        return ("error", str(exc))
    new_relpath = os.path.relpath(dst, root).replace(os.sep, "/")
    return ("ok", new_relpath)


def delete_folder(relpath, project_dir=None):
    """删除 Scores 内一个**空**文件夹（非空拒绝，保护谱库；不删根目录）。

    返回 ("ok", relpath) 或 ("error", 原因)。
    """
    if not is_safe_relative(relpath):
        return ("error", "路径无效")
    root = ensure_scores_dir(project_dir)
    target = os.path.join(root, relpath.replace("/", os.sep))
    if not _is_within(root, target):
        return ("error", "路径越出谱库范围")
    if not os.path.isdir(target):
        return ("error", "文件夹不存在")
    if os.listdir(target):
        return ("error", "文件夹非空")
    try:
        os.rmdir(target)
    except OSError as exc:  # noqa: BLE001
        return ("error", str(exc))
    return ("ok", relpath)
