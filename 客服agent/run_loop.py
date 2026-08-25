"""闭环脚本 — 测试 → LLM修复 → 重启后端 → 再测试"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json
import os
import time
import subprocess
from datetime import datetime
from pathlib import Path

# ── 配置 ────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent
MAX_ROUNDS = 3
TARGET_PASS_RATE = 95.0
BACKEND_PORT = 8001
BACKEND_DIR = PROJECT_DIR / "backend"


def check_backend() -> bool:
    """检查后端是否运行"""
    import requests
    try:
        r = requests.get(f"http://localhost:{BACKEND_PORT}/api/health", timeout=3)
        return r.status_code == 200
    except:
        return False


def restart_backend():
    """重启后端"""
    print("\n🔄 重启后端...")

    # 杀旧进程
    try:
        result = subprocess.run(
            ["powershell", "-Command", f"Get-NetTCPConnection -LocalPort {BACKEND_PORT} -ErrorAction SilentlyContinue | ForEach-Object {{ taskkill /PID $_.OwningProcess /F }}"],
            capture_output=True, text=True, timeout=10
        )
    except:
        pass

    time.sleep(2)

    # 启动新进程
    try:
        subprocess.Popen(
            ["python", "main.py"],
            cwd=str(BACKEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("   后端已启动")
    except Exception as e:
        print(f"   启动失败: {e}")
        return False

    # 等待后端就绪
    for i in range(10):
        time.sleep(1)
        if check_backend():
            print(f"   后端就绪 ({i+1}s)")
            return True

    print("   后端启动超时")
    return False


def run_test_agent() -> dict | None:
    """运行测试 Agent"""
    print("\n" + "=" * 60)
    print(f"🧪 测试 Agent")
    print("=" * 60)

    result = subprocess.run(
        ["python", "test_agent.py"],
        cwd=str(PROJECT_DIR),
        capture_output=True, text=True, timeout=120,
        encoding='utf-8', errors='replace'
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    # 找最新 JSON 报告
    reports = list(PROJECT_DIR.glob("test_report_*.json"))
    if not reports:
        return None

    latest = max(reports, key=lambda p: p.stat().st_mtime)
    with open(latest, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_auto_fix() -> dict | None:
    """运行 Auto Fix Agent"""
    print("\n" + "=" * 60)
    print("🔧 Auto Fix Agent")
    print("=" * 60)

    result = subprocess.run(
        ["python", "auto_fix.py"],
        cwd=str(PROJECT_DIR),
        capture_output=True, text=True, timeout=120,
        encoding='utf-8', errors='replace'
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    # 找最新修复报告
    reports = list(PROJECT_DIR.glob("fix_report_*.json"))
    if not reports:
        return None

    latest = max(reports, key=lambda p: p.stat().st_mtime)
    with open(latest, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── 主循环 ─────────────────────────────────────────────

def main():
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║         测试-修复 闭环系统（LLM 自动修复）                ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"目标通过率: {TARGET_PASS_RATE}%")
    print(f"最大修复轮数: {MAX_ROUNDS}")

    # 检查后端
    if not check_backend():
        print("\n❌ 后端未运行，正在启动...")
        if not restart_backend():
            print("后端启动失败，请手动启动: cd backend && python main.py")
            return

    pass_rates = []

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'=' * 60}")
        print(f"第 {round_num} 轮")
        print(f"{'=' * 60}")

        # 测试
        report = run_test_agent()
        if not report:
            print("\n❌ 测试失败")
            break

        pass_rate = report.get('pass_rate', 0)
        failed = report.get('failed', 0)
        total = report.get('total', 0)
        pass_rates.append(pass_rate)

        print(f"\n📊 通过率: {pass_rate}% ({total - failed}/{total})")

        if pass_rate >= TARGET_PASS_RATE:
            print(f"\n🎉 达到目标 {TARGET_PASS_RATE}%！")
            break

        if failed == 0:
            print(f"\n🎉 全部通过！")
            break

        # 修复
        fix_result = run_auto_fix()

        if not fix_result or not fix_result.get('patches_applied', 0):
            print(f"\n️  无法自动修复，剩余 {failed} 个问题需人工处理")
            break

        # 重启后端
        if not restart_backend():
            print("\n❌ 后端重启失败")
            break

    # 总结
    print(f"\n{'=' * 60}")
    print("闭环总结")
    print(f"{'=' * 60}")
    for i, rate in enumerate(pass_rates, 1):
        marker = "✅" if rate >= TARGET_PASS_RATE else "❌"
        print(f"  第 {i} 轮: {rate}% {marker}")

    final_rate = pass_rates[-1] if pass_rates else 0
    print(f"\n最终通过率: {final_rate}%")


if __name__ == "__main__":
    main()
