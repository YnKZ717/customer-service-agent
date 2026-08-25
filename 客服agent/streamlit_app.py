"""Streamlit 前端界面 — 客服Agent"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import streamlit as st
from graph import build_graph
from tools_vector import load_pending_faqs, approve_pending_faq, reject_pending_faq

# ── 页面配置（设置中文，防止浏览器翻译提示）──────────
st.set_page_config(
    page_title="Neowow 智能客服",
    page_icon="🤖",
    layout="wide",
)

# 注入 HTML 声明语言为中文，防止浏览器翻译提示
st.markdown("""
<script>
document.documentElement.lang = 'zh-CN';
</script>
""", unsafe_allow_html=True)

# ─ 初始化 Agent ──
@st.cache_resource
def get_app():
    return build_graph()

app = get_app()


# ── 侧边栏：页面切换 ──
page = st.sidebar.radio("选择页面", ["💬 客服对话", "📋 FAQ管理"])


# ═══════════════════════════════════════════
# 页面1：客服对话
# ══════════════════════════════════════════
if page == "💬 客服对话":
    st.title("🤖 Neowow Studio 智能客服")
    st.caption("我是 Neowow 平台的智能客服助手，有什么可以帮你的？")

    # 初始化会话状态
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "你好！我是 Neowow Studio 的智能客服助手。你可以问我关于账号、充值、CodingPlan套餐、智能体使用等问题。"}
        ]
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 快捷问题按钮
    cols = st.columns(4)
    quick_questions = ["怎么充值积分", "CodingPlan是什么", "怎么使用智能体", "我要投诉"]
    for col, q in zip(cols, quick_questions):
        if col.button(q, use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": q})
            st.session_state["_quick_q"] = q

    # 处理用户输入（在显示消息之前处理，这样新消息会出现在列表中）
    # 注意：form 放在最后，这里先检查是否有待处理输入
    if "_pending_input" in st.session_state:
        user_input = st.session_state.pop("_pending_input")
    elif "_quick_q" in st.session_state:
        user_input = st.session_state.pop("_quick_q")
    else:
        user_input = None

    if user_input:
        with st.spinner("思考中..."):
            result = app.invoke({
                "user_input": user_input,
                "intent": "",
                "response": "",
                "kb_found": False,
                "kb_reference": "",
                "kb_category": "",
                "chunk_found": False,
                "chunk_reference": "",
                "history": st.session_state.chat_history,
                "ticket_id": "",
                "ticket_summary": "",
            })

            response = result.get("response", "抱歉，系统暂时无法回答。")

            st.session_state.chat_history.append(("user", user_input))
            st.session_state.chat_history.append(("assistant", response))
            st.session_state.messages.append({"role": "assistant", "content": response})

    # 显示所有历史消息（输入框上方）
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # 用户输入框（放在页面最底部）
    with st.form("chat_form", clear_on_submit=True):
        input_text = st.text_input(
            "输入你的问题...",
            label_visibility="collapsed",
            placeholder="输入你的问题，按回车或点击发送...",
        )
        submitted = st.form_submit_button(" 发送", use_container_width=True)
        if submitted and input_text:
            st.session_state.messages.append({"role": "user", "content": input_text})
            st.session_state["_pending_input"] = input_text
            st.rerun()

    # 底部统计
    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.metric("FAQ数量", len(st.session_state.get("_faq_data", [])))
    pending = load_pending_faqs()
    pending_count = len([p for p in pending if p['status'] == 'pending'])
    col2.metric("待确认提案", pending_count)
    col3.metric("对话轮次", len(st.session_state.chat_history) // 2)


# ═══════════════════════════════════════════
# 页面2：FAQ管理（沉淀审核）
# ═══════════════════════════════════════════
elif page == "📋 FAQ管理":
    st.title("📋 FAQ 管理")
    st.caption("审核用户提出的新问题，批准后会加入知识库")

    pending = load_pending_faqs()
    pending_items = [p for p in pending if p['status'] == 'pending']

    if not pending_items:
        st.info("暂无待确认的 FAQ 提案")
    else:
        st.subheader(f"待确认提案（{len(pending_items)} 条）")

        for i, p in enumerate(pending_items):
            real_idx = pending.index(p)
            with st.container(border=True):
                st.markdown(f"**问题：** {p['question']}")
                st.markdown(f"**答案：** {p['answer']}")
                st.caption(f"时间：{p['created_at']}")

                if p.get('original_answer') and p['original_answer'] != p['answer']:
                    with st.expander("查看原始回答（未提炼）"):
                        st.write(p['original_answer'])

                col1, col2 = st.columns(2)
                if col1.button("✅ 批准", key=f"approve_{real_idx}"):
                    if approve_pending_faq(real_idx):
                        st.success(f"已批准：{p['question']}")
                        st.rerun()
                if col2.button("❌ 拒绝", key=f"reject_{real_idx}"):
                    if reject_pending_faq(real_idx):
                        st.success(f"已拒绝：{p['question']}")
                        st.rerun()

    # 查看已批准的FAQ
    st.divider()
    st.subheader("📚 知识库 FAQ")
    from tools_vector import FAQ_DATA
    st.write(f"共 **{len(FAQ_DATA)}** 条 FAQ")

    for i, (q, a, c) in enumerate(FAQ_DATA):
        with st.expander(f"{i+1}. [{c}] {q}"):
            st.write(a)
