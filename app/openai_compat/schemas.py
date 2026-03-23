"""OpenAI 兼容接口的数据模型。"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "knowledge-ai"


class ModelsListResponse(BaseModel):
    object: str = "list"
    data: List[ModelCard]


class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]], None] = ""
    name: Optional[str] = None


class ChatCompletionsRequest(BaseModel):
    model: str
    messages: List[ChatMessage] = Field(default_factory=list)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False


class AssistantMessage(BaseModel):
    role: str = "assistant"
    content: str


class ChatChoice(BaseModel):
    index: int = 0
    message: AssistantMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionsResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Usage
