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
        return {"intent": state["intent"], "user_input": user_input, "user_memory": state.get("user_memory", {})}

    # 优先检查是否匹配排查流程（在常规关键词之前）
    if match_flow(user_input):
        return {"intent": "troubleshoot", "user_input": user_input, "user_memory": state.get("user_memory", {})}

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(k in user_input for k in keywords):
            return {"intent": intent, "user_input": user_input, "user_memory": state.get("user_memory", {})}

    # 没匹配到任何关键词 → 通用问题
    return {"intent": "general", "user_input": user_input, "user_memory": state.get("user_memory", {})}


def answer_from_kb(state: dict) -> dict:
    """节点2：知识库回答 — 先查知识库，不管意图是什么"""
    query = state.get("user_input", "")

    if not query or not isinstance(query, str):
        return {"kb_found": False, "intent": state.get("intent", "general"), "kb_reference": "", "user_memory": state.get("user_memory", {})}

    # 查知识库，获取精确匹配和相关参考（返回4值：question, answer, reference, images）
    question, answer, reference, images = search_knowledge_base(query, threshold=0.65, return_reference=True)

    if answer is None:
        # 知识库里没有精确匹配，但可能有相关参考
        return {
            "kb_found": False,
            "intent": state["intent"],
            "user_input": state["user_input"],
            "kb_reference": reference,  # 传给大模型作为参考
            "user_memory": state.get("user_memory", {}),
        }

    result = {
        "response": answer,
        "intent": state["intent"],
        "kb_category": question or "未匹配",
        "kb_found": True,
        "kb_reference": "",
        "user_memory": state.get("user_memory", {}),
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
        return {"chunk_found": False, "intent": state.get("intent", "general"), "chunk_reference": "", "user_memory": state.get("user_memory", {})}

    # 搜索chunk片段
    chunks = search_chunks(query, top_k=2, threshold=0.5)

    if chunks:
        # 把片段拼成参考文本
        chunk_text = "\n\n".join([f"[文档片段{i+1}]：{c}" for i, c in enumerate(chunks)])
        return {
            "chunk_found": True,
            "chunk_reference": chunk_text,
            "intent": state["intent"],
            "user_memory": state.get("user_memory", {}),
        }
    else:
        return {
            "chunk_found": False,
            "chunk_reference": "",
            "intent": state["intent"],
            "user_memory": state.get("user_memory", {}),
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
        "user_memory": state.get("user_memory", {}),
    }


def troubleshoot(state: dict) -> dict:
    """故障排查节点 — 结构化决策树 + LLM引导 + 知识库增强 + 工具调用"""
    import json
    user_input = state["user_input"]
    history = state.get("history", [])
    prev_flow = state.get("troubleshoot_flow", "")
    prev_step_idx = state.get("troubleshoot_step", 0)
    user_images = state.get("user_images", [])

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
        user_memory = _update_memory(state)
        return {
            "response": "请问具体遇到了什么问题？可以描述一下现象或发截图，我帮你排查。",
            "intent": "troubleshoot",
            "user_memory": user_memory,
        }

    log_flow_start(flow_id, user_input)

    flow = get_flow(flow_id)
    if not flow:
        log_error("flow_not_found", f"流程 {flow_id} 不存在")
        user_memory = _update_memory(state)
        return {
            "response": "暂时无法处理这个问题，请点击「转人工客服」联系处理。",
            "intent": "troubleshoot",
            "user_memory": user_memory,
        }

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

    # ── 3.5 更新多轮记忆 ──
    user_memory = _update_memory(state)

    # ─ 3.6 首轮有 TaskID 时，跳过 step0 直接返回查询结果 ──
    if not prev_flow and tool_results:
        # 查找任务状态查询结果
        task_result = None
        for tool_name, result in tool_results:
            if tool_name == "task_status":
                task_result = result
                break

        if task_result:
            status = task_result.get("status", "").upper()
            error = task_result.get("error_message", "")
            platform_error = task_result.get("platform_error", "")

            # 任务不存在
            if status == "NOT_FOUND":
                log_response(0, f"任务不存在: {task_result.get('task_id')}")
                return {
                    "response": f"【查询结果】{error or '未找到该任务，请检查 TaskID 是否正确'}",
                    "intent": "troubleshoot",
                    "troubleshoot_flow": "",
                    "troubleshoot_step": 0,
                    "user_memory": user_memory,
                }

            # 任务失败 — 直接给出失败原因
            if status == "FAILED":
                response = f"【查询结果】您的任务状态为：失败\n【失败原因】{error}"
                if platform_error:
                    response += f"\n【平台报错】{platform_error[:100]}"

                # 检测是否为疑似误伤
                if _is_false_positive(task_result):
                    response += "\n\n【系统判断】⚠️ 检测到可能是平台误伤（内容实际合规但被错误拦截）"
                    response += (
                        "\n\n建议：\n"
                        "1. 先尝试精简提示词，避免使用可能触发审核的词汇\n"
                        "2. 如确认内容合规，请点击「转人工客服」提交工单，附上 TaskID\n"
                        "3. 客服会向平台申请内容复核，通常 24 小时内处理"
                    )
                else:
                    response += "\n\n请根据以上信息检查并修改后重试。如仍有问题，请点击「转人工客服」提交工单。"

                log_response(0, f"任务失败: {task_result.get('task_id')}")
                return {
                    "response": response,
                    "intent": "troubleshoot",
                    "troubleshoot_flow": "",
                    "troubleshoot_step": 0,
                    "user_memory": user_memory,
                }

            # 任务处理中/排队中
            if status in ("PROCESSING", "PENDING"):
                status_text = "处理中" if status == "PROCESSING" else "排队中"
                log_response(0, f"任务{status_text}: {task_result.get('task_id')}")
                return {
                    "response": f"【查询结果】您的任务正在{status_text}，请耐心等待。",
                    "intent": "troubleshoot",
                    "troubleshoot_flow": "",
                    "troubleshoot_step": 0,
                    "user_memory": user_memory,
                }

            # 任务成功
            if status == "SUCCESS":
                log_response(0, f"任务成功: {task_result.get('task_id')}")
                return {
                    "response": "【查询结果】您的任务已完成，请查看生成结果。",
                    "intent": "troubleshoot",
                    "troubleshoot_flow": "",
                    "troubleshoot_step": 0,
                    "user_memory": user_memory,
                }

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
                "user_memory": user_memory,
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
                "user_memory": user_memory,
            }
            if is_final:
                result["response"] += "\n\n如以上方法未能解决，请点击「转人工客服」提交工单，附上 TaskID，客服会帮你处理。"
            return result
        else:
            # 进入下一步骤
            current_step = get_step(flow, next_id)
            current_step_idx = prev_step_idx + 1

    # ─ 5. 构建 LLM prompt（带决策树约束 + 工具结果 + 用户记忆）──
    flow_structure = _format_flow_structure(flow)

    # 构建工具结果上下文
    tool_context = ""
    if tool_results:
        tool_context = "\n\n## 已查询到的信息\n"
        for tool_name, tool_result in tool_results:
            tool_context += f"- {tool_name}: {json.dumps(tool_result, ensure_ascii=False)}\n"

    # 构建用户记忆上下文
    memory_context = _format_user_memory(user_memory)

    current_question = current_step['question'] if current_step else '建议转人工客服'
    troubleshoot_prompt = (
        "你是 Neowow 平台的技术支持，正在通过结构化流程引导用户排查问题。\n\n"
        "## 当前排查流程\n"
        f"{flow_structure}\n\n"
        "## 知识库参考（与当前问题相关的FAQ）\n"
        f"{kb_context if kb_context else '（暂无相关FAQ）'}\n"
        f"{tool_context}{memory_context}\n"
        "## 回答规则\n"
        "- 简洁、直接、有条理，用编号或分点说明\n"
        '- 不要加emoji，不要用"哈""呢""啦"等语气词\n'
        "- 保持AI客服特征，不需要伪装成真人\n"
        f"- 当前应该问的问题是：「{current_question}」\n"
        "- 根据用户回答判断下一步，严格按照流程走\n"
        "- 如果已查询到任务状态/积分/会员信息，在回答中引用这些数据\n"
        "- 如果用户记忆中已有 TaskID，后续不需要再问\n"
        "- 如果问题已解决，给出解决方案\n"
        f"- 如果排查步数已达上限({flow['max_steps']}步)，主动建议点击「转人工客服」提交工单"
    )

    messages = [{"role": "system", "content": troubleshoot_prompt}]

    # 添加最近对话历史
    for role, content in history[-8:]:
        messages.append({"role": "user" if role == "user" else "assistant", "content": content})

    # 多模态：有图片时用 content array 格式
    if user_images:
        content_parts = [{"type": "text", "text": user_input}]
        for img_b64 in user_images:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"}
            })
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": user_input})

    # ── 6. 调用 LLM ──
    reply, model_used = _call_llm(messages)

    log_response(current_step_idx, reply[:50])

    return {
        "response": reply,
        "intent": "troubleshoot",
        "troubleshoot_flow": flow_id,
        "troubleshoot_step": current_step_idx,
        "user_memory": user_memory,
        "model_used": model_used,
    }


