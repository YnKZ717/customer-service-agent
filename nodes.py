"""节点定义 — 客服Agent的每个处理步骤"""
from tools_vector import search_knowledge_base, save_pending_faq, FAQ_DATA
from tools_chunk import search_chunks
from ticket_utils import create_ticket, transfer_to_human
from troubleshoot_flows import (
    match_flow, get_flow, get_step, match_branch,
    get_solution, get_kb_context, TROUBLESHOOT_FLOWS,
)
from mock_tools import check_task_status, check_credits_balance, check_member_status
from agent_logger import (
    log_flow_start, log_kb_lookup, log_tool_call,
    log_branch_match, log_response, log_error, log_step,
)
from openai import OpenAI
from config import LLM_CONFIG, FALLBACK_MODELS
from i18n import t
import re

# 初始化大模型客户端（主模型）
client = OpenAI(
    api_key=LLM_CONFIG["api_key"],
    base_url=LLM_CONFIG["base_url"],
)

# 初始化备用模型客户端
fallback_clients = []
for fm in FALLBACK_MODELS:
    if fm["api_key"] and fm["base_url"]:
        fallback_clients.append(OpenAI(api_key=fm["api_key"], base_url=fm["base_url"]))


# ── 意图关键词映射（与知识库对齐）──────────────────────────
INTENT_KEYWORDS = {
    # 账户相关
    "account":      ["注册", "登录", "账号", "密码", "注销", "换绑"],

    # 计费相关
    "billing":      ["充值", "积分", "付费", "支付", "扫码", "余额", "套餐"],

    # 套餐服务
    "codingplan":   ["CodingPlan", "套餐", "额度", "Credits", "会员", "权益", "VIP"],

    # 智能体使用
    "agent_service":["智能体", "对话", "创作", "云端服务", "试用"],

    # 桌面客户端
    "desktop":      ["客户端", "桌面", "下载", "安装"],

    # 应用市场
    "app_market":   ["应用市场", "购买应用", "上传应用", "预览"],

    # 技能市场
    "skill_market": ["技能市场", "技能", "同步", "收藏"],

    # 部署 Token
    "deploy_token": ["部署Token", "CI/CD", "发布"],

    # 数据备份
    "backup":       ["备份", "数据", "记录", "云端"],

    # 投诉反馈
    "complaint":    ["投诉", "不满意", "差评"],

    # 转人工
    "human":        ["人工", "转人工", "客服"],

    # 故障排查
    "troubleshoot": ["失败", "报错", "错误", "不行", "有问题", "异常", "卡住", "没反应",
                    "生成失败", "无法生成", "不能用", "坏了"],

    # 任务状态查询
    "task_status":  ["任务", "进度", "好了吗", "完成了吗", "还要多久", "状态"],

    # 操作指导
    "howto":        ["怎么用", "怎么做", "如何使用", "教程", "指南", "步骤"],
}

# ── 三层 system prompt 组装 ──
SYSTEM_PROMPT_STABLE = """你是 Neowow Studio 的智能客服助手。Neowow 是一站式智能创意内容生产与协作平台。

## 回答风格
- 简洁、直接、有条理，用编号或分点说明
- 语气友好但不随意，不要用"老板"等称呼
- 不要加 emoji
- 不要用"哈""呢""啦"等语气词
- 保持一定的 AI 客服特征，不需要伪装成真人

## 回答规则
1. 优先用知识库内容回答，确保准确
2. 知识库没有的，用你的理解回答
3. 完全不知道的问题，诚实说"这个我暂时无法确认，建议联系人工客服"
4. 涉及充值、账号安全等敏感操作，提醒用户通过官方渠道
5. 需要排查或申请豁免时，引导用户点击「转人工客服」按钮提交工单，在工单中附上 TaskID/画布链接等信息
6. Agent 本身无法直接提交工单或处理豁免，需要人工客服介入

## 重要概念区分
- 版权限制：内容涉及知名IP、品牌logo等，属于火山引擎统一拦截，不是平台单独设置。可以建议用户调整提示词或联系客服申请豁免
- 敏感内容拦截：提示词包含暴力、色情、政治等敏感信息被拒。如果是误伤可以联系客服申请豁免
- 这两者是不同的机制，不要混淆

## 能力边界
- 能回答：Neowow 平台功能、套餐、操作指南、常见问题
- 不能回答：第三方平台（如火山引擎/抖音）的具体技术问题
- 不要说"这不归我管"，给出替代方案

## 禁止行为
- 不要说"我们不提供XX服务"
- 不要说"建议您联系XX官方"
- 不要编造平台没有的功能"""

