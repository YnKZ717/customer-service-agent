"""测试 Agent — 自动评估主 Agent 回答质量"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import json
from datetime import datetime


# ── 配置 ─────────────────────────────────────────────

API_BASE = "http://localhost:8001"


def get_token():
    """获取 JWT Token"""
    r = requests.post(f"{API_BASE}/api/auth/login", json={
        'username': 'user',
        'password': 'user123'
    })
    return r.json()['token']


# ── 测试用例 ─────────────────────────────────────────────

TEST_CASES = [
    # FAQ 命中测试
    {
        "id": "faq_1",
        "question": "怎么充值积分",
        "expected_kb": True,
        "expected_keywords": ["支付宝", "微信", "礼品卡"],
        "description": "充值 FAQ 应命中知识库"
    },
    {
        "id": "faq_2",
        "question": "会员订阅积分什么时候到账",
        "expected_kb": True,
        "expected_keywords": ["立即发放", "24小时"],
        "description": "积分到账 FAQ 应命中知识库"
    },
    {
        "id": "faq_3",
        "question": "v3和v8模型有什么区别",
        "expected_kb": True,
        "expected_keywords": ["v3", "v8", "速度"],
        "description": "模型区别 FAQ 应命中知识库"
    },

    # 排查流程测试
    {
        "id": "troubleshoot_1",
        "question": "视频生成失败了",
        "expected_troubleshoot": True,
        "expected_keywords": ["报错", "截图"],
        "description": "应进入排查流程，追问报错信息"
    },
    {
        "id": "troubleshoot_2",
        "question": "图片生成不出来",
        "expected_troubleshoot": True,
        "expected_keywords": ["报错", "截图"],
        "description": "应进入排查流程"
    },
    {
        "id": "troubleshoot_3",
        "question": "等了很久了太慢了",
        "expected_troubleshoot": True,
        "expected_keywords": ["任务", "多久"],
        "description": "应进入超时排查流程"
    },

    # 工具调用测试（通过日志验证）
    {
        "id": "tool_1",
        "question": "TaskID 是 8078e05dfc514a299c7b40d37e61fa0f",
        "history": [
            ["user", "视频生成失败了"],
            ["assistant", " 故障排查中（第 1 步）\n请问有报错提示吗？可以把错误信息或截图发给我，我帮你看看是什么问题。"]
        ],
        "expected_tool": "check_task_status",
        "expected_keywords": ["失败", "版权"],
        "description": "应调用 check_task_status 工具"
    },

    # 自动工单测试
    {
        "id": "auto_ticket",
        "question": "Failed: 生成视频涉及版权限制 TaskID: 8078e05dfc514a299c7b40d37e61fa0f",
        "expected_auto_ticket": True,
        "description": "应自动创建工单"
    },

    # 普通问题测试
    {
        "id": "general_1",
        "question": "Neowow是Midjourney的官网吗",
        "expected_kb": True,
        "expected_keywords": ["不是", "独立"],
        "description": "应命中知识库"
    },
]


def run_test(case, token):
    """运行单个测试用例"""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    r = requests.post(f"{API_BASE}/api/chat", headers=headers, json={
        'user_input': case['question'],
        'history': case.get('history', [])
    })

    if r.status_code != 200:
        return {
            **case,
            'pass': False,
            'error': f"HTTP {r.status_code}",
            'response': ''
        }

    data = r.json()
    response = data.get('response', '')
    issues = []

    # 检查知识库命中
    if case.get('expected_kb'):
        if not data.get('kb_found'):
            issues.append("期望命中知识库但未命中")

    # 检查排查流程
    if case.get('expected_troubleshoot'):
        if not data.get('is_troubleshooting'):
            issues.append("期望进入排查流程但未进入")

    # 检查自动工单
    if case.get('expected_auto_ticket'):
        if not data.get('ticket_id'):
            issues.append("期望自动创建工单但未创建")

    # 检查关键词
    for kw in case.get('expected_keywords', []):
        if kw not in response:
            issues.append(f"回答中缺少关键词: {kw}")

    # 工具调用检查（通过回答内容判断）
    if case.get('expected_tool'):
        if data.get('is_troubleshooting') and "查询" in response:
            pass  # 通过
        else:
            issues.append(f"工具调用可能未触发：{case['expected_tool']}")

    return {
        **case,
        'pass': len(issues) == 0,
        'issues': issues,
        'response': response[:100],
        'kb_found': data.get('kb_found'),
        'is_troubleshooting': data.get('is_troubleshooting'),
        'ticket_id': data.get('ticket_id'),
    }


def generate_report(results):
    """生成测试报告"""
    total = len(results)
    passed = sum(1 for r in results if r['pass'])
    failed = total - passed

    report = f"""
╔═══════════════════════════════════════════════════════════╗
║              测试 Agent 报告                               ║
╚═══════════════════════════════════════════════════════════╝

测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
测试总数：{total}
通过：{passed} ✅
失败：{failed} ❌
通过率：{passed/total*100:.1f}%

"""

    # 失败的用例
    failed_cases = [r for r in results if not r['pass']]
    if failed_cases:
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += "失败用例：\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for r in failed_cases:
            report += f"❌ {r['id']}: {r['description']}\n"
            report += f"   问题：{r['question']}\n"
            report += f"   期望：kb={r.get('expected_kb')}, troubleshoot={r.get('expected_troubleshoot')}\n"
            report += f"   实际：kb={r['kb_found']}, troubleshoot={r['is_troubleshooting']}\n"
            report += f"   回答：{r['response'][:80]}...\n"
            report += f"   问题：\n"
            for issue in r['issues']:
                report += f"     - {issue}\n"
            report += "\n"

    # 通过的用例
    passed_cases = [r for r in results if r['pass']]
    if passed_cases:
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += "通过用例：\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for r in passed_cases:
            report += f"✅ {r['id']}: {r['description']}\n"

    # 建议
    report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    report += "修复建议：\n"
    report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if failed > 0:
        report += "1. 检查失败的 FAQ 是否在 approved_faqs.json 中\n"
        report += "2. 检查排查触发词是否覆盖用户表述\n"
        report += "3. 检查工具调用条件是否正确\n"
    else:
        report += "所有测试通过！可以考虑增加更多边界测试用例。\n"

    return report


def main():
    print("=" * 60)
    print("测试 Agent 启动")
    print("=" * 60)

    # 获取 Token
    print("\n[1/3] 获取 Token...")
    try:
        token = get_token()
        print(f"   Token: {token[:20]}...")
    except Exception as e:
        print(f"   错误：{e}")
        print("   提示：确保后端已启动")
        return

    # 运行测试
    print(f"\n[2/3] 运行测试（共 {len(TEST_CASES)} 条）...")
    results = []
    for i, case in enumerate(TEST_CASES, 1):
        print(f"   [{i}/{len(TEST_CASES)}] {case['id']}: {case['description']}")
        result = run_test(case, token)
        results.append(result)
        status = "✅" if result['pass'] else "❌"
        print(f"      {status}")

    # 生成报告
    print(f"\n[3/3] 生成报告...")
    report = generate_report(results)

    # 输出报告
    print(report)

    # 保存报告
    report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"报告已保存：{report_file}")


if __name__ == "__main__":
    main()