def _extract_info_from_input(text: str) -> dict:
    """从用户输入中提取关键信息（TaskID等）"""
    import re
    info = {}

    # 提取 TaskID — 支持多种格式：
    # 1. 32位十六进制（如：000465cf4f9545bfa47ba66ee5e2544b）
    task_match = re.search(r'[a-f0-9]{32}', text.lower())
    if task_match:
        info["task_id"] = task_match.group(0)
    else:
        # 2. 带前缀的 TaskID（如：TaskID: xxx、任务ID：xxx）
        task_match = re.search(r'(?:TaskID|任务ID|task\s*id)[：:\s]+([A-Za-z0-9_\-]+)', text, re.IGNORECASE)
        if task_match:
            info["task_id"] = task_match.group(1)
        else:
            # 3. 末尾的独立 ID（如：视频生成失败了 NOT_EXIST）
            # 匹配末尾的非中文字符序列（长度>=4，排除纯标点和短词）
            task_match = re.search(r'[\s，。！？,!\?]*([A-Za-z][A-Za-z0-9_]{3,}|[0-9]{8,})$', text)
            if task_match:
                info["task_id"] = task_match.group(1)

    return info


# ── 多轮记忆相关函数 ──────────────────────────────────────

def _extract_user_memory(text: str, current_memory: dict) -> dict:
    """
    从用户输入中提取需要跨轮次记住的信息

    记住的信息包括：
    - task_id: TaskID（跨轮次复用，不用重复问）
    - member_level: 会员等级（结合权益回答）
    - member_days: 会员剩余天数
    - problem_type: 问题类型（如 video_fail、image_fail 等）
    - troubleshooting: 是否正在排查中
    """
    import re
    memory = current_memory.copy() if current_memory else {}

    # 提取 TaskID
    info = _extract_info_from_input(text)
    if info.get("task_id"):
        memory["task_id"] = info["task_id"]

    # 提取会员等级声明
    member_match = re.search(r'(?:我是|我的|我用的)\s*(?:[是|的])?\s*(\S+)(?:会员|VIP|plus|Plus|PLUS|pro|Pro|PRO)', text)
    if member_match:
        memory["member_level"] = member_match.group(1).upper()
    elif re.search(r'(?:PLUS|plus|Pro|pro|PRO|标准|基础|高级)会员', text):
        # 提取会员类型
        for level in ["PLUS", "PRO", "标准", "基础", "高级"]:
            if level.lower() in text.lower():
                memory["member_level"] = level
                break

    # 提取问题类型（从排查流程匹配）
    from troubleshoot_flows import match_flow
    flow_id = match_flow(text)
    if flow_id:
        memory["problem_type"] = flow_id
        memory["troubleshooting"] = True

    return memory


