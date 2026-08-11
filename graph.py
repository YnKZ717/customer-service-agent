"""LangGraph 图定义 — 客服Agent的工作流"""
from langgraph.graph import StateGraph, END

from nodes import (
    classify_intent,
    answer_from_kb,
    handle_human,
    general_reply,
)


# ── 状态定义（Agent 的记忆）───────────────────────────────
class AgentState(dict):
    user_input: str          # 当前用户输入
    intent: str              # 意图分类结果
    response: str            # 客服回复
    kb_category: str         # 知识库匹配的分类
    history: list            # 对话历史 [(role, content), ...]
    ticket_id: str           # 工单号（转人工时生成）
    ticket_summary: str      # 工单摘要


def build_graph():
    """构建客服Agent流程图"""
    graph = StateGraph(AgentState)

    # ── 添加节点 ──
    graph.add_node("classify", classify_intent)      # 意图识别
    graph.add_node("kb_answer", answer_from_kb)      # 知识库回答
    graph.add_node("human", handle_human)             # 转人工
    graph.add_node("general", general_reply)          # 通用回复

    # ─ 入口 ──
    graph.set_entry_point("classify")

    # ── 条件分支：根据意图路由 ──
    def route_by_intent(state):
        intent = state.get("intent", "general")
        if intent == "human":
            return "human"
        elif intent in ("refund", "return", "shipping", "invoice",
                        "order", "payment", "member", "complaint", "promo"):
            return "kb_answer"
        else:
            return "general"

    graph.add_conditional_edges(
        "classify",
        route_by_intent,
        {
            "human": "human",
            "kb_answer": "kb_answer",
            "general": "general",
        },
    )

    # ─ 所有分支 → 结束 ─
    graph.add_edge("kb_answer", END)
    graph.add_edge("human", END)
    graph.add_edge("general", END)

    return graph.compile()
