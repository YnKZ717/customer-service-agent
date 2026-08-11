"""LangGraph 图定义 — 客服Agent的工作流"""
from langgraph.graph import StateGraph, END

from nodes import (
    classify_intent,
    answer_from_kb,
    handle_human,
    general_reply,
    end_conversation,
)


# 状态定义
class AgentState(dict):
    user_input: str       # 用户输入
    intent: str           # 意图分类结果
    response: str         # 客服回复


def build_graph():
    """构建客服Agent流程图"""
    graph = StateGraph(AgentState)

    # ─ 添加节点 ──
    graph.add_node("classify", classify_intent)     # 意图识别
    graph.add_node("kb_answer", answer_from_kb)     # 知识库回答
    graph.add_node("human", handle_human)            # 转人工
    graph.add_node("general", general_reply)         # 通用回复
    graph.add_node("end", end_conversation)          # 结束

    # ─ 连线 ──
    graph.set_entry_point("classify")               # 入口：意图识别
    graph.add_edge("end", END)                       # 结束节点

    # 条件分支：根据意图走不同路线
    def route_by_intent(state):
        intent = state.get("intent", "general")
        if intent == "human":
            return "human"
        elif intent in ("refund", "shipping", "invoice"):
            return "kb_answer"
        else:
            return "general"

    graph.add_conditional_edges(
        "classify",              # 从意图识别节点出发
        route_by_intent,         # 条件函数
        {                       # 路由表
            "human": "human",
            "kb_answer": "kb_answer",
            "general": "general",
        },
    )

    # 各分支最终都到结束
    graph.add_edge("kb_answer", "end")
    graph.add_edge("human", "end")
    graph.add_edge("general", "end")

    return graph.compile()