SYSTEM_PROMPT_MEMORY_TEMPLATE = """对话历史（最近{count}轮）：
{history}
（根据历史判断用户是老用户还是新用户，保持回答连贯性）"""

SYSTEM_PROMPT_TASK_TEMPLATE = """知识库参考（可能相关，但不一定完全匹配）：
{kb_context}
（如果以上内容与用户问题相关，优先参考；如果无关，忽略）"""


def build_system_prompt(history: list, kb_context: str = None) -> str:
    """动态组装三层 system prompt"""
    layers = [SYSTEM_PROMPT_STABLE]

    # 记忆层：用户历史
    if history:
        recent = history[-6:]  # 最近3轮
        history_text = "\n".join([
            f"  {'用户' if r == 'user' else '客服'}：{c}"
            for r, c in recent
        ])
        memory_layer = SYSTEM_PROMPT_MEMORY_TEMPLATE.format(
            count=len(recent),
            history=history_text
        )
        layers.append(memory_layer)

    # 任务层：知识库参考
    if kb_context:
        task_layer = SYSTEM_PROMPT_TASK_TEMPLATE.format(kb_context=kb_context)
        layers.append(task_layer)

    return "\n\n".join(layers)


def classify_intent(state: dict) -> dict:
    """节点1：意图识别 — 判断用户问题类型"""
    user_input = state["user_input"]

    # 如果已经预设了 intent（如多轮排查恢复），直接使用
    if state.get("intent"):
        return {"intent": state["intent"], "user_input": user_input}

    # 优先检查是否匹配排查流程（在常规关键词之前）
    if match_flow(user_input):
        return {"intent": "troubleshoot", "user_input": user_input}

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(k in user_input for k in keywords):
            return {"intent": intent, "user_input": user_input}

    # 没匹配到任何关键词 → 通用问题
    return {"intent": "general", "user_input": user_input}


def answer_from_kb(state: dict) -> dict:
    """节点2：知识库回答 — 先查知识库，不管意图是什么"""
    query = state.get("user_input", "")

    if not query or not isinstance(query, str):
        return {"kb_found": False, "intent": state.get("intent", "general"), "kb_reference": ""}

    # 查知识库，获取精确匹配和相关参考（返回4值：question, answer, reference, images）
    question, answer, reference, images = search_knowledge_base(query, threshold=0.65, return_reference=True)

    if answer is None:
        # 知识库里没有精确匹配，但可能有相关参考
        return {
            "kb_found": False,
            "intent": state["intent"],
            "user_input": state["user_input"],
            "kb_reference": reference,  # 传给大模型作为参考
        }

    result = {
        "response": answer,
        "intent": state["intent"],
        "kb_category": question or "未匹配",
        "kb_found": True,
        "kb_reference": "",
    }
    if images:
        result["kb_images"] = images
    log_step("kb_answer", user_input=query[:50], kb_category=question or "未匹配", response=answer[:100])
    print(f"[主Agent] kb_answer | 问题：{query[:30]}...")
    print(f"[主Agent] 知识库命中：{question or "未匹配"}")
    print(f"[主Agent] 回答：{answer[:50]}...")
    return result


def chunk_search_node(state: dict) -> dict:
    """节点3：Chunk搜索 — FAQ没找到时，搜文档片段"""
    query = state.get("user_input", "")

    if not query or not isinstance(query, str):
        return {"chunk_found": False, "intent": state.get("intent", "general"), "chunk_reference": ""}

    # 搜索chunk片段
    chunks = search_chunks(query, top_k=2, threshold=0.5)

    if chunks:
        # 把片段拼成参考文本
        chunk_text = "\n\n".join([f"[文档片段{i+1}]：{c}" for i, c in enumerate(chunks)])
        return {
            "chunk_found": True,
            "chunk_reference": chunk_text,
            "intent": state["intent"],
        }
    else:
        return {
            "chunk_found": False,
            "chunk_reference": "",
            "intent": state["intent"],
        }


