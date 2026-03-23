"""本地 Embedding 服务 - 基于 sentence-transformers"""

import logging
from typing import List, Optional

from sentence_transformers import SentenceTransformer

from app.config import get_settings

logger = logging.getLogger(__name__)


class LocalEmbeddingService:
    """基于 sentence-transformers 的本地 Embedding 服务（无需 API 调用）"""

    def __init__(self, model_name: Optional[str] = None):
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self._dimension = settings.embedding_dimension

        logger.info(f"加载 Embedding 模型: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        self._dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"Embedding 模型加载完成，维度: {self._dimension}")

    def embed_text(self, text: str) -> List[float]:
        """对单个文本进行向量化"""
        if not text or not text.strip():
            return [0.0] * self._dimension
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        if not texts:
            return []
        cleaned = [t if t and t.strip() else " " for t in texts]
        embeddings = self.model.encode(cleaned, normalize_embeddings=True, show_progress_bar=True)
        return embeddings.tolist()

    def get_dimension(self) -> int:
        return self._dimension

    def health_check(self) -> bool:
        try:
            result = self.model.encode("test")
            return len(result) > 0
        except Exception:
            return False
