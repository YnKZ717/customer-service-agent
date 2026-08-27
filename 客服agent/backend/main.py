"""FastAPI 后端 — 客服Agent API服务"""
import sys
import os
import json
import time
import logging
import hashlib
from datetime import datetime
from collections import defaultdict

# ── 禁止 HuggingFace 联网检查（必须在所有 import 之前）──
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# ── 日志系统 ──
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "server.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("backend")

# 将父目录加入路径，以导入现有的 graph/nodes/tools 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, AsyncGenerator
import uvicorn

# 导入现有模块
from graph import build_graph
from tools_vector import (
    load_pending_faqs,
    approve_pending_faq,
    reject_pending_faq,
    FAQ_DATA,
)
from ticket_utils import load_tickets, save_tickets, create_ticket, extract_error_ids, is_copyright_error
from i18n import set_language, get_language, t
from ab_test import assign_user, get_strategy, record_experiment, get_experiment_results
from auth import create_token, USERS, get_current_user
from auth import create_token, USERS, hash_password

# ── FastAPI 应用 ──
app = FastAPI(title="Neowow 智能客服 API")

# ── 静态文件：FAQ 截图（统一从 assets/images/ 读取）──
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "images")
if os.path.isdir(_ASSETS_DIR):
    app.mount("/faq-images", StaticFiles(directory=_ASSETS_DIR), name="faq-images")

# CORS：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 请求日志中间件 ──
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start
        logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration:.2f}s)")
        return response
    except Exception as e:
        duration = time.time() - start
        logger.error(f"{request.method} {request.url.path} -> ERROR: {e} ({duration:.2f}s)")
        return JSONResponse(status_code=500, content={"error": "服务器内部错误"})


# ── 全局异常处理 ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"未捕获异常: {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"error": "服务器内部错误，请稍后再试"})


# ── 初始化 Agent（全局单例）──
logger.info("正在初始化 Agent...")
agent_app = build_graph()
logger.info("Agent 初始化完成，FAQ 数量: %d", len(FAQ_DATA))


# ── 数据模型 ──
class ChatRequest(BaseModel):
    user_input: str = Field(default="", max_length=500, description="用户问题")
    history: Optional[list] = Field(default=[], description="对话历史")
    images: Optional[list[str]] = Field(default=[], description="用户上传的图片 base64 列表")


class ChatResponse(BaseModel):
    response: str
    intent: str
    kb_found: bool
    kb_category: str
    chunk_found: bool
    ticket_id: str = ""
    kb_images: list = []  # FAQ 命中的截图
    is_troubleshooting: bool = False  # 是否在排查流程中
    troubleshoot_step: int = 0        # 当前排查步骤
    model_used: str = ""              # 实际使用的模型


class ErrorResponse(BaseModel):
    error: str


# ── API 鉴权 ──
API_KEY = os.getenv("API_KEY", "neowow-dev-2026")