def handle_human(state: dict) -> dict:
    """节点3：转人工 — 创建真实工单"""
    user_input = state["user_input"]
    history = state.get("history", [])

    ticket = create_ticket(user_input, history)
    return {
        "response": t("ticket_created", ticket_id=ticket['ticket_id']),
        "ticket_id": ticket['ticket_id'],
        "intent": state["intent"],
    }


def troubleshoot(state: dict) -> dict:
    """故障排查节点 — 结构化决策树 + LLM引导 + 知识库增强 + 工具调用"""
    import json
    user_input = state["user_input"]
    history = state.get("history", [])
    prev_flow = state.get("troubleshoot_flow", "")
    prev_step_idx = state.get("troubleshoot_step", 0)

    #  1. 匹配或复用排查流程 ──
    if prev_flow and prev_flow != "resumed":
        flow_id = prev_flow
    elif prev_flow == "resumed":
        # 从历史第一条用户消息推断流程
        flow_id = None
        for role, content in history:
            if role == "user":
                flow_id = match_flow(content)
                break
    else:
        flow_id = match_flow(user_input)

    if not flow_id:
        log_error("flow_match", "无法匹配排查流程", {"user_input": user_input[:50]})
        return {"response": "请问具体遇到了什么问题？可以描述一下现象或发截图，我帮你排查。", "intent": "troubleshoot"}

    log_flow_start(flow_id, user_input)

    flow = get_flow(flow_id)
    if not flow:
        log_error("flow_not_found", f"流程 {flow_id} 不存在")
        return {"response": "暂时无法处理这个问题，请点击「转人工客服」联系处理。", "intent": "troubleshoot"}

    # ── 2. 查知识库注入上下文 ──
    kb_context = get_kb_context(flow, FAQ_DATA)
    kb_categories = flow.get("kb_categories", [])
    log_kb_lookup(kb_categories, len(kb_context.split("\n\n")) if kb_context else 0)

    # ── 3. 提取用户输入中的关键信息（TaskID等）──
    extracted_info = _extract_info_from_input(user_input)
    tool_results = []

    # 如果用户提供了 TaskID，自动查询任务状态
    if extracted_info.get("task_id"):
        task_result = check_task_status(extracted_info["task_id"])
        log_tool_call("check_task_status", {"task_id": extracted_info["task_id"]}, task_result)
        tool_results.append(("task_status", task_result))

    # 如果用户提到积分/余额，查询积分
    if any(kw in user_input for kw in ["积分", "余额", "扣费"]):
        credits_result = check_credits_balance()
        log_tool_call("check_credits_balance", {}, credits_result)
        tool_results.append(("credits", credits_result))

    # 如果用户提到会员，查询会员状态
    if any(kw in user_input for kw in ["会员", "到期", "续费"]):
        member_result = check_member_status()
        log_tool_call("check_member_status", {}, member_result)
        tool_results.append(("member", member_result))

    # ─ 4. 确定当前步骤 ──
    if not prev_flow:
        # 首轮：直接问第一步
        current_step = get_step(flow, "step0")
        current_step_idx = 0
    else:
        # 继续对话：根据用户回答匹配上一轮的分支
        prev_step = get_step(flow, f"step{prev_step_idx}")
        if prev_step:
            next_id = match_branch(prev_step, user_input)
            log_branch_match(f"step{prev_step_idx}", user_input, next_id)
        else:
            next_id = "done"

        # 判断下一步是解决方案还是新步骤
        if next_id == "done":
            # 排查结束，建议转工单
            log_response(prev_step_idx + 1, "建议转工单", is_final=True)
            return {
                "response": (
                    "如果问题仍未解决，建议点击「转人工客服」提交工单。\n"
                    "请在工单中附上 TaskID 和画布浏览器地址，客服会尽快帮你排查。"
                ),
                "intent": "troubleshoot",
                "troubleshoot_flow": flow_id,
                "troubleshoot_step": flow["max_steps"],
            }
        elif next_id in flow.get("solutions", {}):
            # 匹配到解决方案
            solution = get_solution(flow, next_id)
            is_final = prev_step_idx + 1 >= flow["max_steps"]

            # 如果有工具查询结果，注入到回复中
            if tool_results:
                solution = _inject_tool_results(solution, tool_results)

            log_response(prev_step_idx + 1, solution[:50], is_final=is_final)

            result = {
                "response": solution,
                "intent": "troubleshoot",
                "troubleshoot_flow": flow_id,
                "troubleshoot_step": prev_step_idx + 1,
            }
            if is_final:
                result["response"] += "\n\n如以上方法未能解决，请点击「转人工客服」提交工单，附上 TaskID，客服会帮你处理。"
            return result
        else:
            # 进入下一步骤
            current_step = get_step(flow, next_id)
            current_step_idx = prev_step_idx + 1

    # ── 5. 构建 LLM prompt（带决策树约束 + 工具结果）──
    flow_structure = _format_flow_structure(flow)

    # 构建工具结果上下文
    tool_context = ""
    if tool_results:
        tool_context = "\n\n## 已查询到的信息\n"
        for tool_name, tool_result in tool_results:
            tool_context += f"- {tool_name}: {json.dumps(tool_result, ensure_ascii=False)}\n"

    troubleshoot_prompt = f"""你是 Neowow 平台的技术支持，正在通过结构化流程引导用户排查问题。

## 当前排查流程
{flow_structure}

## 知识库参考（与当前问题相关的FAQ）
{kb_context if kb_context else "（暂无相关FAQ）"}
{tool_context}

## 回答规则
- 简洁、直接、有条理，用编号或分点说明
- 不要加emoji，不要用"哈""呢""啦"等语气词
- 保持AI客服特征，不需要伪装成真人
- 当前应该问的问题是："{current_step['question'] if current_step else '建议转人工客服'}"
- 根据用户回答判断下一步，严格按照流程走
- 如果已查询到任务状态/积分/会员信息，在回答中引用这些数据
- 如果问题已解决，给出解决方案
- 如果排查步数已达上限({flow['max_steps']}步)，主动建议点击「转人工客服」提交工单"""

    messages = [{"role": "system", "content": troubleshoot_prompt}]

    # 添加最近对话历史
    for role, content in history[-8:]:
        messages.append({"role": "user" if role == "user" else "assistant", "content": content})

    messages.append({"role": "user", "content": user_input})

    # ── 6. 调用 LLM ──
    reply = _call_llm(messages)

    log_response(current_step_idx, reply[:50])

    return {
        "response": reply,
        "intent": "troubleshoot",
        "troubleshoot_flow": flow_id,
        "troubleshoot_step": current_step_idx,
    }


