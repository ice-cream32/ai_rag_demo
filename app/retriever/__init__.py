"""检索器模块"""

from app.retriever.vector_retriever import VectorRetriever

_instance = None


def get_vector_retriever() -> VectorRetriever:
    """获取 VectorRetriever 单例"""
    global _instance
    if _instance is None:
        _instance = VectorRetriever()
    return _instance


__all__ = ["VectorRetriever", "get_vector_retriever"]
