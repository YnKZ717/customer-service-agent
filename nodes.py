"""节点定义 — 客服Agent的每个处理步骤"""
from tools import search_knowledge_base, transfer_to_human


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
    """节点4：通用回复 — 大模型兜底（后续接入API）"""
    user_input = state["user_input"]
    response = (
        '感谢您的提问。关于"' + user_input + '"，我暂时无法给出准确回答。\n'
        '建议您：\n'
        '1. 尝试换个说法提问\n'
        '2. 输入"人工"转接人工客服\n'
        '3. 查看帮助中心获取更多信息'
    )
    return {"response": response, "intent": "general"}
