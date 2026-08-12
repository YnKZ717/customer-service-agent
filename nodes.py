"""节点定义 — 客服Agent的每个处理步骤"""
from tools_vector import search_knowledge_base, transfer_to_human, save_pending_faq
from tools_chunk import search_chunks
from openai import OpenAI
from config import LLM_CONFIG

# 初始化大模型客户端
client = OpenAI(
    api_key=LLM_CONFIG["api_key"],
    base_url=LLM_CONFIG["base_url"],
)


# ── 意图关键词映射（与知识库对齐）──────────────────────────
INTENT_KEYWORDS = {
    "account":      ["注册", "登录", "账号", "密码"],
    "billing":      ["充值", "积分", "付费", "支付", "扫码"],
    "codingplan":   ["CodingPlan", "套餐", "额度", "Credits"],
    "agent_service":["智能体", "对话", "创作", "云端服务"],
    "desktop":      ["客户端", "桌面", "下载", "安装"],
    "app_market":   ["应用市场", "购买应用", "上传应用", "预览"],
    "skill_market": ["技能市场", "技能", "同步"],
    "deploy_token": ["部署Token", "CI/CD", "发布"],
    "backup":       ["备份", "数据", "记录", "云端"],
    "membership":   ["会员", "权益", "VIP"],
    "complaint":    ["投诉", "不满意", "差评"],
    "human":        ["人工", "转人工", "客服"],
}

# ── 三层 system prompt 组装 ──
SYSTEM_PROMPT_STABLE = """你是 Neowow Studio 的智能客服助手。Neowow 是一站式智能创意内容生产与协作平台。
回答规则：
1. 礼貌、简洁、准确
2. 不确定的问题诚实告知，建议转人工
3. 不编造平台没有的功能
4. 涉及充值、账号安全等敏感操作，提醒用户通过官方渠道"""

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

    # 查知识库，获取精确匹配和相关参考
    question, answer, reference = search_knowledge_base(query, threshold=0.8, return_reference=True)

    if answer is None:
        # 知识库里没有精确匹配，但可能有相关参考
        return {
            "kb_found": False,
            "intent": state["intent"],
            "user_input": state["user_input"],
            "kb_reference": reference,  # 传给大模型作为参考
        }

    return {
        "response": answer,
        "intent": state["intent"],
        "kb_category": question or "未匹配",
        "kb_found": True,
        "kb_reference": "",
    }


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
    """节点3：转人工 — 生成工单"""
    result = transfer_to_human(
        state["user_input"],
        state.get("history", []),
    )
    result["intent"] = state["intent"]
    return result


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

    try:
        response = client.chat.completions.create(
            model=LLM_CONFIG["model_name"],
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        reply = response.choices[0].message.content

        # 沉淀：新问题自动记录
        save_pending_faq(user_input, reply, history)
    except Exception as e:
        reply = f"系统暂时繁忙，请稍后再试。（错误：{str(e)[:50]}）"

    return {"response": reply, "intent": "general"}
