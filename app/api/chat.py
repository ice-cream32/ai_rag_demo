"""对话接口 - Agent 统一入口"""

import logging
import time
from typing import Optional, List, Dict, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agent.agent import get_agent

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== 请求 / 响应模型 ====================

class ChatRequest(BaseModel):
    """对话请求"""
    query: str
    chat_history: Optional[List[Dict[str, str]]] = None  # [{"role": "user", "content": "..."}]


class ChatResponse(BaseModel):
    """对话响应"""
    code: int           # 业务状态码: 200 成功 / 400 参数错误 / 500 服务异常
    message: str        # 人类可读描述
    query: str
    answer: Optional[str] = None
    processing_time_ms: Optional[float] = None


def ok(query: str, answer: str, ms: float) -> ChatResponse:
    return ChatResponse(code=200, message="success", query=query, answer=answer, processing_time_ms=ms)


def err(code: int, msg: str, query: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"code": code, "message": msg, "query": query, "answer": None, "processing_time_ms": None},
    )


# ==================== API 端点 ====================

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Agent 对话接口

    统一处理料号解析、参数计算、对比、BOM、知识库问答等所有问题。
    Agent 会自动判断意图并调用相应的技能（Tool）。

    响应体 code 说明:
      200 - 成功
      400 - 请求参数错误 (query 为空)
      500 - 服务内部异常
    """
    if not request.query.strip():
        return err(400, "query 不能为空", request.query)

    start = time.time()

    try:
        agent = get_agent()
        answer = agent.run(
            query=request.query,
            chat_history=request.chat_history,
        )
        ms = round((time.time() - start) * 1000, 1)
        return ok(request.query, answer, ms)

    except Exception as e:
        logger.error(f"对话处理失败: {str(e)}", exc_info=True)
        return err(500, f"对话处理失败: {str(e)}", request.query)
