"""FastAPI 后端 — 客服Agent API服务"""
import sys
import os

# 将父目录加入路径，以导入现有的 graph/nodes/tools 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

# 导入现有模块
from graph import build_graph
from tools_vector import (
    load_pending_faqs,
    approve_pending_faq,
    reject_pending_faq,
    FAQ_DATA,
)

# ── FastAPI 应用 ──
app = FastAPI(title="Neowow 智能客服 API")

# CORS：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 初始化 Agent（全局单例）──
agent_app = build_graph()


# ── 数据模型 ──
class ChatRequest(BaseModel):
    user_input: str
    history: Optional[list] = []  # [(role, content), ...]


class ChatResponse(BaseModel):
    response: str
    intent: str
    kb_found: bool
    kb_category: str
    chunk_found: bool
    ticket_id: str = ""


# ── API 接口 ──

@app.get("/api/health")
def health_check():
    """健康检查"""
    return {"status": "ok", "faq_count": len(FAQ_DATA)}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """客服对话接口"""
    try:
        result = agent_app.invoke({
            "user_input": request.user_input,
            "intent": "",
            "response": "",
            "kb_found": False,
            "kb_reference": "",
            "kb_category": "",
            "chunk_found": False,
            "chunk_reference": "",
            "history": request.history or [],
            "ticket_id": "",
            "ticket_summary": "",
        })

        return ChatResponse(
            response=result.get("response", ""),
            intent=result.get("intent", ""),
            kb_found=result.get("kb_found", False),
            kb_category=result.get("kb_category", ""),
            chunk_found=result.get("chunk_found", False),
            ticket_id=result.get("ticket_id", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pending")
def get_pending():
    """获取待确认 FAQ 列表"""
    pending = load_pending_faqs()
    items = []
    for real_idx, p in enumerate(pending):
        if p['status'] == 'pending':
            item = dict(p)
            item['_realIndex'] = real_idx
            items.append(item)
    return {"items": items, "total": len(items)}


@app.get("/api/faqs")
def get_faqs():
    """获取当前知识库所有 FAQ"""
    return {
        "items": [
            {"index": i, "question": q, "answer": a, "category": c}
            for i, (q, a, c) in enumerate(FAQ_DATA)
        ],
        "total": len(FAQ_DATA),
    }


@app.post("/api/approve/{index}")
def approve_faq(index: int):
    """批准 FAQ 提案"""
    success = approve_pending_faq(index)
    if success:
        return {"message": "已批准", "index": index}
    raise HTTPException(status_code=400, detail="批准失败")


@app.post("/api/reject/{index}")
def reject_faq(index: int):
    """拒绝 FAQ 提案"""
    success = reject_pending_faq(index)
    if success:
        return {"message": "已拒绝", "index": index}
    raise HTTPException(status_code=400, detail="拒绝失败")


# ── 启动 ──
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
