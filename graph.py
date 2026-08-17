"""LangGraph 图定义 — 客服Agent的工作流"""
from langgraph.graph import StateGraph, END

from nodes import (
    classify_intent,
    answer_from_kb,
    chunk_search_node,
    handle_human,
    general_reply,
    troubleshoot,
)


# ── 状态定义（Agent 的记忆）───────────────────────────────
class AgentState(dict):
    user_input: str          # 当前用户输入
    intent: str              # 意图分类结果
    response: str            # 客服回复
    kb_found: bool           # FAQ知识库是否找到答案
    kb_reference: str        # FAQ知识库参考内容（传给大模型）
    kb_category: str         # FAQ知识库匹配的分类
    kb_images: list          # FAQ命中的截图文件名
    chunk_found: bool        # Chunk文档片段是否找到
    chunk_reference: str     # Chunk文档片段参考内容（传给大模型）
    history: list            # 对话历史 [(role, content), ...]
    ticket_id: str           # 工单号（转人工时生成）
    ticket_summary: str      # 工单摘要
    troubleshoot_flow: str   # 当前排查流程 ID（如 "video_fail"）
    troubleshoot_step: int   # 当前排查步骤（0, 1, 2...）


def build_graph():
    """构建客服Agent流程图"""
    graph = StateGraph(AgentState)

    # ── 添加节点 ──
    graph.add_node("classify", classify_intent)      # 意图识别
    graph.add_node("kb_answer", answer_from_kb)      # FAQ知识库回答
    graph.add_node("chunk_search", chunk_search_node) # Chunk文档片段搜索
    graph.add_node("troubleshoot", troubleshoot)      # 故障排查（多轮引导）
    graph.add_node("human", handle_human)             # 转人工
    graph.add_node("general", general_reply)          # 通用回复（大模型兜底）

    # ── 入口 ──
    graph.set_entry_point("classify")

    # ── 条件分支1：根据意图判断路由 ──
    def route_after_classify(state):
        intent = state.get("intent", "general")
        if intent == "human":
            return "human"
        elif intent == "troubleshoot":
            return "troubleshoot"
        else:
            # 所有问题都先查FAQ知识库
            return "kb_answer"

    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "human": "human",
            "troubleshoot": "troubleshoot",
            "kb_answer": "kb_answer",
        },
    )

    # ── 条件分支2：FAQ查完后，没找到就查Chunk ──
    def route_after_kb(state):
        if state.get("kb_found"):
            return "end"
        else:
            return "chunk_search"

    graph.add_conditional_edges(
        "kb_answer",
        route_after_kb,
        {
            "end": END,
            "chunk_search": "chunk_search",
        },
    )

    # ── 条件分支3：Chunk查完后，没找到就走大模型 ──
    def route_after_chunk(state):
        # 无论Chunk是否找到，都走大模型（Chunk找到的话会给大模型提供参考）
        return "general"

    graph.add_conditional_edges(
        "chunk_search",
        route_after_chunk,
        {
            "general": "general",
        },
    )

    # ── 其他分支 → 结束 ──
    graph.add_edge("human", END)
    graph.add_edge("troubleshoot", END)
    graph.add_edge("general", END)

    return graph.compile()