def _update_memory(state: dict) -> dict:
    """更新用户记忆"""
    current_memory = state.get("user_memory", {})
    user_input = state.get("user_input", "")
    return _extract_user_memory(user_input, current_memory)


def _format_user_memory(memory: dict) -> str:
    """将用户记忆格式化为 LLM 可读的文本"""
    if not memory:
        return ""

    parts = []
    if memory.get("task_id"):
        parts.append(f"- TaskID: {memory['task_id']}")
    if memory.get("member_level"):
        parts.append(f"- 会员等级: {memory['member_level']}")
    if memory.get("problem_type"):
        parts.append(f"- 问题类型: {memory['problem_type']}")
    if memory.get("troubleshooting"):
        parts.append("- 当前正在排查流程中")

    if not parts:
        return ""

    return "\n## 用户记忆（跨轮次信息）\n" + "\n".join(parts) + "\n"


def _is_false_positive(task_result: dict) -> bool:
    """
    判断是否为疑似误伤（平台误判）

    判断逻辑：
    - 错误码为 SYSTEM_ERROR 且错误信息包含敏感内容相关关键词
    - 这类错误通常是平台过度拦截，用户内容可能实际合规
    """
    error_code = (task_result.get("error_code") or "").upper()
    platform_error = (task_result.get("platform_error") or "").lower()
    error_message = (task_result.get("error_message") or "").lower()

    # 关键词：敏感信息、版权相关（这些是常见的误伤类型）
    false_positive_keywords = [
        "sensitive", "sensitive information",
        "敏感", "敏感信息",
    ]

    # 判断：错误码是 SYSTEM_ERROR 且包含敏感内容关键词
    if error_code == "SYSTEM_ERROR":
        for kw in false_positive_keywords:
            if kw in platform_error or kw in error_message:
                return True

    return False


