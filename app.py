"""Gradio 前端界面 — 客服Agent网页版"""
import gradio as gr
import sys
sys.stdout.reconfigure(encoding='utf-8')

from graph import build_graph

# 初始化Agent
app = build_graph()

def chat(message, history):
    """处理用户消息，返回客服回复"""
    # 把Gradio的history格式转换成我们的格式
    chat_history = []
    if history:
        for turn in history:
            chat_history.append(("user", turn["content"]))
            chat_history.append(("assistant", turn["content"]))

    result = app.invoke({
        "user_input": message,
        "intent": "",
        "response": "",
        "kb_found": False,
        "kb_reference": "",
        "kb_category": "",
        "chunk_found": False,
        "chunk_reference": "",
        "history": chat_history,
        "ticket_id": "",
        "ticket_summary": "",
    })

    response = result.get("response", "抱歉，系统暂时无法回答。")
    return response


# 创建Gradio界面
demo = gr.ChatInterface(
    fn=chat,
    title="Neowow Studio 智能客服",
    description="我是 Neowow 平台的智能客服助手，有什么可以帮你的？",
    examples=["怎么充值积分", "CodingPlan是什么", "怎么使用智能体", "我要投诉"],
)

if __name__ == "__main__":
    demo.launch()
