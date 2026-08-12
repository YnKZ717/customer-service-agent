"""入口文件 — 客服Agent"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from graph import build_graph
from tools_vector import load_pending_faqs, approve_pending_faq


def format_history(history: list) -> None:
    """格式化打印对话历史"""
    print("\n" + "-" * 40)
    print("对话历史：")
    for role, content in history[-5:]:
        prefix = "用户" if role == "user" else "客服"
        print(f"  {prefix}：{content}")
    print("-" * 40)


def show_pending() -> None:
    """显示待确认的 FAQ 提案"""
    pending = load_pending_faqs()
    if not pending:
        print("\n暂无待确认提案")
        return

    print("\n" + "=" * 50)
    print("待确认 FAQ 提案")
    print("=" * 50)
    for i, p in enumerate(pending):
        status = {"pending": "待确认", "approved": "已批准", "rejected": "已拒绝"}[p['status']]
        print(f"\n[{i}] {status} | {p['created_at']}")
        print(f"  问：{p['question']}")
        print(f"  答：{p['answer'][:60]}...")
        if p.get('history'):
            print(f"  上下文：{len(p['history'])}轮对话")

    print("\n" + "-" * 50)
    print("操作：approve <编号> 批准 | reject <编号> 拒绝")
    print("-" * 50)


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
        if user_input.lower() == "pending":
            show_pending()
            continue
        if user_input.lower().startswith("approve "):
            try:
                idx = int(user_input.split()[1])
                approve_pending_faq(idx)
            except (IndexError, ValueError):
                print("用法：approve <编号>")
            continue
        if user_input.lower().startswith("reject "):
            try:
                idx = int(user_input.split()[1])
                # TODO: 实现 reject
                print(f"已拒绝提案 {idx}")
            except (IndexError, ValueError):
                print("用法：reject <编号>")
            continue

        # 调用Agent
        result = app.invoke({
            "user_input": user_input,
            "intent": "",
            "response": "",
            "kb_found": False,
            "kb_reference": "",
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
