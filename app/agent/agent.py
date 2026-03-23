"""存储芯片 Agent - 基于 LangChain + 阿里云百炼 API"""

import logging
from typing import Any, Dict, Iterable, List, Optional

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from app.agent.skills import get_all_tools
from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位专业的存储芯片技术助手，名字叫先搜小芯。你精通各种存储芯片的技术参数和行业知识，能够帮助用户解析料号、检索技术文档并回答相关问题。
具备以下能力：

. **料号解析**：解析存储芯片料号（镁光/SPECTEK/三星/海力士等品牌的NAND/DDR颗粒和晶圆），提取品牌、型号、容量、位宽、制程、球位、良率等关键参数。
. **知识库检索**：检索半导体技术文档，回答技术知识相关问题。

工作原则：
- 当用户提供料号时，必须优先调用工具 parse_part_number_rule_learning（本地规则优先，必要时联网补全），不要猜测参数值
- 当用户询问技术知识时，先检索知识库再回答
- 使用中文回答，保持专业且简洁
- 基于工具返回的实际数据回答，不编造内容"""


class StorageChipAgent:
    """存储芯片 Agent，基于 LangChain create_agent + 百炼 LLM"""

    def __init__(self):
        settings = get_settings()

        # 初始化百炼 LLM（通过 LangChain OpenAI 兼容接口）
        self.llm = ChatOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=settings.dashscope_model,
            temperature=settings.dashscope_temperature,
            max_tokens=settings.dashscope_max_tokens,
        )

        # 收集所有 Skills
        self.tools = get_all_tools()

        # 创建 LangChain Agent (LangGraph-based react agent)
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
        )

        logger.info(
            f"Agent 初始化完成: model={settings.dashscope_model}, "
            f"tools={[t.name for t in self.tools]}"
        )

    def run(self, query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        执行 Agent 对话

        参数:
            query: 用户输入
            chat_history: 对话历史 [{"role": "user", "content": "..."}, ...]

        返回:
            Agent 回复文本
        """
        try:
            # 构建消息列表
            messages = []
            if chat_history:
                for msg in chat_history:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role in ("user", "assistant"):
                        messages.append({"role": role, "content": content})

            messages.append({"role": "user", "content": query})

            # 调用 agent
            result = self.agent.invoke({"messages": messages})

            # 提取最终回复
            output_messages = result.get("messages", [])
            if output_messages:
                # 取最后一条 AI 消息
                for msg in reversed(output_messages):
                    if hasattr(msg, "content") and msg.type == "ai" and msg.content:
                        return msg.content

            return "处理完成，但没有文本回复。"

        except Exception as e:
            logger.error(f"Agent 运行错误: {e}", exc_info=True)
            return f"Agent 处理失败: {str(e)}"

    @staticmethod
    def _build_messages(query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        """构建 LangChain agent 所需 messages 结构。"""
        messages: List[Dict[str, str]] = []
        if chat_history:
            for msg in chat_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": query})
        return messages

    @staticmethod
    def _chunk_to_text(content: Any) -> str:
        """将 LangChain 消息 chunk 的 content 统一转换为文本。"""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    # OpenAI 风格内容块：{"type": "text", "text": "..."}
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return str(content)

    def stream(self, query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> Iterable[str]:
        """真实流式输出：边生成边返回文本 chunk。"""
        try:
            messages = self._build_messages(query=query, chat_history=chat_history)

            # stream_mode="messages" 时，create_agent 会持续返回消息块。
            for item in self.agent.stream({"messages": messages}, stream_mode="messages"):
                msg = None
                if isinstance(item, tuple) and item:
                    msg = item[0]
                elif hasattr(item, "content"):
                    msg = item

                if msg is None:
                    continue

                content = getattr(msg, "content", None)
                text = self._chunk_to_text(content)
                if text:
                    yield text
        except Exception as e:
            logger.error(f"Agent 流式运行错误: {e}", exc_info=True)
            yield f"\n[流式输出异常] {str(e)}"


# 单例
_agent_instance: Optional[StorageChipAgent] = None


def get_agent() -> StorageChipAgent:
    """获取 Agent 单例"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = StorageChipAgent()
    return _agent_instance
