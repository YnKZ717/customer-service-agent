"""工具函数 — 客服Agent能调用的能力"""


def search_knowledge_base(query: str) -> str:
    """搜索知识库（先写死，后面接真实数据库）"""
    faq = {
        "退款": "退款将在3-5个工作日内原路返回，请注意查收。",
        "发货": "订单确认后24小时内发货，可通过订单号查询物流。",
        "发票": "可在订单详情页申请电子发票，1-3个工作日开具。",
    }
    for keyword, answer in faq.items():
        if keyword in query:
            return answer
    return "抱歉，暂未找到相关信息，已为您转接人工客服。"


def transfer_to_human(state: dict) -> dict:
    """转接人工客服（先打印，后面接真实工单系统）"""
    print(">>> 已转接人工客服，工单号：TK-001")
    return {"response": "已为您转接人工客服，请稍候。"}
