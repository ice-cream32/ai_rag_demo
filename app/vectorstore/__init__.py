"""向量存储模块 - 阿里云 OSS 云向量库"""

from app.vectorstore.aliyun_store import AliyunVectorStore

_instance = None


def get_vector_store() -> AliyunVectorStore:
    """获取向量存储单例"""
    global _instance
    if _instance is None:
        _instance = AliyunVectorStore()
    return _instance


__all__ = ["AliyunVectorStore", "get_vector_store"]
