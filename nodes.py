"""节点定义 — 客服Agent的每个处理步骤"""
from tools import search_knowledge_base, transfer_to_human
from openai import OpenAI
from config import LLM_CONFIG

# 初始化大模型客户端
client = OpenAI(
    api_key=LLM_CONFIG["api_key"],
    base_url=LLM_CONFIG["base_url"],
)


# ── 意图关键词映射（与知识库对齐）──────────────────────────
INTENT_KEYWORDS = {
    "refund":   ["退款", "退钱", "退回"],
    "return":   ["退货", "退换", "换货"],
    "shipping": ["发货", "物流", "快递", "配送", "到哪了"],
    "invoice":  ["发票", "开票"],
    "order":    ["订单", "下单", "订单状态"],
    "payment":  ["支付", "付款", "微信", "支付宝"],
    "member":   ["会员", "VIP", "积分"],
    "complaint":["投诉", "不满意", "差评"],
    "promo":    ["优惠", "折扣", "优惠券", "活动", "促销"],
    "human":    ["人工", "转人工", "客服", "投诉人工"],
}


def classify_intent(state: dict) -> dict:
    """节点1：意图识别 — 判断用户问题类型"""
    user_input = state["user_input"]

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(k in user_input for k in keywords):
            return {"intent": intent, "user_input": user_input}

    # 没匹配到任何关键词 → 通用问题
    return {"intent": "general", "user_input": user_input}


def answer_from_kb(state: dict) -> dict:
    """节点2：知识库回答 — 查FAQ回答"""
    category, answer = search_knowledge_base(state["user_input"])
    return {
        "response": answer,
        "intent": state["intent"],
        "kb_category": category or "未匹配",
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
    """节点4：通用回复 — 大模型兜底"""
    user_input = state["user_input"]
    history = state.get("history", [])

    # 构建对话历史
    messages = [{"role": "system", "content": "你是智能客服助手，礼貌、简洁、准确地回答用户问题。如果不确定，诚实告知并建议转人工。"}]
    for role, content in history[-6:]:  # 最近3轮对话
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
    except Exception as e:
        reply = f"系统暂时繁忙，请稍后再试。（错误：{str(e)[:50]}）"

    return {"response": reply, "intent": "general"}
