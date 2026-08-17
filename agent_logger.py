"""Agent 结构化日志系统 — 记录每一步操作，方便调试和追溯"""
import json
import logging
from datetime import datetime
from pathlib import Path


# ── 日志配置 ─────────────────────────────────────────────

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 创建 logger
logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)

# 文件 handler
file_handler = logging.FileHandler(
    LOG_DIR / f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    encoding="utf-8",
)
file_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(file_handler)

# 控制台 handler（可选，调试时开启）
# console_handler = logging.StreamHandler()
# console_handler.setFormatter(logging.Formatter("%(message)s"))
# logger.addHandler(console_handler)


# ── 日志记录函数 ─────────────────────────────────────────────

def log_step(step_type: str, **kwargs):
    """
    记录一个步骤

    step_type 可选值:
    - "intent": 意图识别
    - "kb_lookup": 知识库查询
    - "tool_call": 工具调用
    - "flow_match": 流程匹配
    - "branch": 分支判断
    - "response": 最终回复
    - "error": 错误信息
    """
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "step": step_type,
        **kwargs,
    }
    logger.info(json.dumps(log_entry, ensure_ascii=False))


def log_flow_start(flow_id: str, user_input: str):
    """记录排查流程开始"""
    log_step(
        "flow_start",
        flow_id=flow_id,
        user_input=user_input[:50],
    )


def log_kb_lookup(categories: list, match_count: int, matches: list = None):
    """记录知识库查询"""
    log_step(
        "kb_lookup",
        categories=categories,
        match_count=match_count,
        matches=matches[:3] if matches else [],  # 只记前3条
    )


def log_tool_call(tool_name: str, params: dict, result: dict):
    """记录工具调用"""
    log_step(
        "tool_call",
        tool=tool_name,
        params=params,
        result=result,
    )


def log_branch_match(step_id: str, user_input: str, branch: str):
    """记录分支匹配"""
    log_step(
        "branch",
        step=step_id,
        user_input=user_input[:50],
        matched_branch=branch,
    )


def log_response(step: int, response: str, is_final: bool = False):
    """记录回复"""
    log_step(
        "response",
        step=step,
        response=response[:100],
        is_final=is_final,
    )


def log_error(error_type: str, message: str, context: dict = None):
    """记录错误"""
    log_step(
        "error",
        error_type=error_type,
        message=message,
        context=context or {},
    )
