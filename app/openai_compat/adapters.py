"""Adapters between OpenAI-compatible schema and internal agent chat schema."""

import math
import time
import uuid
from typing import Dict, List, Tuple

from app.openai_compat.schemas import (
    AssistantMessage,
    ChatChoice,
    ChatCompletionsResponse,
    ChatMessage,
    Usage,
)


def _content_to_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item.get("text", "")))
                elif "content" in item:
                    parts.append(str(item.get("content", "")))
            else:
                parts.append(str(item))
        return "\n".join([p for p in parts if p])
    return str(content)


def openai_messages_to_internal(messages: List[ChatMessage]) -> Tuple[str, List[Dict[str, str]]]:
    """
    Convert OpenAI messages into current internal chat payload:
    - query: last non-empty user message
    - chat_history: prior user/assistant messages only
    """
    query = ""
    history: List[Dict[str, str]] = []

    for msg in messages:
        role = (msg.role or "").strip().lower()
        content = _content_to_text(msg.content).strip()
        if role not in {"user", "assistant"}:
            continue
        if not content:
            continue
        history.append({"role": role, "content": content})
        if role == "user":
            query = content

    if query:
        # remove the last user message from history because it becomes query
        for idx in range(len(history) - 1, -1, -1):
            if history[idx]["role"] == "user" and history[idx]["content"] == query:
                del history[idx]
                break

    return query, history


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # lightweight estimate for compatibility output only
    return max(1, math.ceil(len(text) / 4))


def internal_answer_to_openai_response(model: str, query: str, answer: str) -> ChatCompletionsResponse:
    prompt_tokens = _estimate_tokens(query)
    completion_tokens = _estimate_tokens(answer)
    usage = Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )

    return ChatCompletionsResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
        created=int(time.time()),
        model=model,
        choices=[
            ChatChoice(
                index=0,
                message=AssistantMessage(content=answer),
                finish_reason="stop",
            )
        ],
        usage=usage,
    )
