"""测试超时守卫：单条测试超过指定时长就强制终止，并给出自检信息。

为什么需要它：
    有些测试会走到"弹系统对话框等待人工操作"这种阻塞路径（例如文件选择框）。
    无人操作时会永久挂起。这个守卫保证任何一步都不会无限等待。

用法：
    python _verify/run_tests.py <timeout_seconds> <test1.py> [test2.py ...]

行为：
    每个测试单独一个子进程 + 硬超时；超时则 kill，并打印：
        - 超时的测试名与实际耗时
        - 已捕获的输出（截断）
        - 残留进程提示
"""
import os
import subprocess
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_one(script_path, timeout_s):
    """跑一个测试脚本，返回 (状态, 耗时秒, 输出文本)。"""
    start = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, script_path],
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        elapsed = time.monotonic() - start
        return ("ok" if proc.returncode == 0 else "fail"), elapsed, out or ""
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            out, _ = proc.communicate(timeout=10)
        except Exception:
            out = ""
        elapsed = time.monotonic() - start
        return "timeout", elapsed, out or ""


def count_results(text):
    passed = failed = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("PASS "):
            passed += 1
        elif stripped.startswith("FAIL "):
            failed += 1
    return passed, failed


def main():
    if len(sys.argv) < 3:
        print("usage: run_tests.py <timeout_seconds> <test1.py> [test2.py ...]")
        return 2

    timeout_s = float(sys.argv[1])
    scripts = sys.argv[2:]
    print("=" * 72)
    print(f"测试超时守卫：每条测试上限 {timeout_s:.0f} 秒（超过自动终止并自检）")
    print("=" * 72)

    summary = []
    for script in scripts:
        name = os.path.basename(script)
        status, elapsed, out = run_one(script, timeout_s)
        passed, failed = count_results(out)
        summary.append((name, status, elapsed, passed, failed))

        flag = {"ok": "OK   ", "fail": "FAIL ", "timeout": "TIMEOUT"}[status]
        print(f"  {flag} {name:<34} {elapsed:6.1f}s  PASS={passed:<4} FAIL={failed}")

        if status == "timeout":
            print(f"        !! 超过 {timeout_s:.0f} 秒被强制终止 —— 该测试可能卡在阻塞操作上")
            tail = [ln for ln in out.splitlines() if ln.strip()][-8:]
            for ln in tail:
                print("        | " + ln[:150])
        elif status == "fail" and failed == 0:
            tail = [ln for ln in out.splitlines() if "Error" in ln or "Traceback" in ln][-4:]
            for ln in tail:
                print("        | " + ln[:150])

    print("-" * 72)
    timeouts = [s for s in summary if s[1] == "timeout"]
    failures = [s for s in summary if s[1] == "fail"]
    print(f"总计 {len(summary)} 个测试：OK {len(summary) - len(timeouts) - len(failures)}，"
          f"FAIL {len(failures)}，TIMEOUT {len(timeouts)}")

    if timeouts:
        print("\n超时的测试（需要检查是否有阻塞操作）：")
        for name, _, elapsed, _, _ in timeouts:
            print(f"  - {name}（{elapsed:.1f}s）")
    if failures:
        print("\n失败的测试：")
        for name, _, elapsed, passed, failed in failures:
            print(f"  - {name}（PASS={passed} FAIL={failed}）")

    return 0 if not timeouts and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