def _get_false_positive_guidance(task_result: dict) -> str:
    """获取误伤引导文案"""
    task_id = task_result.get("task_id", "")
    return (
        "\n\n⚠️ 检测到可能是平台误伤（内容实际合规但被错误拦截）。"
        "建议：\n"
        "1. 先尝试精简提示词，避免使用可能触发审核的词汇\n"
        "2. 如确认内容合规，请点击「转人工客服」提交工单，附上 TaskID\n"
        "3. 客服会向平台申请内容复核，通常 24 小时内处理"
    )


def _inject_tool_results(solution: str, tool_results: list) -> str:
    """将工具查询结果注入到解决方案中"""
    import json
    for tool_name, result in tool_results:
        if tool_name == "task_status":
            status = result.get("status", "未知").upper()
            error = result.get("error_message", "")
            platform_error = result.get("platform_error", "")

            if status == "FAILED":
                solution += f"\n\n【查询结果】您的任务状态为：失败\n【失败原因】{error}"
                if platform_error:
                    solution += f"\n【平台报错】{platform_error[:100]}"

                # 检测是否为疑似误伤
                if _is_false_positive(result):
                    solution += (
                        "\n\n【系统判断】️ 检测到可能是平台误伤（内容实际合规但被错误拦截）"
                        "\n\n建议：\n"
                        "1. 先尝试精简提示词，避免使用可能触发审核的词汇\n"
                        "2. 如确认内容合规，请点击「转人工客服」提交工单，附上 TaskID\n"
                        "3. 客服会向平台申请内容复核，通常 24 小时内处理"
                    )
                else:
                    solution += "\n\n请根据以上信息检查并修改后重试。如仍有问题，请点击「转人工客服」提交工单。"

            elif status == "PROCESSING":
                solution += f"\n\n【查询结果】您的任务正在处理中，请耐心等待。"
            elif status == "SUCCESS":
                solution += "\n\n【查询结果】您的任务已完成，请查看生成结果。"
            elif status == "PENDING":
                solution += "\n\n【查询结果】您的任务正在排队，请耐心等待。"
            elif status == "NOT_FOUND":
                solution += f"\n\n【查询结果】{error or '未找到该任务'}"
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


