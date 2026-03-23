"""OpenAI-compatible router (Phase 4: non-stream chat completions)."""

import time
import logging
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from app.agent.agent import get_agent
from app.config import get_settings
from app.openai_compat.adapters import (
    internal_answer_to_openai_response,
    openai_messages_to_internal,
)
from app.openai_compat.schemas import (
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    ModelCard,
    ModelsListResponse,
)
from app.openai_compat.stream import build_chat_completion_sse
from app.openai_compat.utils import authenticate_openai_request, openai_error

router = APIRouter()
logger = logging.getLogger(__name__)


def _preview(text: str, max_len: int = 120) -> str:
    """截取文本用于日志预览，换行符替换为空格。"""
    text = (text or "").strip().replace("\n", " ")
    return (text[:max_len] + "…") if len(text) > max_len else text


def _payload_preview(payload: "ChatCompletionsRequest") -> str:
    """构造请求 payload 的简洁预览行。"""
    last_user = next(
        (m.content for m in reversed(payload.messages) if m.role == "user"), ""
    )
    content_str = last_user if isinstance(last_user, str) else str(last_user)
    return (
        f"model={payload.model} stream={payload.stream} "
        f"temperature={payload.temperature} max_tokens={payload.max_tokens} "
        f"last_user_msg={_preview(content_str, 80)!r}"
    )


def _stream_with_logging(
    chunk_iter,
    *,
    log: logging.Logger,
    request_id: str,
    auth_source: str,
    model: str,
    start: float,
):
    """包装 agent.stream() 迭代器，流结束后打印回答预览。"""
    collected = []
    for chunk in chunk_iter:
        collected.append(chunk)
        yield chunk
    answer = "".join(collected)
    log.info(
        "openai_compat /v1/chat/completions stream_done | request_id=%s auth=%s model=%s duration_ms=%.1f answer_preview=%r",
        request_id,
        auth_source,
        model,
        (time.time() - start) * 1000,
        _preview(answer),
    )


def _allowed_models(settings) -> set[str]:
    items = {
        settings.openai_compat_model_id,
        settings.dashscope_model,
        settings.openai_compat_model_name,
    }
    return {i for i in items if i}


@router.get("/models", response_model=ModelsListResponse)
async def list_models(request: Request, response: Response):
    """OpenAI-compatible models list endpoint."""
    start = time.time()
    settings = get_settings()

    ok, request_id, auth_source, auth_error = authenticate_openai_request(request, settings.api_key)
    response.headers["X-Request-Id"] = request_id
    if not ok:
        logger.warning(
            "openai_compat /v1/models failed | request_id=%s auth=%s success=false duration_ms=%.1f",
            request_id,
            auth_source,
            (time.time() - start) * 1000,
        )
        auth_error.headers["X-Request-Id"] = request_id
        return auth_error

    created = int(time.time())

    model_id = settings.openai_compat_model_id or settings.dashscope_model
    model_name = settings.openai_compat_model_name or model_id

    result = ModelsListResponse(
        data=[
            ModelCard(
                id=model_id,
                created=created,
                owned_by=model_name,
            )
        ]
    )
    logger.info(
        "openai_compat /v1/models success | request_id=%s auth=%s model=%s duration_ms=%.1f",
        request_id,
        auth_source,
        model_id,
        (time.time() - start) * 1000,
    )
    return result


@router.post("/chat/completions", response_model=ChatCompletionsResponse)
async def chat_completions(request: Request, payload: ChatCompletionsRequest, response: Response):
    """OpenAI-compatible non-stream chat completions endpoint."""
    start = time.time()
    settings = get_settings()
    model = payload.model
    stream = payload.stream

    ok, request_id, auth_source, auth_error = authenticate_openai_request(request, settings.api_key)
    response.headers["X-Request-Id"] = request_id
    if not ok:
        logger.warning(
            "openai_compat /v1/chat/completions failed | request_id=%s auth=%s model=%s stream=%s reason=auth duration_ms=%.1f",
            request_id,
            auth_source,
            model,
            stream,
            (time.time() - start) * 1000,
        )
        auth_error.headers["X-Request-Id"] = request_id
        return auth_error

    allowed = _allowed_models(settings)
    if payload.model not in allowed:
        err = openai_error(
            status_code=404,
            message=f"The model '{payload.model}' does not exist",
            error_type="invalid_request_error",
            code="model_not_found",
            param="model",
        )
        err.headers["X-Request-Id"] = request_id
        logger.warning(
            "openai_compat /v1/chat/completions failed | request_id=%s auth=%s model=%s stream=%s reason=model_not_found duration_ms=%.1f",
            request_id,
            auth_source,
            model,
            stream,
            (time.time() - start) * 1000,
        )
        return err

    if not payload.messages:
        err = openai_error(
            status_code=400,
            message="messages must not be empty",
            error_type="invalid_request_error",
            code="invalid_messages",
            param="messages",
        )
        err.headers["X-Request-Id"] = request_id
        logger.warning(
            "openai_compat /v1/chat/completions failed | request_id=%s auth=%s model=%s stream=%s reason=empty_messages duration_ms=%.1f",
            request_id,
            auth_source,
            model,
            stream,
            (time.time() - start) * 1000,
        )
        return err

    query, chat_history = openai_messages_to_internal(payload.messages)

    # ── 请求预览日志 ──────────────────────────────────────────────
    logger.info(
        "openai_compat /v1/chat/completions recv | request_id=%s auth=%s %s",
        request_id,
        auth_source,
        _payload_preview(payload),
    )

    if not query:
        err = openai_error(
            status_code=400,
            message="messages must contain at least one non-empty user message",
            error_type="invalid_request_error",
            code="invalid_messages",
            param="messages",
        )
        err.headers["X-Request-Id"] = request_id
        logger.warning(
            "openai_compat /v1/chat/completions failed | request_id=%s auth=%s model=%s stream=%s reason=no_user_query duration_ms=%.1f",
            request_id,
            auth_source,
            model,
            stream,
            (time.time() - start) * 1000,
        )
        return err

    try:
        agent = get_agent()
        if payload.stream:
            chunk_iter = _stream_with_logging(
                agent.stream(query=query, chat_history=chat_history),
                log=logger,
                request_id=request_id,
                auth_source=auth_source,
                model=model,
                start=start,
            )
            sse = StreamingResponse(
                build_chat_completion_sse(model=payload.model, chunks=chunk_iter),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
            sse.headers["X-Request-Id"] = request_id
            return sse
        answer = agent.run(query=query, chat_history=chat_history)
        result = internal_answer_to_openai_response(
            model=payload.model,
            query=query,
            answer=answer,
        )
        logger.info(
            "openai_compat /v1/chat/completions success | request_id=%s auth=%s model=%s stream=%s duration_ms=%.1f answer_preview=%r",
            request_id,
            auth_source,
            model,
            stream,
            (time.time() - start) * 1000,
            _preview(answer),
        )
        return result
    except Exception as exc:
        err = openai_error(
            status_code=500,
            message=f"Internal error: {str(exc)}",
            error_type="server_error",
            code="internal_error",
        )
        err.headers["X-Request-Id"] = request_id
        logger.exception(
            "openai_compat /v1/chat/completions failed | request_id=%s auth=%s model=%s stream=%s reason=internal_error duration_ms=%.1f",
            request_id,
            auth_source,
            model,
            stream,
            (time.time() - start) * 1000,
        )
        return err