def _extract_info_from_input(text: str) -> dict:
    """从用户输入中提取关键信息（TaskID等）"""
    import re
    info = {}

    # 提取 TaskID（32位十六进制）
    task_match = re.search(r'[a-f0-9]{32}', text.lower())
    if task_match:
        info["task_id"] = task_match.group(0)

    return info


def _inject_tool_results(solution: str, tool_results: list) -> str:
    """将工具查询结果注入到解决方案中"""
    import json
    for tool_name, result in tool_results:
        if tool_name == "task_status":
            status = result.get("status", "未知")
            error = result.get("error_message", "")
            if status == "failed":
                solution += f"\n\n【查询结果】您的任务状态为：失败\n【失败原因】{error}"
            elif status == "processing":
                progress = result.get("progress", 0)
                solution += f"\n\n【查询结果】您的任务正在处理中，当前进度：{progress}%"
            elif status == "completed":
                solution += "\n\n【查询结果】您的任务已完成，请查看生成结果。"
        elif tool_name == "credits":
            balance = result.get("credits_balance", 0)
            solution += f"\n\n【账户信息】当前积分余额：{balance}"
        elif tool_name == "member":
            level = result.get("member_level", "无")
            days = result.get("days_remaining", 0)
            solution += f"\n\n【会员信息】等级：{level}，剩余{days}天"

    return solution

def _format_flow_structure(flow: dict) -> str:
    """将决策树格式化为 LLM 可读的文本"""
    lines = [f"流程名称：{flow['name']}"]
    lines.append(f"最大排查步数：{flow['max_steps']}")
    lines.append("")
    for step in flow.get("steps", []):
        lines.append(f"步骤 {step['id']}: {step['question']}")
        for branch in step.get("branches", []):
            lines.append(f"  → 用户提到{branch['keywords']} → {branch['next']}")
        lines.append(f"  → 其他 → {step.get('default_next', 'done')}")
        lines.append("")
    return "\n".join(lines)


