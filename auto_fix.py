"""Auto Fix Agent — LLM 分析测试失败原因，自动生成代码补丁并应用"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from config import LLM_CONFIG, FALLBACK_MODELS

# ── 配置 ─────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent
client = OpenAI(
    api_key=LLM_CONFIG["api_key"],
    base_url=LLM_CONFIG["base_url"],
)


def load_json_report(report_path: str | None = None) -> dict:
    """加载测试 JSON 报告"""
    if report_path:
        with open(report_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    reports = list(PROJECT_DIR.glob("test_report_*.json"))
    if not reports:
        return None
    latest = max(reports, key=lambda p: p.stat().st_mtime)
    with open(latest, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── 读取要修改的文件 ──────────────────────────────────

FILES_TO_FIX = {
    "troubleshoot_flows.py": "troubleshoot_flows.py",
    "tools_vector.py": "tools_vector.py",
    "nodes.py": "nodes.py",
    "approved_faqs.json": "approved_faqs.json",
}


def read_file(filepath: str) -> str:
    full_path = PROJECT_DIR / filepath
    if not full_path.exists():
        return ""
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


# ── LLM 分析并生成补丁 ──────────────────────────────

def llm_analyze_and_fix(failed_cases: list, file_contents: dict) -> list:
    """用 LLM 分析失败原因，生成代码修改方案"""

    # 构建失败信息
    failures_text = ""
    for case in failed_cases:
        failures_text += f"\n## 失败用例: {case['id']}\n"
        failures_text += f"问题: {case['question']}\n"
        failures_text += f"期望: kb={case.get('kb_found', 'N/A')}, troubleshoot={case.get('is_troubleshooting', 'N/A')}\n"
        failures_text += f"实际回答片段: {case.get('response_snippet', '')}\n"
        for issue in case.get('issues', []):
            failures_text += f"问题: {issue}\n"

    # 构建文件内容摘要
    files_text = ""
    for name, content in file_contents.items():
        lines = content.split('\n')

        if name == "troubleshoot_flows.py":
            # 对排查流程文件，提取所有流程名和 triggers 行
            flows_info = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('"') and '":' in stripped and '{' in stripped:
                    flow_name = stripped.split('"')[1]
                    flows_info.append(f"  流程 {flow_name} (line {i+1})")
                if '"triggers"' in stripped:
                    flows_info.append(f"    triggers: {stripped[:120]}")
                if '"name"' in stripped and '"' in stripped.split('"name"')[1]:
                    name_val = stripped.split('"name"')[1].split('"')[2] if '"' in stripped.split('"name"')[1] else ""
                    flows_info[-1] += f" → {name_val}"
            files_text += f"\n### {name} (流程结构)\n" + '\n'.join(flows_info) + "\n"
        else:
            # 其他文件显示前 80 行
            preview = '\n'.join(lines[:80])
            if len(lines) > 80:
                preview += f"\n... ({len(lines) - 80} more lines)"
            files_text += f"\n### {name}\n```\n{preview}\n```\n"

    prompt = f"""你是一个代码修复专家。根据测试失败信息，分析原因并生成具体的代码修改方案。

## 测试失败信息
{failures_text}

## 相关文件内容
{files_text}

## 修复规则（必须严格遵守）

### 规则1：排查流程未触发（troubleshoot_miss）
- 文件：troubleshoot_flows.py
- 根据问题内容判断属于哪个流程：
  - 视频相关 → video_fail
  - 图片相关 → image_fail
  - 等待/太慢/卡住 → timeout
  - 质量/不像/效果不好 → quality
  - 积分/账号/会员/充值 → account_issue
- 在该流程的 triggers 列表中添加触发词（直接用用户问题作为触发词）
- 示例：问题"积分突然少了" → 在 account_issue 的 triggers 中添加 "积分突然少了"

### 规则2：知识库未命中（kb_miss）
- 文件：tools_vector.py
- 降低 search_knowledge_base 的 threshold 参数，每次降 0.05，不低于 0.3

### 规则3：关键词缺失（keyword_miss）
- 检查对应 solution 文本是否包含预期关键词
- 如果不包含，在 solution 中添加

## 输出格式
```json
[
  {{
    "file": "文件名",
    "action": "replace",
    "old_text": "要替换的原文（必须完全匹配，包括缩进）",
    "new_text": "新内容",
    "reason": "修改原因"
  }}
]
```

