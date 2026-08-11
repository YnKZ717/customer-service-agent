"""入口文件 — 客服Agent"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from graph import build_graph


def main():
    """运行客服Agent"""
    app = build_graph()

    print("=" * 50)
    print("  智能客服Agent v0.1")
    print("  输入 'quit' 退出")
    print("=" * 50)

    while True:
        user_input = input("\n用户：").strip()
        if user_input.lower() in ("quit", "exit", "退出"):
            print("客服：再见！")
            break
        if not user_input:
            continue

        # 调用Agent
        result = app.invoke({
            "user_input": user_input,
            "intent": "",
            "response": "",
        })

        print(f"客服：{result.get('response', '')}")


if __name__ == "__main__":
    main()
