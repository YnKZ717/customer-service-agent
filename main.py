"""入口文件 — 客服Agent"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from graph import build_graph


def format_history(history: list) -> None:
    """格式化打印对话历史"""
    print("\n" + "-" * 40)
    print("对话历史：")
    for role, content in history[-5:]:  # 只显示最近5轮
        prefix = "用户" if role == "user" else "客服"
        print(f"  {prefix}：{content}")
    print("-" * 40)


def main():
    """运行客服Agent"""
    app = build_graph()

    # 对话历史（跨轮次记忆）
    history = []

    print("=" * 50)
    print("  智能客服Agent v0.2（优化版）")
    print("  输入 'quit' 退出 | 输入 'history' 查看历史")
    print("=" * 50)

    while True:
        user_input = input("\n用户：").strip()

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "退出"):
            print("\n客服：再见！感谢您的咨询。")
            break
        if user_input.lower() == "history":
            format_history(history)
            continue

        # 调用Agent
        result = app.invoke({
            "user_input": user_input,
            "intent": "",
            "response": "",
            "kb_category": "",
            "history": history,
            "ticket_id": "",
            "ticket_summary": "",
        })

        response = result.get("response", "")
        print(f"\n客服：{response}")

        # 更新对话历史
        history.append(("user", user_input))
        history.append(("assistant", response))

        # 显示意图分类（调试用，后续可去掉）
        intent = result.get("intent", "")
        kb_cat = result.get("kb_category", "")
        if intent:
            print(f"  [意图：{intent} | 知识库分类：{kb_cat}]")

        # 转人工时显示工单信息
        ticket_id = result.get("ticket_id", "")
        if ticket_id:
            print(f"  [工单号：{ticket_id}]")


if __name__ == "__main__":
    main()