## 注意
- old_text 必须与文件中的内容完全匹配
- 每次只改必要的地方
- 如果无法确定，返回 []
"""

    reply = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=LLM_CONFIG["model_name"],
                messages=[{"role": "system", "content": "你是代码修复专家。"}, {"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.2,
            )
            reply = response.choices[0].message.content
            break
        except Exception as e:
            if attempt == 0:
                continue
            # 尝试备用模型
            for fm in FALLBACK_MODELS:
                try:
                    fb_client = OpenAI(api_key=fm["api_key"], base_url=fm["base_url"])
                    response = fb_client.chat.completions.create(
                        model=fm["model_name"],
                        messages=[{"role": "system", "content": "你是代码修复专家。"}, {"role": "user", "content": prompt}],
                        max_tokens=2000,
                        temperature=0.2,
                    )
                    reply = response.choices[0].message.content
                    break
                except:
                    continue

    if not reply:
        print("  LLM 调用失败")
        return []

    # 提取 JSON — 找 ```json ... ``` 块，或第一个 [...]
    json_str = None
    # 优先找 markdown 代码块
    md_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', reply, re.DOTALL)
    if md_match:
        json_str = md_match.group(1)
    else:
        # 退而求其次：找第一个 [...]
        json_match = re.search(r'\[.*\]', reply, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)

    if not json_str:
        print("  LLM 未返回有效 JSON")
        print(f"  原始输出: {reply[:200]}")
        return []

    try:
        patches = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  JSON 解析失败: {e}")
        print(f"  JSON 内容: {json_str[:200]}")
        return []

    return patches


# ── 应用补丁 ──────────────────────────────────────────

def apply_patches(patches: list) -> list:
    """应用代码补丁"""
    applied = []
    failed = []

    for patch in patches:
        filepath = PROJECT_DIR / patch["file"]
        if not filepath.exists():
            failed.append({"file": patch["file"], "reason": "文件不存在"})
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        action = patch.get("action", "replace")

        if action == "replace":
            old_text = patch.get("old_text", "")
            new_text = patch.get("new_text", "")
            if old_text and old_text in content:
                content = content.replace(old_text, new_text, 1)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                applied.append({"file": patch["file"], "reason": patch.get("reason", "")})
            else:
                failed.append({"file": patch["file"], "reason": "old_text 未找到"})

        elif action == "insert":
            # 在指定位置插入
            old_text = patch.get("old_text", "")
            new_text = patch.get("new_text", "")
            if old_text and old_text in content:
                content = content.replace(old_text, new_text + old_text, 1)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                applied.append({"file": patch["file"], "reason": patch.get("reason", "")})
            else:
                failed.append({"file": patch["file"], "reason": "insert position 未找到"})

        elif action == "append":
            # 追加到文件末尾
            new_text = patch.get("new_text", "")
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write("\n" + new_text)
            applied.append({"file": patch["file"], "reason": patch.get("reason", "")})

    return applied, failed


# ── 主流程 ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Auto Fix Agent 启动")
    print("=" * 60)

    # 加载报告
    print("\n[1/4] 加载测试报告...")
    report = load_json_report()
    if not report:
        print("❌ 未找到测试报告，请先运行 test_agent.py")
        return

    failed = report.get('failed', 0)
    total = report.get('total', 0)
    pass_rate = report.get('pass_rate', 0)
    print(f"   通过率: {pass_rate}% ({total - failed}/{total})")

    if failed == 0:
        print("\n✅ 所有测试通过，无需修复！")
        return

    failed_cases = report.get('failed_cases', [])
    print(f"   失败用例: {len(failed_cases)}")

    # 读取相关文件
    print(f"\n[2/4] 读取源文件...")
    file_contents = {}
    for name in FILES_TO_FIX:
        content = read_file(name)
        if content:
            file_contents[name] = content
            print(f"   ✅ {name} ({len(content)} chars)")

    # LLM 分析并生成补丁
    print(f"\n[3/4] LLM 分析失败原因并生成补丁...")
    patches = llm_analyze_and_fix(failed_cases, file_contents)

    if not patches:
        print("\n⚠️  LLM 未能生成修复方案")
        return

    print(f"   生成 {len(patches)} 个补丁:")
    for i, p in enumerate(patches, 1):
        print(f"   [{i}] {p['file']}: {p.get('reason', '')[:60]}")

    # 应用补丁
    print(f"\n[4/4] 应用补丁...")
    applied, failed_patches = apply_patches(patches)

    if applied:
        print(f"\n✅ 成功应用 {len(applied)} 个补丁:")
        for a in applied:
            print(f"   - {a['file']}: {a['reason']}")

    if failed_patches:
        print(f"\n❌ {len(failed_patches)} 个补丁应用失败:")
        for f in failed_patches:
            print(f"   - {f['file']}: {f['reason']}")

    # 保存修复报告
    fix_report = {
        "timestamp": datetime.now().isoformat(),
        "original_pass_rate": pass_rate,
        "patches_generated": len(patches),
        "patches_applied": len(applied),
        "patches_failed": len(failed_patches),
        "applied": applied,
        "failed": failed_patches,
    }

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = f"fix_report_{ts}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(fix_report, f, ensure_ascii=False, indent=2)

    print(f"\n修复报告已保存：{report_file}")
    print(f"\n下一步：重启后端，然后运行 python test_agent.py 验证")


if __name__ == "__main__":
    main()
