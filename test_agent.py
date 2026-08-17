"""测试 Agent — 自动评估主 Agent 回答质量 + 输出修复建议"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import json
from datetime import datetime


# ── 配置 ─────────────────────────────────────────────

API_BASE = "http://localhost:8001"

# ─ 失败类型到修复模块的映射 ─────────────────────────────

FIX_RULES = {
    "kb_miss": {
        "module": "tools_vector.py / approved_faqs.json",
        "fix_direction": "检查 FAQ 是否在 approved_faqs.json 中，或关键词权重不足",
        "fix_actions": [
            "确认问题对应的FAQ条目存在于 approved_faqs.json",
            "检查 FAQ 的 category 是否与 INTENT_KEYWORDS 对齐",
            "检查 search_knowledge_base 的 threshold 是否过高（当前0.65）",
            "考虑添加更多相似问法到 FAQ",
        ],
    },
    "troubleshoot_miss": {
        "module": "troubleshoot_flows.py",
        "fix_direction": "排查流程触发词未覆盖用户表述",
        "fix_actions": [
            "在 TROUBLESHOOT_FLOWS 对应流程的 triggers 中添加用户用词",
            "检查 match_flow() 的匹配逻辑是否合理",
            "检查 classify_intent() 中 match_flow() 的调用优先级",
        ],
    },
    "branch_miss": {
        "module": "troubleshoot_flows.py",
        "fix_direction": "决策树分支关键词未匹配用户回答",
        "fix_actions": [
            "在对应 step 的 branches 中添加更多关键词",
            "检查 match_branch() 的匹配顺序",
            "考虑调整 default_next 的指向",
        ],
    },
    "keyword_miss": {
        "module": "nodes.py / troubleshoot_flows.py",
        "fix_direction": "回答中缺少预期关键词，可能是 system prompt 或解决方案文本问题",
        "fix_actions": [
            "检查对应 solution 文本是否包含预期关键词",
            "检查 system prompt 是否限制了回答风格导致关键词被省略",
            "检查 LLM temperature 是否过高导致回答不稳定",
        ],
    },
    "tool_miss": {
        "module": "nodes.py",
        "fix_direction": "工具调用条件未触发",
        "fix_actions": [
            "检查 troubleshoot() 中工具调用的触发条件",
            "检查 _extract_info_from_input() 的 TaskID 正则是否匹配",
            "检查工具结果是否正确注入到回复中",
        ],
    },
    "auto_ticket_miss": {
        "module": "backend/main.py",
        "fix_direction": "自动工单创建逻辑未触发",
        "fix_actions": [
            "检查 extract_error_ids() 的正则是否匹配用户输入",
            "检查 is_copyright_error() 的判断逻辑",
            "检查 is_in_troubleshoot 条件是否阻止了自动工单",
        ],
    },
    "intent_wrong": {
        "module": "nodes.py",
        "fix_direction": "意图分类错误",
        "fix_actions": [
            "检查 INTENT_KEYWORDS 中对应意图的关键词列表",
            "检查 classify_intent() 中 match_flow() 的优先级",
            "考虑添加更多触发词到对应意图",
        ],
    },
}


def get_token():
    """获取 JWT Token"""
    r = requests.post(f"{API_BASE}/api/auth/login", json={
        'username': 'user',
        'password': 'user123'
    })
    return r.json()['token']


# ── 测试用例 ─────────────────────────────────────────────

TEST_CASES = [
    # === FAQ 命中测试 ===
    {
        "id": "faq_1",
        "question": "怎么充值积分",
        "expected_kb": True,
        "expected_keywords": ["支付宝", "微信", "礼品卡"],
        "description": "充值 FAQ 应命中知识库",
    },
    {
        "id": "faq_2",
        "question": "会员订阅积分什么时候到账",
        "expected_kb": True,
        "expected_keywords": ["立即发放", "24小时"],
        "description": "积分到账 FAQ 应命中知识库",
    },
    {
        "id": "faq_3",
        "question": "v3和v8模型有什么区别",
        "expected_kb": True,
        "expected_keywords": ["v3", "v8", "速度"],
        "description": "模型区别 FAQ 应命中知识库",
    },
    {
        "id": "faq_4",
        "question": "CodingPlan是什么",
        "expected_kb": True,
        "description": "CodingPlan FAQ 应命中知识库",
    },
    {
        "id": "faq_5",
        "question": "怎么申请退款",
        "expected_kb": True,
        "description": "退款 FAQ 应命中知识库",
    },
    {
        "id": "faq_6",
        "question": "如何上传自定义技能",
        "expected_kb": True,
        "description": "技能上传 FAQ 应命中知识库",
    },

    # === 排查流程测试 ===
    {
        "id": "troubleshoot_1",
        "question": "视频生成失败了",
        "expected_troubleshoot": True,
        "expected_keywords": ["报错", "截图"],
        "description": "应进入排查流程，追问报错信息",
    },
    {
        "id": "troubleshoot_2",
        "question": "图片生成不出来",
        "expected_troubleshoot": True,
        "expected_keywords": ["报错", "截图"],
        "description": "应进入排查流程",
    },
    {
        "id": "troubleshoot_3",
        "question": "等了很久了太慢了",
        "expected_troubleshoot": True,
        "expected_keywords": ["任务", "多久"],
        "description": "应进入超时排查流程",
    },
    {
        "id": "troubleshoot_4",
        "question": "生成效果不好不像",
        "expected_troubleshoot": True,
        "description": "应进入质量排查流程",
    },
    {
        "id": "troubleshoot_5",
        "question": "积分突然少了",
        "expected_troubleshoot": True,
        "description": "应进入账号积分排查流程",
    },

    # === 多轮排查测试 ===
    {
        "id": "multi_turn_1",
        "question": "有版权限制的报错",
        "history": [
            ["user", "视频生成失败了"],
            ["assistant", " 故障排查中（第1步）\n请问有报错提示吗？可以把错误信息或截图发给我，我帮你看看是什么问题。"],
        ],
        "expected_troubleshoot": True,
        "expected_keywords": ["版权", "提示词"],
        "description": "多轮排查：回答版权问题应命中版权解决方案",
    },
    {
        "id": "multi_turn_2",
        "question": "TaskID 是 8078e05dfc514a299c7b40d37e61fa0f",
        "history": [
            ["user", "视频生成失败了"],
            ["assistant", "🔍 故障排查中（第1步）\n请问有报错提示吗？可以把错误信息或截图发给我，我帮你看看是什么问题。"],
        ],
        "expected_troubleshoot": True,
        "description": "多轮排查：提供TaskID应调用工具查询",
    },

    # === 工具调用测试 ===
    {
        "id": "tool_1",
        "question": "TaskID 是 8078e05dfc514a299c7b40d37e61fa0f",
        "history": [
            ["user", "视频生成失败了"],
            ["assistant", "🔍 故障排查中（第1步）\n请问有报错提示吗？可以把错误信息或截图发给我，我帮你看看是什么问题。"],
        ],
        "expected_tool": "check_task_status",
        "expected_keywords": ["失败", "版权"],
        "description": "应调用 check_task_status 工具",
    },

    # === 自动工单测试 ===
    {
        "id": "auto_ticket",
        "question": "Failed: 生成视频涉及版权限制 TaskID: 8078e05dfc514a299c7b40d37e61fa0f",
        "expected_auto_ticket": True,
        "description": "应自动创建工单",
    },

    # === 普通问题测试 ===
    {
        "id": "general_1",
        "question": "Neowow是Midjourney的官网吗",
        "expected_kb": True,
        "expected_keywords": ["不是", "独立"],
        "description": "应命中知识库",
    },
    {
        "id": "general_2",
        "question": "你好",
        "expected_keywords": [],
        "description": "普通问候应正常回复",
    },
]


def analyze_failure(case, response_text, kb_found, is_troubleshoot, ticket_id):
    """分析失败原因，输出修复建议"""
    failure_types = []

    # 分析每种期望未满足的原因
    if case.get('expected_kb') and not kb_found:
        failure_types.append({
            "type": "kb_miss",
            "detail": f"问题 '{case['question']}' 未命中知识库",
            **FIX_RULES["kb_miss"],
        })

    if case.get('expected_troubleshoot') and not is_troubleshoot:
        failure_types.append({
            "type": "troubleshoot_miss",
            "detail": f"问题 '{case['question']}' 未进入排查流程",
            **FIX_RULES["troubleshoot_miss"],
        })

    if case.get('expected_auto_ticket') and not ticket_id:
        failure_types.append({
            "type": "auto_ticket_miss",
            "detail": f"问题 '{case['question']}' 未自动创建工单",
            **FIX_RULES["auto_ticket_miss"],
        })

    # 关键词缺失
    missing_kw = []
    for kw in case.get('expected_keywords', []):
        if kw not in response_text:
            missing_kw.append(kw)
    if missing_kw:
        failure_types.append({
            "type": "keyword_miss",
            "detail": f"回答缺少关键词: {', '.join(missing_kw)}",
            **FIX_RULES["keyword_miss"],
        })

    return failure_types


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
            'response': '',
            'failure_types': [],
        }

    data = r.json()
    response = data.get('response', '')
    kb_found = data.get('kb_found', False)
    is_troubleshoot = data.get('is_troubleshooting', False)
    ticket_id = data.get('ticket_id', '')
    issues = []

    # 检查知识库命中
    if case.get('expected_kb') and not kb_found:
        issues.append("期望命中知识库但未命中")

    # 检查排查流程
    if case.get('expected_troubleshoot') and not is_troubleshoot:
        issues.append("期望进入排查流程但未进入")

    # 检查自动工单
    if case.get('expected_auto_ticket') and not ticket_id:
        issues.append("期望自动创建工单但未创建")

    # 检查关键词
    for kw in case.get('expected_keywords', []):
        if kw not in response:
            issues.append(f"回答中缺少关键词: {kw}")

    # 工具调用检查
    if case.get('expected_tool'):
        if is_troubleshoot and ("查询" in response or "TaskID" in response or "任务" in response):
            pass
        else:
            issues.append(f"工具调用可能未触发：{case['expected_tool']}")

    # 分析失败原因
    failure_types = []
    if issues:
        failure_types = analyze_failure(case, response, kb_found, is_troubleshoot, ticket_id)

    return {
        **case,
        'pass': len(issues) == 0,
        'issues': issues,
        'failure_types': failure_types,
        'response': response[:100],
        'kb_found': kb_found,
        'is_troubleshooting': is_troubleshoot,
        'ticket_id': ticket_id,
    }


def generate_report(results):
    """生成测试报告（文本 + JSON）"""
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

    # 失败的用例 + 修复建议
    failed_cases = [r for r in results if not r['pass']]
    if failed_cases:
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += "失败用例 & 修复建议：\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for r in failed_cases:
            report += f" {r['id']}: {r['description']}\n"
            report += f"   问题：{r['question']}\n"
            report += f"   期望：kb={r.get('expected_kb')}, troubleshoot={r.get('expected_troubleshoot')}\n"
            report += f"   实际：kb={r['kb_found']}, troubleshoot={r['is_troubleshooting']}\n"
            report += f"   回答：{r['response'][:80]}...\n"
            report += f"   问题：\n"
            for issue in r['issues']:
                report += f"     - {issue}\n"

            # 修复建议
            if r.get('failure_types'):
                report += f"   📋 修复建议：\n"
                for ft in r['failure_types']:
                    report += f"     [{ft['type']}] 模块: {ft['module']}\n"
                    report += f"       方向: {ft['fix_direction']}\n"
                    report += f"       操作:\n"
                    for action in ft['fix_actions']:
                        report += f"         - {action}\n"
            report += "\n"

    # 通过的用例
    passed_cases = [r for r in results if r['pass']]
    if passed_cases:
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += "通过用例：\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for r in passed_cases:
            report += f"✅ {r['id']}: {r['description']}\n"

    # 修复建议汇总
    if failed_cases:
        report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += "修复优先级：\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        # 按模块汇总
        module_fixes = {}
        for r in failed_cases:
            for ft in r.get('failure_types', []):
                mod = ft['module']
                if mod not in module_fixes:
                    module_fixes[mod] = []
                module_fixes[mod].append(f"{r['id']}: {ft['detail']}")

        for mod, fixes in module_fixes.items():
            report += f"📁 {mod} ({len(fixes)} 个问题)\n"
            for f in fixes:
                report += f"   - {f}\n"
            report += "\n"

    # 生成 JSON 报告（给修复Agent用）
    json_report = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        "failed_cases": [
            {
                "id": r['id'],
                "question": r['question'],
                "issues": r['issues'],
                "failure_types": r.get('failure_types', []),
                "response_snippet": r['response'][:100],
                "kb_found": r['kb_found'],
                "is_troubleshooting": r['is_troubleshooting'],
                "ticket_id": r['ticket_id'],
            }
            for r in failed_cases
        ],
        "module_summary": {
            mod: len(fixes)
            for mod, fixes in module_fixes.items()
        } if failed_cases else {},
    }

    return report, json_report


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
    report, json_report = generate_report(results)

    # 输出报告
    print(report)

    # 保存文本报告
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = f"test_report_{ts}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"文本报告已保存：{report_file}")

    # 保存 JSON 报告（给修复Agent用）
    json_file = f"test_report_{ts}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    print(f"JSON报告已保存：{json_file}")

    return json_report


if __name__ == "__main__":
    main()
