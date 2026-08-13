"""工单工具函数 — 独立模块，避免循环导入"""
import json
import os
from datetime import datetime

# 项目根目录（tools_vector.py 所在目录）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_TICKET_FILE = os.path.join(_PROJECT_ROOT, "tickets.json")


def load_tickets() -> list:
    """加载所有工单"""
    try:
        with open(_TICKET_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_tickets(tickets: list):
    """保存工单到文件"""
    with open(_TICKET_FILE, 'w', encoding='utf-8') as f:
        json.dump(tickets, f, ensure_ascii=False, indent=2)


def create_ticket(user_input: str, history: list) -> dict:
    """创建工单"""
    tickets = load_tickets()
    ticket_id = f"TK-{len(tickets) + 1:04d}"
    ticket = {
        "ticket_id": ticket_id,
        "question": user_input[:200],
        "history": history[-6:] if history else [],
        "status": "pending",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reply": "",
        "replied_at": "",
    }
    tickets.append(ticket)
    save_tickets(tickets)
    return ticket


def transfer_to_human(user_input: str, history: list) -> dict:
    """转接人工客服（独立运行时用）"""
    ticket = create_ticket(user_input, history)
    return {
        "response": f"已为您转接人工客服，工单号：{ticket['ticket_id']}。客服将尽快与您联系。",
        "ticket_id": ticket['ticket_id'],
    }