def _call_llm(messages: list) -> str:
    """调用 LLM（主模型 + 自动重试 + 备用模型降级）"""
    reply = None

    for attempt in range(2):
        try:
            if attempt == 1:
                print("[自动重试] 主模型第 2 次尝试...")
            response = client.chat.completions.create(
                model=LLM_CONFIG["model_name"],
                messages=messages,
                max_tokens=600,
                temperature=0.3,
            )
            reply = response.choices[0].message.content
            break
        except Exception as e:
            print(f"[模型降级] 主模型第{attempt+1}次失败：{str(e)[:60]}")
            if attempt == 0:
                continue

    if reply is None:
        print("[模型降级] 主模型重试失败，切换备用模型...")
        for i, fb_client in enumerate(fallback_clients):
            fm = FALLBACK_MODELS[i]
            try:
                print(f"[模型降级] 切换到备用模型 {fm['model_name']}...")
                response = fb_client.chat.completions.create(
                    model=fm["model_name"],
                    messages=messages,
                    max_tokens=600,
                    temperature=0.3,
                )
                reply = response.choices[0].message.content
                break
            except Exception:
                continue

    if reply is None:
        reply = "抱歉，系统暂时繁忙，请稍后再试。如需紧急帮助，请点击「转人工客服」。"

    return reply


def general_reply(state: dict) -> dict:
    """节点5：通用回复 — 大模型兜底，使用三层 system prompt"""
    user_input = state["user_input"]
    history = state.get("history", [])
    kb_reference = state.get("kb_reference", "")
    chunk_reference = state.get("chunk_reference", "")

    # 合并参考内容
    all_reference = ""
    if kb_reference:
        all_reference += "【FAQ参考】\n" + kb_reference + "\n\n"
    if chunk_reference:
        all_reference += "【文档片段参考】\n" + chunk_reference

    # 组装三层 system prompt
    system_prompt = build_system_prompt(history, all_reference if all_reference else None)

    # 构建消息
    messages = [{"role": "system", "content": system_prompt}]
    for role, content in history[-6:]:
        messages.append({"role": "user" if role == "user" else "assistant", "content": content})
    messages.append({"role": "user", "content": user_input})

    reply = None

    # 主模型调用（失败自动重试 1 次）
    for attempt in range(2):
        try:
            if attempt == 1:
                print("[自动重试] 主模型第 2 次尝试...")
            response = client.chat.completions.create(
                model=LLM_CONFIG["model_name"],
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )
            reply = response.choices[0].message.content
            break
        except Exception as e:
            print(f"[模型降级] 主模型第{attempt+1}次失败：{str(e)[:60]}")
            if attempt == 0:
                continue  # 重试一次

    # 主模型彻底失败，尝试备用模型
    if reply is None:
        print("[模型降级] 主模型重试失败，切换备用模型...")
        for i, fb_client in enumerate(fallback_clients):
            fm = FALLBACK_MODELS[i]
            try:
                print(f"[模型降级] 切换到备用模型 {fm['model_name']}...")
                response = fb_client.chat.completions.create(
                    model=fm["model_name"],
                    messages=messages,
                    max_tokens=500,
                    temperature=0.7,
                )
                reply = response.choices[0].message.content
                print("[模型降级] 备用模型成功")
                break
            except Exception as e2:
                print(f"[模型降级] 备用模型 {i+1} 也失败：{str(e2)[:50]}")
                continue

    if reply is None:
        reply = t("service_unavailable")

    # 沉淀：新问题自动记录（只沉淀有实质内容的回答）
    if reply and not reply.startswith("系统暂时繁忙") and not reply.startswith("Service temporarily") and not reply.startswith("抱歉"):
        save_pending_faq(user_input, reply, history)

    log_step("general_reply", user_input=user_input[:50], response=reply[:100], intent="general")
    print(f"[主Agent] general_reply | 问题：{user_input[:30]}...")
    print(f"[主Agent] 回答：{reply[:50]}...")
    return {"response": reply, "intent": "general"}


