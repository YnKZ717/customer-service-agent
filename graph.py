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
    kb_found: bool           # 知识库是否找到答案
    kb_reference: str        # 知识库参考内容（传给大模型）
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

    # ── 条件分支1：根据意图判断是否转人工或查知识库 ──
    def route_after_classify(state):
        intent = state.get("intent", "general")
        if intent == "human":
            return "human"
        else:
            # 所有问题都先查知识库（包括general）
            return "kb_answer"

    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "human": "human",
            "kb_answer": "kb_answer",
        },
    )

    # ── 条件分支2：知识库查完后，没找到就走大模型 ──
    def route_after_kb(state):
        if state.get("kb_found"):
            return "end"
        else:
            return "general"

    graph.add_conditional_edges(
        "kb_answer",
        route_after_kb,
        {
            "end": END,
            "general": "general",
        },
    )

    # ─ 其他分支 → 结束 ──
    graph.add_edge("human", END)
    graph.add_edge("general", END)

    return graph.compile()
