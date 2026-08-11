"""节点定义 — 客服Agent的每个处理步骤"""
from tools import search_knowledge_base, transfer_to_human
from config import SYSTEM_PROMPT


def classify_intent(state: dict) -> dict:
    """节点1：意图识别 — 判断用户问题类型"""
    user_input = state["user_input"]

    # 简单关键词分类（后面换成大模型分类）
    if any(k in user_input for k in ["退款", "退货", "取消"]):
        intent = "refund"
    elif any(k in user_input for k in ["发货", "物流", "快递"]):
        intent = "shipping"
    elif any(k in user_input for k in ["发票", "开票"]):
        intent = "invoice"
    elif any(k in user_input for k in ["人工", "客服", "投诉"]):
        intent = "human"
    else:
        intent = "general"

    return {"intent": intent, "user_input": user_input}


def answer_from_kb(state: dict) -> dict:
    """节点2：知识库回答 — 查FAQ回答"""
    answer = search_knowledge_base(state["user_input"])
    return {"response": answer, "intent": state["intent"]}


def handle_human(state: dict) -> dict:
    """节点3：转人工"""
    result = transfer_to_human(state)
    return result


def general_reply(state: dict) -> dict:
    """节点4：通用回复 — 大模型兜底"""
    # 后面接大模型API
    response = f"感谢您的提问（{state['user_input']}），我正在为您查询，请稍候。"
    return {"response": response}


def end_conversation(state: dict) -> dict:
    """节点5：结束"""
    print(f"\n客服：{state.get('response', '对话结束')}")
    return state
