"""Task 8 纯逻辑测试：只测 score.py 的解析，不发送任何键盘/鼠标输入。

所有断言都是"解析结果 == 显式期望值"的精确比对（不是子串匹配）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from score import (  # noqa: E402
    ScoreParseError,
    NOTE_KEYS,
    parse_score,
    parse_score_notes,
)

NORMAL, SHARP, FLAT, HALF = "normal", "sharp", "flat", "half"

# (音符, 调音) 期望 → 变成 "1:normal;3:sharp" 这样的紧凑字符串便于比对
def fmt(notes):
    return ";".join(f"{n['note']}:{n['modifier']}" for n in notes)


def fmt_keys(notes):
    return ",".join(n["key"] for n in notes)


results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}  {name}")
    print(f"      {detail}")


def expect(name, text, expected):
    try:
        got = parse_score(text)
    except ScoreParseError as exc:
        check(name, False, f"unexpected ScoreParseError: {exc}")
        return
    actual = fmt(got)
    check(name, actual == expected, f"expected [{expected}]  actual [{actual}]")


def expect_error(name, text, needle):
    try:
        parse_score(text)
    except ScoreParseError as exc:
        got = str(exc)
        ok = needle in got
        check(name, ok, f"error={'OK' if ok else 'MISMATCH'}  msg=[{got}]")
    except Exception as exc:  # noqa: BLE001
        check(name, False, f"wrong exception type: {type(exc).__name__}: {exc}")
    else:
        check(name, False, "expected a ScoreParseError but parsing succeeded")


print("================ A. 基础音符 ================")
expect("A 基础音符 1 2 3 4 5 6 7 1'",
       "1 2 3 4 5 6 7 1'",
       "1:normal;2:normal;3:normal;4:normal;5:normal;6:normal;7:normal;1':normal")

notes_a = parse_score("1 2 3 4 5 6 7 1'")
check("A 键盘映射正确 (1->z 2->x 3->c 4->v 5->b 6->n 7->m 1'->,)",
      fmt_keys(notes_a) == "z,x,c,v,b,n,m,,",
      f"keys=[{fmt_keys(notes_a)}]")

print("\n================ B. 升调区间 [up 3 4 5] ================")
expect("B 1 2 [^ 3 4 5] 6",
       "1 2 [↑ 3 4 5] 6",
       "1:normal;2:normal;3:sharp;4:sharp;5:sharp;6:normal")

print("\n================ C. 降调 + 半音区间 ================")
expect("C 1 [v 2 3] 4 [~ 5 6] 7",
       "1 [↓ 2 3] 4 [~ 5 6] 7",
       "1:normal;2:flat;3:flat;4:normal;5:half;6:half;7:normal")

print("\n================ D. 跨行 / 混合分隔 ================")
expect("D 跨行解析 (换行等价于空格)",
       "1 2 3\n4 5 6\n7 1'",
       "1:normal;2:normal;3:normal;4:normal;5:normal;6:normal;7:normal;1':normal")
expect("D Tab 分隔",
       "1\t2\t3",
       "1:normal;2:normal;3:normal")
expect("D 多空行 / 行首尾空白 / 区间跨行内",
       "\n\n  1   2  \n\n  [↑ 3]  \n4\n",
       "1:normal;2:normal;3:sharp;4:normal")
expect("D 区间结束后恢复 normal（区间后紧跟音符）",
       "[~ 6 7] 1 [↑ 2] 3",
       "6:half;7:half;1:normal;2:sharp;3:normal")

print("\n================ E. 注释 ================")
expect("E 行尾注释",
       "1 2 3 # 这是注释\n4 5",
       "1:normal;2:normal;3:normal;4:normal;5:normal")
expect("E 整行注释 + 行内多段",
       "# 整行注释\n1 2 # 注释A\n3 # 注释B",
       "1:normal;2:normal;3:normal")
expect("E 只有注释的文件 -> 空列表",
       "# 只有注释\n# 第二行\n",
       "")
expect("E 注释符号紧跟音符（1#x）按注释处理",
       "1#comment\n2",
       "1:normal;2:normal")

print("\n================ F/G. 非法音符 ================")
expect_error("F 非法音符 8", "8", "invalid note '8'")
expect_error("F 非法音符在区间里", "1 [↑ 8] 2", "invalid note '8'")
expect_error("F 非法音符 0", "1 0 2", "invalid note '0'")
expect_error("G 非法字符串 abc", "abc", "invalid note 'abc'")
expect_error("G 非法字符串 1x", "1x", "invalid note '1x'")
expect_error("G 近似但非法的音符 1''", "1''", "invalid note")
expect_error("G 逗号本身不是合法音符（1' 才是）", "1 2 ,", "unexpected character ','")

print("\n================ H. 不完整调音区间 ================")
expect_error("H 缺少 ] （文件结尾）", "[↑ 1 2", "unclosed '['")
expect_error("H 缺少 ] （后跟换行）", "[↑ 1 2\n3", "unclosed '['")
expect_error("H 缺少 ] （注释截断）", "[↑ 1 2 # 注释", "unclosed '['")
expect_error("H 嵌套 [ 不合法", "[↑ [↓ 1] 2]", "nested '['")

print("\n================ I. 多余 / 缺失 括号 ================")
expect_error("I 多余 ]", "1 2 3]", "unexpected ']'")
expect_error("I 多余 ] 在行首", "]", "unexpected ']'")
expect_error("I 只有 ] 没有 [", "1 ] 2", "unexpected ']'")

print("\n================ J. 空输入 ================")
check("J 空字符串 -> 空列表", parse_score("") == [], f"got {parse_score('')}")
check("J 纯空白 -> 空列表", parse_score("   \n\t\n  ") == [], "whitespace only")
try:
    parse_score(None)
    check("J None -> TypeError", False, "no exception raised")
except TypeError as exc:
    check("J None -> TypeError", True, f"TypeError: {exc}")
except Exception as exc:  # noqa: BLE001
    check("J None -> TypeError", False, f"wrong exception: {type(exc).__name__}")

print("\n================ 额外：调音符号与边界 ================")
expect_error("额外 调音符号必须在括号内 (^ 1 2)",
             "↑ 1 2", "must be used inside a bracket")
expect_error("额外 空区间 [^]", "[↑]", "no notes")
expect_error("额外 空区间 []", "[]", "empty bracket")
expect_error("额外 括号里第一个不是调音符号", "[1 2]", "invalid modifier")
expect_error("额外 调音符号大小写无关的 normal 可显式写", "[Normal 1]", "invalid modifier")
expect("额外 normal 显式区间", "[normal 1 2] 3", "1:normal;2:normal;3:normal")
expect("额外 ASCII 写法表示升降调", "[+ 1] [- 2] [~ 3]", "1:sharp;2:flat;3:half")
expect("额外 区间内多个空格 / 制表符", "[  ↑   1 \t 2  ] 3", "1:sharp;2:sharp;3:normal")

print("\n================ 额外：parse_score_notes 与 NOTE_KEYS ================")
notes = parse_score_notes("1 [↑ 2] 1'")
check("额外 parse_score_notes 返回 Note 元组",
      notes[0].note == "1" and notes[0].key == "z" and notes[0].modifier == NORMAL
      and notes[1].modifier == SHARP and notes[2].key == ",",
      f"notes={notes}")
check("额外 as_dict() 结构与 parse_score 一致",
      notes[0].as_dict() == {"note": "1", "key": "z", "modifier": NORMAL},
      f"as_dict={notes[0].as_dict()}")
check("额外 NOTE_KEYS 就是文档里的 8 个音符",
      NOTE_KEYS == {"1": "z", "2": "x", "3": "c", "4": "v", "5": "b", "6": "n", "7": "m", "1'": ","},
      f"NOTE_KEYS={NOTE_KEYS}")

print()
failed = [name for name, ok in results if not ok]
print(f"总计 {len(results)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for name in failed:
        print("  - " + name)
    sys.exit(1)
print("全部通过")