def verify_token(authorization: str = Header(None)):
    """验证 JWT Token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少认证信息")

    # 支持 "Bearer xxx" 格式
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    try:
        from auth import decode_token
        return decode_token(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"认证失败: {str(e)}")


# ── 限流 ──
RATE_LIMIT = 200  # 每分钟最多30次请求
rate_limit_store = defaultdict(list)

def check_rate_limit(request: Request, _user: dict = Depends(verify_token)):
    """检查请求频率限制"""
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    # 清理60秒前的记录
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < 60]

    if len(rate_limit_store[ip]) >= RATE_LIMIT:
        logger.warning("限流触发: IP=%s, 请求数=%d", ip, len(rate_limit_store[ip]))
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    rate_limit_store[ip].append(now)
    return ip


# ── API 接口 ──

class LanguageRequest(BaseModel):
    lang: str = Field(..., pattern="^(zh|en)$", description="语言代码：zh 或 en")


@app.post("/api/language")
def set_language_api(request: LanguageRequest, _ip: str = Depends(check_rate_limit)):
    """切换语言"""
    set_language(request.lang)
    logger.info("语言切换为：%s", request.lang)
    return {"language": request.lang}


@app.get("/api/ab/strategy/{user_id}")
def get_user_strategy(user_id: str, _ip: str = Depends(check_rate_limit)):
    """获取用户的 A/B 测试策略"""
    return get_strategy(user_id)


@app.post("/api/ab/record")
def record_ab_experiment(request: dict, _ip: str = Depends(check_rate_limit)):
    """记录 A/B 测试数据"""
    try:
        record_experiment(
            request.get("user_id", ""),
            request.get("strategy", ""),
            request.get("question", ""),
            request.get("answer", ""),
            request.get("rating"),
        )
        return {"message": "记录成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ab/results")
def get_ab_results(_ip: str = Depends(check_rate_limit)):
    """获取 A/B 测试结果"""
    return get_experiment_results()


@app.get("/api/language")
def get_language_api(_ip: str = Depends(check_rate_limit)):
    """获取当前语言"""
    return {"language": get_language()}


@app.get("/api/health")
def health_check():
    """健康检查"""
    return {"status": "ok", "faq_count": len(FAQ_DATA)}


@app.post("/api/chat", response_model=ChatResponse, responses={500: {"model": ErrorResponse}})
def chat(request: ChatRequest, _ip: str = Depends(check_rate_limit)):
    """客服对话接口 — 自动检测 TaskID 错误并创建工单"""
    try:
        logger.info("用户提问: %s (历史: %d 轮)", request.user_input[:50], len(request.history or []) // 2)

        # ── 自动检测：用户是否发送了包含 TaskID 的报错信息 ──
        # 优化：如果用户在排查流程中提供 TaskID，优先进入排查调用工具
        error_ids = extract_error_ids(request.user_input)
        is_in_troubleshoot = False
        if request.history:
            for i in range(len(request.history) - 1, -1, -1):
                role, content_h = request.history[i]
                if role == "assistant" and "故障排查中" in content_h:
                    is_in_troubleshoot = True
                    break

        if error_ids and 'task_id' in error_ids and not is_in_troubleshoot:
            is_copyright = is_copyright_error(request.user_input)
            # 创建高优先级工单
            ticket = create_ticket(
                user_input=request.user_input,
                history=request.history or [],
                priority="high" if is_copyright else "normal",
                tags=(["版权豁免"] if is_copyright else []) + ["自动创建"],
            )
            # 把提取的 ID 追加到工单
            tickets = load_tickets()
            for t in tickets:
                if t['ticket_id'] == ticket['ticket_id']:
                    t['task_id'] = error_ids.get('task_id', '')
                    t['session_id'] = error_ids.get('session_id', '')
                    t['node_id'] = error_ids.get('node_id', '')
                    break
            save_tickets(tickets)

            if is_copyright:
                response_text = f"检测到版权限制报错，已为您自动创建高优先级工单（工单号：{ticket['ticket_id']}）。客服将在后台为您申请内容豁免，请稍候。"
            else:
                response_text = f"已收到您的报错信息，已创建工单（工单号：{ticket['ticket_id']}），客服将尽快排查。TaskID：{error_ids.get('task_id', '')}"

            logger.info("自动创建工单: %s (版权=%s)", ticket['ticket_id'], is_copyright)
            record_stat("ticket")
            return ChatResponse(
                response=response_text,
                intent="auto_ticket",
                kb_found=False,
                kb_category="",
                chunk_found=False,
                ticket_id=ticket['ticket_id'],
            )

        # ── 正常 Agent 对话流程 ──

        # ─ 从 history 恢复排查状态（多轮对话）──
        prev_troubleshoot_flow = ""
        prev_troubleshoot_step = 0
        initial_intent = ""
        if request.history:
            # 优先检查是否有"排查结束"标记
            has_ended = False
            for i in range(len(request.history) - 1, -1, -1):
                role, content = request.history[i]
                if role == "assistant" and "排查结束" in content:
                    has_ended = True
                    break
                elif role == "assistant" and "故障排查中" in content:
                    break

            if not has_ended:
                # 没有结束标记，正常恢复排查状态
                for i in range(len(request.history) - 1, -1, -1):
                    role, content = request.history[i]
                    if role == "assistant" and "故障排查中" in content:
                        # 尝试从内容中推断步骤数和 flow_id
                        import re
                        m = re.search(r'第(\d+)步', content)
                        if m:
                            prev_troubleshoot_step = int(m.group(1)) - 1  # 0-indexed
                        fm = re.search(r'flow:(\w+)', content)
                        if fm:
                            prev_troubleshoot_flow = fm.group(1)
                        else:
                            prev_troubleshoot_flow = "resumed"  # 标记为恢复模式
                        initial_intent = "troubleshoot"  # 强制走排查节点
                        break

        result = agent_app.invoke({
            "user_input": request.user_input,
            "intent": initial_intent,
            "response": "",
            "kb_found": False,
            "kb_reference": "",
            "kb_category": "",
            "kb_images": [],
            "chunk_found": False,
            "chunk_reference": "",
            "history": request.history or [],
            "ticket_id": "",
            "ticket_summary": "",
            "troubleshoot_flow": prev_troubleshoot_flow,
            "troubleshoot_step": prev_troubleshoot_step,
            "user_memory": {},
            "model_used": "",
            "user_images": request.images or [],
            "troubleshoot_options": [],
        })

        response_text = result.get("response", "")
        kb_found = result.get("kb_found", False)
        source = "知识库" if kb_found else "大模型"
        logger.info("回答来源: %s | 分类: %s | 回答长度: %d 字", source, result.get("kb_category", "-"), len(response_text))
        # 记录统计
        stat_type = "kb" if kb_found else "llm"
        record_stat(stat_type)

        # 排查状态
        is_troubleshooting = bool(result.get("troubleshoot_flow", ""))
        troubleshoot_step = result.get("troubleshoot_step", 0)
        if is_troubleshooting:
            stat_type = "troubleshoot"
            record_stat(stat_type)

        return ChatResponse(
            response=response_text,
            intent=result.get("intent", ""),
            kb_found=kb_found,
            kb_category=result.get("kb_category", ""),
            chunk_found=result.get("chunk_found", False),
            ticket_id=result.get("ticket_id", ""),
            kb_images=result.get("kb_images", []),
            is_troubleshooting=is_troubleshooting,
            troubleshoot_step=troubleshoot_step,
            model_used=result.get("model_used", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("处理聊天请求时出错: %s", str(e))
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后再试")


@app.get("/api/pending")
def get_pending(_ip: str = Depends(check_rate_limit)):
    """获取待确认 FAQ 列表"""
    try:
        pending = load_pending_faqs()
        items = []
        for real_idx, p in enumerate(pending):
            if p['status'] == 'pending':
                item = dict(p)
                item['_realIndex'] = real_idx
                items.append(item)
        logger.info("返回待确认列表: %d 条", len(items))
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.exception("获取待确认列表失败: %s", str(e))
        raise HTTPException(status_code=500, detail="获取数据失败")


class FaqCreateRequest(BaseModel):
    question: str = Field(..., min_length=1, description="问题")
    answer: str = Field(..., min_length=1, description="答案")
    category: str = Field(..., description="分类")
    images: list = Field(default=[], description="截图列表")


@app.post("/api/faqs")
def add_faq(request: FaqCreateRequest, _ip: str = Depends(check_rate_limit)):
    """新增 FAQ"""
    try:
        from tools_vector import init_knowledge_base
        FAQ_DATA.append((request.question, request.answer, request.category, request.images))
        init_knowledge_base()
        logger.info("新增 FAQ: %s", request.question)
        return {"message": "已添加", "question": request.question}
    except Exception as e:
        logger.exception("新增 FAQ 失败: %s", str(e))
        raise HTTPException(status_code=500, detail="添加失败")


@app.put("/api/faqs/{index}")
def update_faq(index: int, request: FaqCreateRequest, _ip: str = Depends(check_rate_limit)):
    """更新 FAQ"""
    try:
        from tools_vector import init_knowledge_base
        if index < 0 or index >= len(FAQ_DATA):
            raise HTTPException(status_code=404, detail="FAQ 不存在")
        FAQ_DATA[index] = (request.question, request.answer, request.category, request.images)
        init_knowledge_base()
        logger.info("更新 FAQ: %s", request.question)
        return {"message": "已更新", "question": request.question}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("更新 FAQ 失败: %s", str(e))
        raise HTTPException(status_code=500, detail="更新失败")


@app.delete("/api/faqs/{index}")
def delete_faq(index: int, _ip: str = Depends(check_rate_limit)):
    """删除 FAQ（持久化）"""
    try:
        import json
        from tools_vector import init_knowledge_base, APPROVED_FAQ_FILE

        if index < 0 or index >= len(FAQ_DATA):
            raise HTTPException(status_code=404, detail="FAQ 不存在")

        removed = FAQ_DATA.pop(index)
        removed_question = removed[0]

        # 从文件中删除对应的 FAQ
        try:
            with open(APPROVED_FAQ_FILE, 'r', encoding='utf-8') as f:
                approved = json.load(f)
            # 按问题匹配删除（因为 FAQ_DATA 和文件顺序一致）
            new_approved = [f for f in approved if f.get('question') != removed_question]
            if len(new_approved) < len(approved):
                with open(APPROVED_FAQ_FILE, 'w', encoding='utf-8') as f:
                    json.dump(new_approved, f, ensure_ascii=False, indent=2)
                logger.info("已从文件删除 FAQ: %s", removed_question)
            else:
                logger.warning("FAQ 未从文件删除（硬编码 FAQ）: %s", removed_question)
        except Exception as file_err:
            logger.warning("删除 FAQ 文件记录失败: %s", str(file_err))

        # 重新初始化知识库
        init_knowledge_base()
        logger.info("删除 FAQ: %s", removed_question)
        return {"message": "已删除", "question": removed_question}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("删除 FAQ 失败: %s", str(e))
        raise HTTPException(status_code=500, detail="删除失败")


@app.get("/api/faqs")
def get_faqs(_ip: str = Depends(check_rate_limit)):
    """获取当前知识库所有 FAQ"""
    items = []
    for i, item in enumerate(FAQ_DATA):
        q, a, c = item[0], item[1], item[2]
        images = item[3] if len(item) > 3 else []
        items.append({"index": i, "question": q, "answer": a, "category": c, "images": images})
    return {"items": items, "total": len(FAQ_DATA)}


@app.post("/api/approve/{index}")
def approve_faq(index: int, _ip: str = Depends(check_rate_limit)):
    """批准 FAQ 提案"""
    try:
        logger.info("批准提案: index=%d", index)
        success = approve_pending_faq(index)
        if success:
            logger.info("提案 %d 已批准，已重建向量索引", index)
            return {"message": "已批准", "index": index}
        raise HTTPException(status_code=400, detail="批准失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("批准提案失败: %s", str(e))
        raise HTTPException(status_code=500, detail="操作失败")


@app.post("/api/reject/{index}")
def reject_faq(index: int, _ip: str = Depends(check_rate_limit)):
    """拒绝 FAQ 提案"""
    try:
        logger.info("拒绝提案: index=%d", index)
        success = reject_pending_faq(index)
        if success:
            logger.info("提案 %d 已拒绝", index)
            return {"message": "已拒绝", "index": index}
        raise HTTPException(status_code=400, detail="拒绝失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("拒绝提案失败: %s", str(e))
        raise HTTPException(status_code=500, detail="操作失败")


# ── 用户反馈 ──
FEEDBACK_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "feedback.json")


def load_feedback() -> list:
    try:
        with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_feedback(feedback: list):
    with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)


class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="消息 ID")
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    comment: Optional[str] = Field(default="", description="可选评论")


@app.post("/api/feedback")
def submit_feedback(request: FeedbackRequest, _ip: str = Depends(check_rate_limit)):
    """提交用户反馈"""
    try:
        feedback = load_feedback()
        feedback.append({
            "message_id": request.message_id,
            "rating": request.rating,
            "comment": request.comment,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        save_feedback(feedback)
        logger.info("收到反馈：评分=%d", request.rating)
        return {"message": "感谢你的反馈！"}
    except Exception as e:
        logger.exception("提交反馈失败：%s", str(e))
        raise HTTPException(status_code=500, detail="提交失败")


@app.get("/api/feedback/stats")
def get_feedback_stats(_ip: str = Depends(check_rate_limit)):
    """获取反馈统计"""
    try:
        feedback = load_feedback()
        total = len(feedback)
        if total == 0:
            return {"total": 0, "average": 0, "distribution": {}}

        avg = sum(f['rating'] for f in feedback) / total
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for f in feedback:
            dist[f['rating']] = dist.get(f['rating'], 0) + 1

        return {"total": total, "average": round(avg, 2), "distribution": dist}
    except Exception as e:
        logger.exception("获取反馈统计失败：%s", str(e))
        raise HTTPException(status_code=500, detail="获取统计失败")


# ── 成本统计 ──
STATS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stats.json")


def load_stats() -> dict:
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "total_calls": 0,
            "total_tokens": 0,
            "kb_hits": 0,
            "llm_calls": 0,
            "tickets_created": 0,
            "daily": {},
        }


def save_stats(stats: dict):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def record_stat(stat_type: str, tokens: int = 0):
    """记录一次 API 调用统计"""
    stats = load_stats()
    stats["total_calls"] += 1
    stats["total_tokens"] += tokens

    if stat_type == "kb":
        stats["kb_hits"] += 1
    elif stat_type == "llm":
        stats["llm_calls"] += 1
    elif stat_type == "ticket":
        stats["tickets_created"] += 1
    elif stat_type == "troubleshoot":
        stats.setdefault("troubleshoot_count", 0)
        stats["troubleshoot_count"] += 1
    elif stat_type == "fallback":
        stats.setdefault("fallback_count", 0)
        stats["fallback_count"] += 1

    # 按日期统计
    today = datetime.now().strftime("%Y-%m-%d")
    if today not in stats["daily"]:
        stats["daily"][today] = {"calls": 0, "tokens": 0, "kb": 0, "llm": 0, "troubleshoot": 0, "fallback": 0}
    stats["daily"][today]["calls"] += 1
    stats["daily"][today]["tokens"] += tokens
    stats["daily"][today].setdefault("troubleshoot", 0)
    stats["daily"][today].setdefault("fallback", 0)
    if stat_type == "kb":
        stats["daily"][today]["kb"] += 1
    elif stat_type == "llm":
        stats["daily"][today]["llm"] += 1
    elif stat_type == "fallback":
        stats["daily"][today]["fallback"] += 1
    elif stat_type == "troubleshoot":
        stats["daily"][today]["troubleshoot"] += 1

    save_stats(stats)
    return stats


@app.get("/api/stats")
def get_stats(_ip: str = Depends(check_rate_limit)):
    """获取成本统计"""
    try:
        stats = load_stats()
        # 计算命中率
        total = stats["kb_hits"] + stats["llm_calls"]
        hit_rate = round(stats["kb_hits"] / total * 100, 2) if total > 0 else 0
        return {
            **stats,
            "kb_hit_rate": hit_rate,
        }
    except Exception as e:
        logger.exception("获取统计失败：%s", str(e))
        raise HTTPException(status_code=500, detail="获取统计失败")


@app.get("/api/stats/dashboard")
def get_dashboard_stats(_ip: str = Depends(check_rate_limit)):
    """获取看板统计数据（聚合 + 趋势）"""
    try:
        stats = load_stats()
        total = stats["kb_hits"] + stats["llm_calls"]
        hit_rate = round(stats["kb_hits"] / total * 100, 2) if total > 0 else 0

        # 满意度统计
        feedback = load_feedback()
        fb_total = len(feedback)
        fb_avg = round(sum(f['rating'] for f in feedback) / fb_total, 2) if fb_total > 0 else 0
        fb_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for f in feedback:
            r = f.get('rating', 0)
            if r in fb_dist:
                fb_dist[r] += 1

        # 每日趋势（按日期排序）
        daily_trend = []
        for date in sorted(stats.get("daily", {}).keys()):
            d = stats["daily"][date]
            day_total = d.get("kb", 0) + d.get("llm", 0)
            day_hit = round(d.get("kb", 0) / day_total * 100, 2) if day_total > 0 else 0
            daily_trend.append({
                "date": date,
                "calls": d.get("calls", 0),
                "kb": d.get("kb", 0),
                "llm": d.get("llm", 0),
                "troubleshoot": d.get("troubleshoot", 0),
                "fallback": d.get("fallback", 0),
                "hit_rate": day_hit,
            })

        return {
            "summary": {
                "total_calls": stats["total_calls"],
                "kb_hits": stats["kb_hits"],
                "llm_calls": stats["llm_calls"],
                "tickets_created": stats.get("tickets_created", 0),
                "troubleshoot_count": stats.get("troubleshoot_count", 0),
                "fallback_count": stats.get("fallback_count", 0),
                "kb_hit_rate": hit_rate,
                "total_days": len(stats.get("daily", {})),
            },
            "daily_trend": daily_trend,
            "feedback_stats": {
                "total": fb_total,
                "average": fb_avg,
                "distribution": fb_dist,
            },
            "ab_test": get_experiment_results(),
        }
    except Exception as e:
        logger.exception("获取看板统计失败：%s", str(e))
        raise HTTPException(status_code=500, detail="获取看板统计失败")


@app.post("/api/stats/fallback")
def record_fallback(_ip: str = Depends(check_rate_limit)):
    """记录模型降级事件"""
    record_stat("fallback")
    return {"message": "已记录降级"}


# ── 工单 API ──

class TicketCreateRequest(BaseModel):
    user_input: str = Field(default="", max_length=500, description="用户问题")
    history: Optional[list] = Field(default=[], description="对话历史")


class TicketReplyRequest(BaseModel):
    reply: str = Field(..., min_length=1, description="客服回复内容")


# ── 认证 API ─

class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    token: str
    user: dict


@app.post("/api/auth/login")
def login(request: LoginRequest):
    """用户登录"""
    username = request.username
    password = request.password

    # 验证用户
    user = USERS.get(username)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 生成 Token
    token = create_token(username, user["role"], user["name"])

    return LoginResponse(
        token=token,
        user={
            "username": username,
            "role": user["role"],
            "name": user["name"],
        }
    )


@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return user


@app.post("/api/tickets")
def create_ticket_api(request: TicketCreateRequest, _ip: str = Depends(check_rate_limit)):
    """创建工单"""
    try:
        ticket = create_ticket(request.user_input, request.history or [])
        logger.info("工单创建成功：%s", ticket['ticket_id'])
        return {
            "ticket_id": ticket['ticket_id'],
            "message": f"工单已创建，编号：{ticket['ticket_id']}。客服将尽快处理。",
        }
    except Exception as e:
        logger.exception("创建工单失败：%s", str(e))
        raise HTTPException(status_code=500, detail="创建工单失败")


@app.get("/api/tickets")
def get_tickets(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    _ip: str = Depends(check_rate_limit)
):
    """获取工单列表（支持分页、状态筛选、搜索）"""
    try:
        tickets = load_tickets()

        # 状态筛选
        if status:
            tickets = [t for t in tickets if t['status'] == status]

        # 搜索（问题内容或工单号）
        if search:
            search_lower = search.lower()
            tickets = [t for t in tickets if
                       search_lower in t.get('question', '').lower() or
                       search_lower in t.get('ticket_id', '').lower()]

        # 倒序排列，最新的在前
        tickets.reverse()

        # 分页
        total = len(tickets)
        start = (page - 1) * page_size
        end = start + page_size
        page_tickets = tickets[start:end]

        logger.info("返回工单列表：%d 条 (筛选：%s, 搜索：%s, 页码：%d/%d)",
                   len(page_tickets), status or "全部", search or "无", page, (total + page_size - 1) // page_size)
        return {"items": page_tickets, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        logger.exception("获取工单列表失败：%s", str(e))
        raise HTTPException(status_code=500, detail="获取工单失败")


@app.delete("/api/tickets/{ticket_id}")
def delete_ticket(ticket_id: str, _ip: str = Depends(check_rate_limit)):
    """删除工单"""
    try:
        tickets = load_tickets()
        new_tickets = [t for t in tickets if t['ticket_id'] != ticket_id]
        if len(new_tickets) == len(tickets):
            raise HTTPException(status_code=404, detail="工单不存在")
        save_tickets(new_tickets)
        logger.info("删除工单：%s", ticket_id)
        return {"message": "已删除", "ticket_id": ticket_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("删除工单失败：%s", str(e))
        raise HTTPException(status_code=500, detail="删除工单失败")


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str, _ip: str = Depends(check_rate_limit)):
    """获取单个工单详情"""
    try:
        tickets = load_tickets()
        for t in tickets:
            if t['ticket_id'] == ticket_id:
                return t
        raise HTTPException(status_code=404, detail="工单不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取工单详情失败：%s", str(e))
        raise HTTPException(status_code=500, detail="获取工单失败")


@app.post("/api/tickets/{ticket_id}/reply")
def reply_ticket(ticket_id: str, request: TicketReplyRequest, _ip: str = Depends(check_rate_limit)):
    """客服回复工单"""
    try:
        tickets = load_tickets()
        for t in tickets:
            if t['ticket_id'] == ticket_id:
                t['reply'] = request.reply
                t['status'] = 'resolved'
                t['replied_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_tickets(tickets)
                logger.info("工单 %s 已回复", ticket_id)
                return {"message": "回复成功", "ticket_id": ticket_id}
        raise HTTPException(status_code=404, detail="工单不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("回复工单失败：%s", str(e))
        raise HTTPException(status_code=500, detail="回复失败")


@app.post("/api/tickets/{ticket_id}/status")
def update_ticket_status(ticket_id: str, status: str, _ip: str = Depends(check_rate_limit)):
    """更新工单状态（pending/in_progress/resolved/closed）"""
    try:
        tickets = load_tickets()
        for t in tickets:
            if t['ticket_id'] == ticket_id:
                t['status'] = status
                save_tickets(tickets)
                logger.info("工单 %s 状态更新为 %s", ticket_id, status)
                return {"message": "状态已更新", "ticket_id": ticket_id, "status": status}
        raise HTTPException(status_code=404, detail="工单不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("更新工单状态失败：%s", str(e))
        raise HTTPException(status_code=500, detail="更新失败")


# ── 启动 ──
# ── 流式对话接口 ─────────────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, _ip: str = Depends(check_rate_limit)):
    """客服对话接口（流式）— SSE 逐字推送"""
    try:
        logger.info("用户提问 (流式): %s (历史: %d 轮)", request.user_input[:50], len(request.history or []) // 2)

        # 自动检测 TaskID 错误
        error_ids = extract_error_ids(request.user_input)
        is_in_troubleshoot = False
        if request.history:
            for i in range(len(request.history) - 1, -1, -1):
                role, content_h = request.history[i]
                if role == "assistant" and "故障排查中" in content_h:
                    is_in_troubleshoot = True
                    break

        if error_ids and 'task_id' in error_ids and not is_in_troubleshoot:
            is_copyright = is_copyright_error(request.user_input)
            ticket = create_ticket(
                user_input=request.user_input,
                history=request.history or [],
                priority="high" if is_copyright else "normal",
                tags=(["版权豁免"] if is_copyright else []) + ["自动创建"],
            )
            tickets = load_tickets()
            for t in tickets:
                if t['ticket_id'] == ticket['ticket_id']:
                    t['task_id'] = error_ids.get('task_id', '')
                    t['session_id'] = error_ids.get('session_id', '')
                    t['node_id'] = error_ids.get('node_id', '')
                    break
            save_tickets(tickets)

            if is_copyright:
                response_text = f"检测到版权限制报错，已为您自动创建高优先级工单（工单号：{ticket['ticket_id']}）。客服将在后台为您申请内容豁免，请稍候。"
            else:
                response_text = f"已收到您的报错信息，已创建工单（工单号：{ticket['ticket_id']}），客服将尽快排查。TaskID：{error_ids.get('task_id', '')}"

            logger.info("自动创建工单 (流式): %s (版权=%s)", ticket['ticket_id'], is_copyright)
            record_stat("ticket")

            # 一次性返回（工单不需要流式）
            async def error_gen():
                yield f"data: {json.dumps({'response': response_text, 'intent': 'auto_ticket', 'kb_found': False, 'ticket_id': ticket['ticket_id']}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(error_gen(), media_type="text/event-stream")

        # 恢复排查状态
        prev_troubleshoot_flow = ""
        prev_troubleshoot_step = 0
        initial_intent = ""
        if request.history:
            # 优先检查是否有"排查结束"标记（倒序查找最新的一条）
            has_ended = False
            for i in range(len(request.history) - 1, -1, -1):
                role, content = request.history[i]
                if role == "assistant" and "排查结束" in content:
                    has_ended = True
                    break
                elif role == "assistant" and "故障排查中" in content:
                    # 找到排查标记，停止检查
                    break

            if not has_ended:
                # 没有结束标记，正常恢复排查状态
                for i in range(len(request.history) - 1, -1, -1):
                    role, content = request.history[i]
                    if role == "assistant" and "故障排查中" in content:
                        import re
                        m = re.search(r'第(\d+)步', content)
                        if m:
                            prev_troubleshoot_step = int(m.group(1)) - 1
                        # 提取 flow_id
                        fm = re.search(r'flow:(\w+)', content)
                        if fm:
                            prev_troubleshoot_flow = fm.group(1)
                        else:
                            prev_troubleshoot_flow = "resumed"
                        initial_intent = "troubleshoot"
                        break

        # 调用 Agent
        result = agent_app.invoke({
            "user_input": request.user_input,
            "intent": initial_intent,
            "response": "",
            "kb_found": False,
            "kb_reference": "",
            "kb_category": "",
            "kb_images": [],
            "chunk_found": False,
            "chunk_reference": "",
            "history": request.history or [],
            "ticket_id": "",
            "ticket_summary": "",
            "troubleshoot_flow": prev_troubleshoot_flow,
            "troubleshoot_step": prev_troubleshoot_step,
            "user_memory": {},
            "model_used": "",
            "user_images": request.images or [],
            "troubleshoot_options": [],
        })

        response_text = result.get("response", "")
        kb_found = result.get("kb_found", False)
        source = "知识库" if kb_found else "大模型"
        logger.info("回答来源 (流式): %s | 分类: %s | 回答长度: %d 字", source, result.get("kb_category", "-"), len(response_text))

        # 记录统计
        stat_type = "kb" if kb_found else "llm"
        record_stat(stat_type)

        # 排查状态
        is_troubleshooting = bool(result.get("troubleshoot_flow", ""))
        troubleshoot_step = result.get("troubleshoot_step", 0)
        if is_troubleshooting:
            record_stat("troubleshoot")

        # SSE 流式推送
        async def stream_gen():
            # 推送元数据
            meta = {
                "intent": result.get("intent", ""),
                "kb_found": kb_found,
                "kb_category": result.get("kb_category", ""),
                "chunk_found": result.get("chunk_found", False),
                "ticket_id": result.get("ticket_id", ""),
                "kb_images": result.get("kb_images", []),
                "is_troubleshooting": is_troubleshooting,
                "troubleshoot_step": troubleshoot_step,
                "troubleshoot_flow": result.get("troubleshoot_flow", ""),
                "troubleshoot_options": result.get("troubleshoot_options", []),
                "model_used": result.get("model_used", ""),
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

            # 逐字推送回答（加延迟让流式效果更明显）
            import asyncio
            for i, char in enumerate(response_text):
                yield f"data: {json.dumps({'chunk': char}, ensure_ascii=False)}\n\n"
                if i % 3 == 0:  # 每 3 个字符延迟一次
                    await asyncio.sleep(0.03)

            # 结束标记
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_gen(), media_type="text/event-stream")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("处理流式聊天请求时出错：%s", str(e))
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后再试")


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Neowow 智能客服 API 启动中...")
    logger.info("地址: http://0.0.0.0:8001")
    logger.info("日志目录: %s", LOG_DIR)
    logger.info("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8001)


