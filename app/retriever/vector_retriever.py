"""向量检索器 - 本地 Embedding + 阿里云向量搜索"""

import logging
from typing import List, Dict, Any, Optional, Tuple

from app.embeddings import get_embedding_service
from app.vectorstore import get_vector_store

logger = logging.getLogger(__name__)


class VectorRetriever:
    """
    向量检索器：本地做 Embedding，阿里云做 ANN 搜索

    流程:
        query → 本地 embed → 阿里云 ANN search → 相似度排序 → 返回结果
    """

    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store()
        logger.info("初始化向量检索器 (本地 Embedding + 阿里云向量库)")

    def retrieve(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[float, str, Dict[str, Any]]]:
        """
        检索相关文档

        参数:
            query: 查询文本
            k: 返回结果数
            filter: 元数据过滤

        返回:
            List[Tuple[float, str, Dict]]: (相似度, 文本, 元数据) 列表
        """
        if not query or not isinstance(query, str):
            raise ValueError("Query must be a non-empty string")

        try:
            # 1. 本地向量化
            query_embedding = self.embedding_service.embed_text(query)
            if not query_embedding:
                raise RuntimeError("Embedding 服务返回空向量")

            # 2. 阿里云 ANN 搜索
            results = self.vector_store.search(query_embedding, k, filter)

            if not results:
                logger.warning("搜索未返回结果")
                return []

            # 3. L2 距离 → 相似度 (0~1)
            processed = []
            for distance, text, metadata in results:
                if not text:
                    continue
                similarity = 1.0 / (1.0 + distance) if distance >= 0 else 0.0
                processed.append((similarity, text, metadata or {}))

            processed.sort(key=lambda x: x[0], reverse=True)
            logger.info(f"检索完成: '{query[:50]}...', 返回 {len(processed)} 个结果")
            return processed

        except Exception as e:
            logger.error(f"检索失败: {str(e)}", exc_info=True)
            raise

    def add_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """
        添加文档到向量库 (本地 Embedding + 云端存储)

        参数:
            texts: 文本列表
            metadatas: 元数据列表

        返回:
            List[str]: 向量 ID 列表
        """
        if not texts:
            return []

        logger.info(f"开始向量化 {len(texts)} 个文本块...")
        embeddings = self.embedding_service.embed_documents(texts)
        logger.info(f"向量化完成，开始上传到阿里云...")

        ids = self.vector_store.add_embeddings(embeddings, texts, metadatas)
        logger.info(f"成功添加 {len(ids)} 个文档到向量库")
        return ids

    def get_stats(self) -> Dict[str, Any]:
        """获取向量库统计"""
        try:
            return {
                "vector_count": self.vector_store.count(),
                "is_healthy": self.vector_store.is_healthy(),
                "embedding_model": self.embedding_service.model_name,
                "embedding_dimension": self.embedding_service.get_dimension(),
            }
        except Exception as e:
            return {"error": str(e), "is_healthy": False}
