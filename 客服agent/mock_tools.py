"""工具函数 — 查询任务状态（真实API）"""
import requests
import json
import time
from datetime import datetime


# ── 真实 API 配置 ─────────────────────────────────────────────

CANVAS_NODE_API = "https://dev.neodomain.cn/admin/api/v1/debug/canvas-node"
API_KEY = "v8dn_7Pr31wvI399PB-BAXOVOsgaksba7BWj7J3QOEM"


# ── 模拟用户数据（积分/会员查询用）───
MOCK_USER = {
    "user_id": "test_user_001",
    "credits_balance": 1250,
    "member_level": "PLUS",
    "member_expire": "2027-06-15",
    "monthly_quota": 50,
    "monthly_used": 23,
}


def check_task_status(task_id: str) -> dict:
    """
    查询任务状态（真实API）
    调用 canvas-node 接口，返回任务状态、错误信息、生成详情

    返回:
    {
        "task_id": str,
        "status": "PENDING" | "PROCESSING" | "SUCCESS" | "FAILED" | "not_found",
        "error_code": str | None,
        "error_message": str | None,  # 中文，给用户看的
        "platform_error": str | None,  # 英文，平台原始报错
        "model": str | None,
        "model_code": str | None,
        "consume_points": int | None,
        "resolution": str | None,
        "duration": int | None,
        "task_type": str | None,
        "created_at": str | None,
        "completed_at": str | None,
    }
    """
    print(f"[TOOL] check_task_status(task_id='{task_id}')")

    try:
        resp = requests.get(
            CANVAS_NODE_API,
            params={"taskId": task_id},
            headers={"X-API-Key": API_KEY},
            timeout=20
        )
        body = resp.json()

        if not body.get("success"):
            print(f"[TOOL]   → API ERROR: {body.get('errCode')}: {body.get('errMessage')}")
            return {
                "task_id": task_id,
                "status": "error",
                "error_code": body.get("errCode"),
                "error_message": body.get("errMessage", "查询失败"),
            }

        data = body.get("data", {})
        nodes = data.get("nodes", [])
        generations = data.get("generations", [])
        dispatch_tasks = data.get("dispatchTasks", [])

        # 没有数据
        if not nodes:
            print(f"[TOOL]   → NOT_FOUND")
            return {
                "task_id": task_id,
                "status": "not_found",
                "error_message": "未找到该任务，请检查 TaskID 是否正确",
            }

        # 取第一个节点（最新）
        node = nodes[0]
        status = node.get("status", "UNKNOWN")

        # 从调度任务取平台原始报错（最关键）
        platform_error = None
        platform_error_code = None
        model_code = None
        if dispatch_tasks:
            dt = dispatch_tasks[0]
            platform_error = dt.get("errorMsg")
            platform_error_code = dt.get("errorCode")
            model_code = dt.get("modelCode")

        # 从生成记录取业务信息
        model = None
        consume_points = None
        resolution = None
        if generations:
            gen = generations[0]
            model = gen.get("model")
            consume_points = gen.get("consumePoints")
            resolution = gen.get("resolution")

        result = {
            "task_id": task_id,
            "status": status,
            "error_code": platform_error_code,
            "error_message": node.get("errorMessage"),  # 中文用户提示
            "platform_error": platform_error,  # 英文原始报错
            "model": model or model_code,
            "model_code": model_code,
            "consume_points": consume_points,
            "resolution": resolution,
            "task_type": node.get("taskType"),
            "created_at": node.get("createTime"),
            "completed_at": node.get("updateTime"),
        }

        print(f"[TOOL]   → status={status}, error={platform_error_code}")
        return result

    except requests.Timeout:
        print(f"[TOOL]   → TIMEOUT")
        return {
            "task_id": task_id,
            "status": "error",
            "error_message": "查询超时，请稍后再试",
        }
    except Exception as e:
        print(f"[TOOL]   → EXCEPTION: {str(e)[:50]}")
        return {
            "task_id": task_id,
            "status": "error",
            "error_message": f"查询异常：{str(e)[:50]}",
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
