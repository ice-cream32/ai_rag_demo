"""应用配置管理 - LangChain Agent 版"""

from typing import Literal
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置类，支持环境变量和 .env 文件。"""

    # API 配置
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False          # 生产环境设为 False
    api_workers: int = 1             # 多进程数量，生产建议 CPU 核数 x 2 + 1
    api_key: str = ""               # 外网鉴权 Key，设置后所有接口必须携带 X-API-Key 请求头
    api_title: str = "存储芯片知识库 AI"
    api_version: str = "2.0.0"

    # 阿里云百炼 API 配置 (DashScope OpenAI 兼容模式)
    dashscope_api_key: str = "sk-sp-b3f3e26acb5a4788b44deb2cbe5c4eed"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"
    dashscope_temperature: float = 0.1
    dashscope_max_tokens: int = 4096

    # OpenAI 兼容层配置
    openai_compat_enabled: bool = True
    openai_compat_model_id: str = "先搜小芯"
    openai_compat_model_name: str = "Knowledge AI Agent"

    # 向量模型配置（本地 sentence-transformers）
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384  # all-MiniLM-L6-v2 模型维度

    # 阿里云 OSS 向量存储配置
    aliyun_oss_access_key_id: str = ""
    aliyun_oss_access_key_secret: str = ""
    aliyun_oss_endpoint: str = ""           # 示例：https://oss-cn-shenzhen.aliyuncs.com
    aliyun_oss_bucket_name: str = ""        # 示例：semiconductor-vectors
    aliyun_region: str = ""                 # 示例：cn-shenzhen
    aliyun_account_id: str = ""             # 阿里云账号 ID
    aliyun_vector_batch_size: int = 500     # 批量写入大小
    aliyun_collection_name: str = "semiconductordocs_lite"

    # 文档处理配置
    data_dir: str = "./data/documents"
    chunk_size: int = 800
    chunk_overlap: int = 150

    # RAG 配置
    rag_top_k: int = 5
    rag_min_similarity: float = 0.3

    # 日志配置
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """获取缓存的配置实例。"""
    return Settings()