def _call_llm(messages: list) -> tuple:
    """调用 LLM（主模型 + 自动重试 + 备用模型降级）
    返回: (reply, model_name)
    """
    reply = None
    model_used = LLM_CONFIG["model_name"]

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
                model_used = fm["model_name"]
                # 记录降级事件
                try:
                    import requests
                    requests.post("http://localhost:8001/api/stats/fallback", timeout=2)
                except Exception:
                    pass
                break
            except Exception:
                continue

    if reply is None:
        reply = "抱歉，系统暂时繁忙，请稍后再试。如需紧急帮助，请点击「转人工客服」。"

    return reply, model_used


def general_reply(state: dict) -> dict:
    """节点5：通用回复 — 大模型兜底，使用三层 system prompt"""
    user_input = state["user_input"]
    history = state.get("history", [])
    kb_reference = state.get("kb_reference", "")
    chunk_reference = state.get("chunk_reference", "")
    user_images = state.get("user_images", [])

    # ─ 更新多轮记忆 ──
    user_memory = _update_memory(state)
    memory_context = _format_user_memory(user_memory)

    # 合并参考内容
    all_reference = ""
    if kb_reference:
        all_reference += "【FAQ参考】\n" + kb_reference + "\n\n"
    if chunk_reference:
        all_reference += "【文档片段参考】\n" + chunk_reference

    # 组装三层 system prompt（加入用户记忆）
    system_prompt = build_system_prompt(history, all_reference if all_reference else None)
    if memory_context:
        system_prompt += "\n\n" + memory_context

    # 构建消息
    messages = [{"role": "system", "content": system_prompt}]
    for role, content in history[-6:]:
        messages.append({"role": "user" if role == "user" else "assistant", "content": content})

    # 多模态：有图片时用 content array 格式
    if user_images:
        content_parts = [{"type": "text", "text": user_input}]
        for img_b64 in user_images:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"}
            })
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": user_input})

    reply = None
    model_used = LLM_CONFIG["model_name"]

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
                model_used = fm["model_name"]
                print("[模型降级] 备用模型成功")
                # 记录降级事件
                try:
                    import requests
                    requests.post("http://localhost:8001/api/stats/fallback", timeout=2)
                except Exception:
                    pass
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
    return {"response": reply, "intent": "general", "user_memory": user_memory, "model_used": model_used}


def evaluate_response(state: dict) -> dict:
    """副Agent节点：分维度评估并修正主Agent的回答"""
    user_input = state["user_input"]
    response = state.get("response", "")
    intent = state.get("intent", "general")
    kb_reference = state.get("kb_reference", "")
    chunk_reference = state.get("chunk_reference", "")

    # 只评估没有知识库参考的通用回复
    if intent in ("troubleshoot", "human"):
        return {"response": response, "intent": intent, "user_memory": state.get("user_memory", {})}
    # 有知识库或 Chunk 参考时，回答有依据，不需要副Agent检查
    kb_ref = state.get("kb_reference", "")
    chunk_ref = state.get("chunk_reference", "")
    if kb_ref or chunk_ref:
        return {"response": response, "intent": intent, "user_memory": state.get("user_memory", {})}

    if not response:
        return state

    # 合并参考内容作为评判依据
    all_reference = ""
    if kb_reference:
        all_reference += "【FAQ参考】\n" + kb_reference + "\n\n"
    if chunk_reference:
        all_reference += "【文档片段参考】\n" + chunk_reference

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
        return {"response": fixed, "intent": intent, "user_memory": state.get("user_memory", {})}

    # 如果 LLM 没按格式输出，保守起见保留原回答
    log_step("evaluate", result="UNKNOWN", reply=reply[:100], user_input=user_input[:50])
    print(f"[副Agent] 未知格式 | 回答：{reply[:50]}...")
    return state

