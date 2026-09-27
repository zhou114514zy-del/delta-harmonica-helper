"""琴谱相关模块。

当前阶段（Task 8）：把文本琴谱解析成结构化音符列表。

只做"文本 -> 结构化数据"，不做播放、不调用 input.py、不发送任何键盘或鼠标输入。

语法：
    基础音符  1 2 3 4 5 6 7 1'
    调音区间  [↑ 1 2 3]   [↓ 4 5]   [~ 6 7]
    区间结束自动恢复 normal
    分隔符    空格 / Tab / 换行
    注释      # 到行尾
    调音符号  ↑ 升调 / ↓ 降调 / ~ 半音（normal 也可显式写）

用法：
    from score import parse_score, ScoreParseError

    notes = parse_score("1 2 [↑ 3 4 5] 6")
    # [{'note': '1', 'key': 'z', 'modifier': 'normal'}, ...]
"""

from typing import Dict, List, NamedTuple

# 音符 -> 键盘键
NOTE_KEYS: Dict[str, str] = {
    "1": "z",
    "2": "x",
    "3": "c",
    "4": "v",
    "5": "b",
    "6": "n",
    "7": "m",
    "1'": ",",
}

# 调音状态
MODIFIER_NORMAL = "normal"
MODIFIER_SHARP = "sharp"
MODIFIER_FLAT = "flat"
MODIFIER_HALF = "half"

MODIFIERS = {
    "normal": MODIFIER_NORMAL,
    "↑": MODIFIER_SHARP,
    "+": MODIFIER_SHARP,      # ↑ 的 ASCII 写法
    "↓": MODIFIER_FLAT,
    "-": MODIFIER_FLAT,       # ↓ 的 ASCII 写法
    "~": MODIFIER_HALF,
}

# 会与语法冲突、需要明确报错的字符。
# 注意：[ ] 由专门的括号分支处理，绝不能放进这里，否则区间语法会先被拦掉。
DELIMITERS = "\"',;"
COMMENT_CHARS = "#"


class Note(NamedTuple):
    """一个结构化音符。"""

    note: str        # 原始音符，如 "1"、"1'"
    key: str         # 对应键盘键，如 "z"、","
    modifier: str    # normal / sharp / flat / half

    def as_dict(self) -> dict:
        return {"note": self.note, "key": self.key, "modifier": self.modifier}


class ScoreParseError(ValueError):
    """琴谱解析错误。消息里带有出错的位置。"""

    def __init__(self, message: str, line: int = 1, column: int = 1):
        self.line = line
        self.column = column
        self.message = message
        super().__init__(f"line {line}, column {column}: {message}")


class _Token(NamedTuple):
    text: str
    kind: str        # "word" 或 "bracket"
    line: int
    column: int


def parse_score(text) -> List[dict]:
    """把文本琴谱解析成音符字典列表。

    参数:
        text: 琴谱文本。可以为空（返回空列表）。

    返回:
        [{"note": "1", "key": "z", "modifier": "normal"}, ...]

    异常:
        ScoreParseError: 词法或语法错误，消息里带 line/column。
        TypeError: 传入的不是字符串。
    """
    if text is None:
        raise TypeError("score text must be a string, got None")
    if not isinstance(text, str):
        raise TypeError(f"score text must be a string, got {type(text).__name__}")

    tokens = _tokenize(text)
    return [note.as_dict() for note in _parse_tokens(tokens)]


def parse_score_notes(text) -> List[Note]:
    """与 parse_score 相同，但返回 Note 元组（给程序内部使用更方便）。"""
    if text is None:
        raise TypeError("score text must be a string, got None")
    if not isinstance(text, str):
        raise TypeError(f"score text must be a string, got {type(text).__name__}")
    return _parse_tokens(_tokenize(text))


# ---------------- 词法 ----------------

