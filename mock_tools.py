"""Mock 工具函数 — 模拟真实 API 调用，用于演示"""
import random
from datetime import datetime


# ── 模拟数据库 ─────────────────────────────────────────────

MOCK_TASKS = {
    "8078e05dfc514a299c7b40d37e61fa0f": {
        "task_id": "8078e05dfc514a299c7b40d37e61fa0f",
        "type": "text_to_video",
        "status": "failed",
        "error_code": "copyright_restricted",
        "error_message": "检测到版权敏感元素",
        "created_at": "2026-08-17 16:20:15",
        "model": "kling-v2.5",
        "duration": 5,
        "resolution": "1080P",
    },
    "abcdef1234567890abcdef1234567890": {
        "task_id": "abcdef1234567890abcdef1234567890",
        "type": "image_to_video",
        "status": "processing",
        "progress": 65,
        "created_at": "2026-08-17 16:25:30",
        "model": "dreamina-2.0",
        "duration": 8,
        "resolution": "2K",
    },
    "1234567890abcdef1234567890abcdef": {
        "task_id": "1234567890abcdef1234567890abcdef",
        "type": "text_to_image",
        "status": "completed",
        "created_at": "2026-08-17 16:10:00",
        "model": "neo-nano-pro",
        "resolution": "2K",
    },
}

MOCK_USER = {
    "user_id": "test_user_001",
    "credits_balance": 2850,
    "member_level": "PLUS",
    "member_expire": "2026-09-15 23:59:59",
    "monthly_quota": 50,
    "monthly_used": 23,
}


# ── 工具函数 ─────────────────────────────────────────────

def check_task_status(task_id: str) -> dict:
    """
    查询任务状态
    真实场景：调用 POST /api/tasks/{task_id}/status

    返回:
    {
        "task_id": str,
        "status": "processing" | "completed" | "failed" | "pending",
        "progress": int,  # 0-100
        "error_code": str | None,
        "error_message": str | None,
        "type": str,
        "model": str,
        "duration": int,
        "resolution": str,
        "created_at": str,
    }
    """
    print(f"[TOOL] check_task_status(task_id='{task_id}')")

    # 模拟网络延迟
    import time
    time.sleep(0.3)

    if task_id in MOCK_TASKS:
        result = MOCK_TASKS[task_id]
        print(f"[TOOL]   → status={result['status']}, error={result.get('error_code')}")
        return result
    else:
        print(f"[TOOL]   → NOT_FOUND")
        return {
            "task_id": task_id,
            "status": "not_found",
            "error_code": "task_not_found",
            "error_message": "未找到该任务",
        }


def check_credits_balance(user_id: str = None) -> dict:
    """
    查询用户积分余额
    真实场景：调用 GET /api/user/credits

    返回:
    {
        "user_id": str,
        "credits_balance": int,
        "member_level": str,
        "member_expire": str,
        "monthly_quota": int,
        "monthly_used": int,
    }
    """
    print(f"[TOOL] check_credits_balance(user_id='{user_id}')")
    import time
    time.sleep(0.2)

    result = MOCK_USER.copy()
    print(f"[TOOL]   → balance={result['credits_balance']}, level={result['member_level']}")
    return result


def check_member_status(user_id: str = None) -> dict:
    """
    查询会员状态
    真实场景：调用 GET /api/user/member

    返回:
    {
        "user_id": str,
        "member_level": str,
        "member_expire": str,
        "days_remaining": int,
        "benefits": list,
    }
    """
    print(f"[TOOL] check_member_status(user_id='{user_id}')")
    import time
    time.sleep(0.2)

    expire_date = datetime.fromisoformat(MOCK_USER["member_expire"])
    days_remaining = (expire_date - datetime.now()).days

    result = {
        "user_id": MOCK_USER["user_id"],
        "member_level": MOCK_USER["member_level"],
        "member_expire": MOCK_USER["member_expire"],
        "days_remaining": max(0, days_remaining),
        "benefits": [
            "消费95折优惠",
            "每月50次免费生成",
            "支持2K画质",
            "最长10秒视频",
        ],
    }
    print(f"[TOOL]   → level={result['member_level']}, days_remaining={result['days_remaining']}")
    return result


# ── 工具注册表 ─────────────────────────────────────────────

AVAILABLE_TOOLS = {
    "check_task_status": {
        "description": "查询任务状态，支持视频/图片/音频生成任务",
        "params": {"task_id": "任务ID"},
        "function": check_task_status,
    },
    "check_credits_balance": {
        "description": "查询用户积分余额和会员信息",
        "params": {"user_id": "用户ID（可选）"},
        "function": check_credits_balance,
    },
    "check_member_status": {
        "description": "查询会员等级、到期时间、权益",
        "params": {"user_id": "用户ID（可选）"},
        "function": check_member_status,
    },
}


def get_tool(tool_name: str):
    """获取工具函数"""
    return AVAILABLE_TOOLS.get(tool_name)
