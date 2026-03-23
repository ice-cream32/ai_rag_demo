"""SSE streaming helpers for OpenAI-compatible chat completions."""

import json
import time
import uuid
from typing import Iterable, List, Optional


def _split_text(text: str, max_len: int = 40) -> List[str]:
    """Pseudo-stream split: sentence-first, then fixed-length chunks."""
    if not text:
        return []

    separators = {"。", "！", "？", "\n", ".", "!", "?"}
    sentences: List[str] = []
    buffer = ""

    for ch in text:
        buffer += ch
        if ch in separators:
            sentences.append(buffer)
            buffer = ""
    if buffer:
        sentences.append(buffer)

    chunks: List[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_len:
            chunks.append(sentence)
        else:
            for i in range(0, len(sentence), max_len):
                chunks.append(sentence[i:i + max_len])

    return chunks


def _sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_chat_completion_sse(
    model: str,
    answer: Optional[str] = None,
    chunks: Optional[Iterable[str]] = None,
) -> Iterable[str]:
    """Build OpenAI-compatible SSE stream for chat.completions.

    - `chunks` is preferred for true streaming (token/chunk-by-chunk).
    - `answer` keeps backward compatibility (pseudo-stream split).
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    # First chunk with assistant role
    yield _sse_data(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": None,
                }
            ],
        }
    )

    if chunks is None:
        chunks = _split_text(answer or "")

    for chunk in chunks:
        if not chunk:
            continue
        yield _sse_data(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None,
                    }
                ],
            }
        )

    # Final chunk
    yield _sse_data(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": ""},
                    "finish_reason": "stop",
                }
            ],
        }
    )

    # End marker
    yield "data: [DONE]\n\n"