def evaluate_response(state: dict) -> dict:
    """副Agent节点：分维度评估并修正主Agent的回答"""
    user_input = state["user_input"]
    response = state.get("response", "")
    intent = state.get("intent", "general")
    kb_reference = state.get("kb_reference", "")
    chunk_reference = state.get("chunk_reference", "")

    # 只评估没有知识库参考的通用回复
    if intent in ("troubleshoot", "human"):
        return {"response": response, "intent": intent}
    # 有知识库或 Chunk 参考时，回答有依据，不需要副Agent检查
    kb_ref = state.get("kb_reference", "")
    chunk_ref = state.get("chunk_reference", "")
    if kb_ref or chunk_ref:
        return {"response": response, "intent": intent}

    if not response:
        return state

    # 合并参考内容作为评判依据
    all_reference = ""
    if kb_reference:
        all_reference += "【FAQ参考】
" + kb_reference + "

"
    if chunk_reference:
        all_reference += "【文档片段参考】
" + chunk_reference

    # 评分阈值：低于此分数需要修正
    ACCURACY_THRESHOLD = 3
    COMPLETENESS_THRESHOLD = 3
    TONE_THRESHOLD = 3
    SAFETY_THRESHOLD = 4  # 安全要求更严格

    eval_prompt = f"""你是 Neowow 智能客服的质量审核员。请对以下客服回答进行分维度评分（1-5分），并决定是否需要修正。

## 用户问题
{user_input}

## 客服回答
{response}

{all_reference if all_reference else "（暂无知识库参考）"}

## 评分标准（1-5分）
1. 准确性：回答是否与产品事实一致，有没有编造信息
2. 完整性：是否遗漏了用户问题的关键部分
3. 语气：是否简洁专业、没有emoji、没有"哈/呢/啦"等语气词
4. 安全：是否暴露了内部信息或给出了错误操作指引

## 输出格式
先输出各维度分数，然后输出 PASS 或 FIXED：
SCORES: 准确性=X, 完整性=X, 语气=X, 安全=X
PASS

或者（如果有任一维度低于阈值：准确性<3, 完整性<3, 语气<3, 安全<4）：
SCORES: 准确性=X, 完整性=X, 语气=X, 安全=X
FIXED: <修正后的完整回答>
"""

    messages = [{"role": "user", "content": eval_prompt}]

    reply = None
    for attempt in range(2):
        try:
            fb_client = None
            for fm in FALLBACK_MODELS:
                if fm["api_key"] and fm["base_url"]:
                    fb_client = OpenAI(api_key=fm["api_key"], base_url=fm["base_url"])
                    break

            eval_client = fb_client if fb_client else client
            eval_model = FALLBACK_MODELS[0]["model_name"] if fb_client else LLM_CONFIG["model_name"]

            resp = eval_client.chat.completions.create(
                model=eval_model,
                messages=messages,
                max_tokens=500,
                temperature=0.1,
            )
            reply = resp.choices[0].message.content.strip()
            break
        except Exception as e:
            if attempt == 0:
                continue

    if not reply:
        return state

    # 解析评分结果
    import re
    scores_match = re.search(r'SCORES:\s*准确性=(\d),\s*完整性=(\d),\s*语气=(\d),\s*安全=(\d)', reply)

    if scores_match:
        accuracy = int(scores_match.group(1))
        completeness = int(scores_match.group(2))
        tone = int(scores_match.group(3))
        safety = int(scores_match.group(4))

        # 判断是否需要修正
        need_fix = (
            accuracy < ACCURACY_THRESHOLD or
            completeness < COMPLETENESS_THRESHOLD or
            tone < TONE_THRESHOLD or
            safety < SAFETY_THRESHOLD
        )

        if not need_fix:
            log_step("evaluate", result="PASS",
                     accuracy=accuracy, completeness=completeness,
                     tone=tone, safety=safety, user_input=user_input[:50])
            print(f"[副Agent] PASS | 准确性={accuracy} 完整性={completeness} 语气={tone} 安全={safety} | 问题：{user_input[:30]}...")
            return state

    # 检查是否有 FIXED
    if reply.startswith("FIXED:"):
        fixed = reply[6:].strip()
        log_step("evaluate", result="FIXED", fixed_response=fixed[:100], user_input=user_input[:50])
        print(f"[副Agent] FIXED | 问题：{user_input[:30]}...")
        print(f"[副Agent] 修正：{fixed[:50]}...")
        return {"response": fixed, "intent": intent}

    # 如果 LLM 没按格式输出，保守起见保留原回答
    log_step("evaluate", result="UNKNOWN", reply=reply[:100], user_input=user_input[:50])
    print(f"[副Agent] 未知格式 | 回答：{reply[:50]}...")
    return state

