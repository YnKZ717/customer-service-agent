"""国际化（i18n）— 中英文切换"""

# 语言包
LANGUAGES = {
    "zh": {
        # 聊天界面
        "greeting": "你好！我是 Neowow Studio 的智能客服助手。你可以问我关于账号、充值、CodingPlan 套餐、智能体使用等问题。",
        "input_placeholder": "输入你的问题...",
        "send_button": "发送",
        "transfer_human": "转人工客服",
        "quick_questions": ["怎么充值积分", "CodingPlan 是什么", "怎么使用智能体", "我要投诉"],

        # 反馈
        "feedback_helpful": "有帮助",
        "feedback_not_helpful": "没帮助",
        "feedback_thanks": "感谢反馈",

        # 工单
        "ticket_created": "已为您转接人工客服，工单号：{ticket_id}。客服将尽快与您联系。",
        "ticket_failed": "创建工单失败，请稍后再试。",
        "service_unavailable": "服务暂时不可用，请稍后再试。",

        # 统计
        "faq_count": "FAQ 数量",
        "pending_count": "待确认提案",
        "api_calls": "API 调用",
        "kb_hit_rate": "知识库命中率",
        "chat_rounds": "对话轮次",

        # 状态
        "status_pending": "待处理",
        "status_in_progress": "处理中",
        "status_resolved": "已解决",
        "status_closed": "已关闭",
    },
    "en": {
        # Chat UI
        "greeting": "Hello! I'm Neowow Studio's AI customer service assistant. You can ask me about accounts, recharging, CodingPlan packages, agent usage, etc.",
        "input_placeholder": "Type your question...",
        "send_button": "Send",
        "transfer_human": "Transfer to Human Agent",
        "quick_questions": ["How to recharge credits", "What is CodingPlan", "How to use agents", "I want to complain"],

        # Feedback
        "feedback_helpful": "Helpful",
        "feedback_not_helpful": "Not Helpful",
        "feedback_thanks": "Thanks for feedback",

        # Tickets
        "ticket_created": "You've been transferred to human support. Ticket ID: {ticket_id}. We'll contact you soon.",
        "ticket_failed": "Failed to create ticket. Please try again.",
        "service_unavailable": "Service temporarily unavailable. Please try again later.",

        # Stats
        "faq_count": "FAQ Count",
        "pending_count": "Pending Proposals",
        "api_calls": "API Calls",
        "kb_hit_rate": "KB Hit Rate",
        "chat_rounds": "Chat Rounds",

        # Status
        "status_pending": "Pending",
        "status_in_progress": "In Progress",
        "status_resolved": "Resolved",
        "status_closed": "Closed",
    },
}

# 当前语言（默认中文）
_current_lang = "zh"


def set_language(lang: str):
    """切换语言"""
    global _current_lang
    if lang in LANGUAGES:
        _current_lang = lang


def get_language() -> str:
    """获取当前语言"""
    return _current_lang


def t(key: str, **kwargs) -> str:
    """翻译文本"""
    text = LANGUAGES.get(_current_lang, {}).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text
