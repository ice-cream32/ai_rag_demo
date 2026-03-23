"""向量嵌入模块（本地 sentence-transformers）。"""

from app.embeddings.local_embedding import LocalEmbeddingService

_instance = None


def get_embedding_service() -> LocalEmbeddingService:
    """获取向量服务单例。"""
    global _instance
    if _instance is None:
        _instance = LocalEmbeddingService()
    return _instance


__all__ = ["LocalEmbeddingService", "get_embedding_service"]