def _tokenize(text: str) -> List[_Token]:
    """切分成 word / bracket 两类记号，并记录每个记号的起始行列。

    括号区间是一次性整体扫描的，所以 '[' 段内不会再被切分；
    行列信息仍然按真实换行推进，报错位置因此是准确的。
    """
    tokens: List[_Token] = []
    line = 1
    column = 1
    i = 0
    length = len(text)

    while i < length:
        ch = text[i]

        if ch == "\n":
            line += 1
            column = 1
            i += 1
            continue

        if ch.isspace():
            column += 1
            i += 1
            continue

        if ch in COMMENT_CHARS:
            while i < length and text[i] != "\n":
                i += 1
            continue

        if ch == "]":
            raise ScoreParseError("unexpected ']' (no matching '[')", line, column)

        if ch in "↑↓~":
            raise ScoreParseError(
                f"modifier {ch!r} must be used inside a bracket, e.g. [{ch} 1 2]",
                line, column,
            )

        if ch in DELIMITERS:
            raise ScoreParseError(f"unexpected character {ch!r}", line, column)

        if ch == "[":
            end = _find_bracket_end(text, i)
            if end == -1:
                raise ScoreParseError("unclosed '[': missing ']'", line, column)
            inner = text[i + 1:end]
            if "[" in inner:
                bad_index = inner.index("[")
                bad_line, bad_column = _advance(line, column + 1, inner[:bad_index])
                raise ScoreParseError("nested '[' is not allowed", bad_line, bad_column)
            tokens.append(_Token(inner, "bracket", line, column))
            line, column = _advance(line, column + 1, inner)
            column += 1          # 消费掉 ']'
            i = end + 1
            continue

        # 普通记号：连续的非空白、非注释、非括号字符
        start = i
        while i < length and not text[i].isspace() and text[i] not in "[]#":
            i += 1
        tokens.append(_Token(text[start:i], "word", line, column))
        column += i - start

    return tokens


def _find_bracket_end(text: str, start: int) -> int:
    """找到与 text[start] == '[' 匹配的 ']'；找不到返回 -1。

    括号内不允许换行，所以遇到换行就视为"漏了 ']'"。
    """
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "]":
            return i
        if ch == "\n":
            return -1
        i += 1
    return -1


def _advance(line: int, column: int, consumed: str):
    """按已消费的文本推进行列位置。"""
    newlines = consumed.count("\n")
    if newlines:
        return line + newlines, len(consumed) - consumed.rfind("\n")
    return line, column + len(consumed)


# ---------------- 语法 ----------------

def _parse_tokens(tokens: List[_Token]) -> List[Note]:
    notes: List[Note] = []
    for token in tokens:
        if token.kind == "word":
            if token.text not in NOTE_KEYS:
                raise ScoreParseError(
                    f"invalid note {token.text!r}; valid notes are: {' '.join(NOTE_KEYS)}",
                    token.line, token.column,
                )
            notes.append(Note(note=token.text, key=NOTE_KEYS[token.text], modifier=MODIFIER_NORMAL))
        else:
            notes.extend(_parse_bracket(token))
    return notes


def _parse_bracket(token: _Token) -> List[Note]:
    """解析 [调音符号 音符...] 区间里的每个音符。

    括号内不允许换行，所以这里所有位置都在 token.line 上，
    列号按"字符在括号内的真实偏移"计算（token 从 '[' 开始，故 +1）。
    """
    parts = _split_with_offsets(token.text)
    if not parts:
        raise ScoreParseError(
            "empty bracket: expected a modifier and at least one note, e.g. [↑ 1 2]",
            token.line, token.column,
        )

    modifier_text, modifier_offset = parts[0]
    if modifier_text not in MODIFIERS:
        raise ScoreParseError(
            f"invalid modifier {modifier_text!r} in bracket; expected one of: ↑ ↓ ~ normal",
            token.line, token.column + modifier_offset,
        )
    modifier = MODIFIERS[modifier_text]

    note_parts = parts[1:]
    if not note_parts:
        raise ScoreParseError(
            f"empty bracket: [{modifier_text}] has no notes; expected e.g. [{modifier_text} 1 2]",
            token.line, token.column + modifier_offset,
        )

    notes: List[Note] = []
    for raw, offset in note_parts:
        if raw not in NOTE_KEYS:
            raise ScoreParseError(
                f"invalid note {raw!r}; valid notes are: {' '.join(NOTE_KEYS)}",
                token.line, token.column + offset,
            )
        notes.append(Note(note=raw, key=NOTE_KEYS[raw], modifier=modifier))
    return notes


def _split_with_offsets(text: str):
    """按空白切分，并记录每段在 text 里的起始偏移。"""
    parts = []
    i = 0
    length = len(text)
    while i < length:
        while i < length and text[i].isspace():
            i += 1
        if i >= length:
            break
        start = i
        while i < length and not text[i].isspace():
            i += 1
        parts.append((text[start:i], start))
    return parts
