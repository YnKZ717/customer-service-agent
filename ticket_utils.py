"""工单工具函数 — 独立模块，避免循环导入"""
import json
import os
import re
from datetime import datetime

# 项目根目录（tools_vector.py 所在目录）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_TICKET_FILE = os.path.join(_PROJECT_ROOT, "tickets.json")

# TaskID / SessionID / NodeID 正则模式
_TASKID_RE = re.compile(r'TaskID[:\s]*([a-f0-9]{32})', re.IGNORECASE)
_SESSIONID_RE = re.compile(r'SessionID[:\s]*(\d{19,25})', re.IGNORECASE)
_NODEID_RE = re.compile(r'NodeID[:\s]*([a-f0-9-]{36})', re.IGNORECASE)


def extract_error_ids(text: str) -> dict:
    """从错误消息中提取 TaskID / SessionID / NodeID"""
    result = {}
    m = _TASKID_RE.search(text)
    if m:
        result['task_id'] = m.group(1)
    m = _SESSIONID_RE.search(text)
    if m:
        result['session_id'] = m.group(1)
    m = _NODEID_RE.search(text)
    if m:
        result['node_id'] = m.group(1)
    return result


def is_copyright_error(text: str) -> bool:
    """检测是否为版权限制类错误"""
    keywords = ['版权', 'copyright', '涉及版权', 'content restriction']
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


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


def create_ticket(user_input: str, history: list, priority: str = "normal", tags: list = None) -> dict:
    """创建工单，支持优先级和标签"""
    tickets = load_tickets()
    ticket_id = f"TK-{len(tickets) + 1:04d}"
    ticket = {
        "ticket_id": ticket_id,
        "question": user_input[:500],
        "history": history[-6:] if history else [],
        "status": "pending",
        "priority": priority,
        "tags": tags or [],
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
