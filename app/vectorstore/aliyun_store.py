"""
阿里云 OSS 向量存储实现 (基于 alibabacloud-oss-v2 SDK)

使用阿里云 OSS 原生向量索引能力，实现服务端 ANN 检索。

依赖:
    pip install alibabacloud-oss-v2
"""

import logging
import uuid
import hashlib
import json
import threading
from typing import List, Dict, Any, Optional, Tuple

from app.config import get_settings

logger = logging.getLogger(__name__)


class AliyunVectorStore:
    """
    基于阿里云 OSS V2 向量索引的向量存储

    特性:
        - 服务端 ANN 搜索，无需本地存储
        - 批量写入 (默认 500 条/批)
        - metadata 自动截断 (≤2048 字节)
        - 自动创建向量索引 (幂等)
        - is_healthy() 健康检查
    """

    def __init__(self):
        settings = get_settings()

        self.collection_name = settings.aliyun_collection_name
        self.vector_dimension = settings.embedding_dimension
        self.batch_size = settings.aliyun_vector_batch_size
        self.distance_metric = "euclidean"

        # 阿里云配置
        self._access_key_id = settings.aliyun_oss_access_key_id
        self._access_key_secret = settings.aliyun_oss_access_key_secret
        self._endpoint = settings.aliyun_oss_endpoint
        self._bucket_name = settings.aliyun_oss_bucket_name
        self._region = settings.aliyun_region
        self._account_id = settings.aliyun_account_id

        # 延迟初始化
        self._vector_client = None
        self._client_lock = threading.Lock()
        self._index_ensured = False

        logger.info(
            f"初始化阿里云 OSS 向量存储: index={self.collection_name}, "
            f"dimension={self.vector_dimension}, bucket={self._bucket_name}"
        )

    # ------------------------------------------------------------------
    # 客户端管理
    # ------------------------------------------------------------------

    def _get_vector_client(self):
        """获取 oss_vectors.Client (延迟初始化，线程安全)"""
        if self._vector_client is not None:
            return self._vector_client

        with self._client_lock:
            if self._vector_client is not None:
                return self._vector_client

            try:
                import alibabacloud_oss_v2 as oss
                import alibabacloud_oss_v2.vectors as oss_vectors
            except ImportError:
                raise ImportError(
                    "alibabacloud-oss-v2 库未安装，请运行:\n"
                    "  pip install alibabacloud-oss-v2"
                )

            if self._access_key_id and self._access_key_secret:
                credentials_provider = oss.credentials.StaticCredentialsProvider(
                    access_key_id=self._access_key_id,
                    access_key_secret=self._access_key_secret,
                )
            else:
                credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

            if not self._region:
                raise ValueError("阿里云 region 未配置，请设置 ALIYUN_REGION")
            if not self._account_id:
                raise ValueError("阿里云 account_id 未配置，请设置 ALIYUN_ACCOUNT_ID")

            cfg = oss.config.load_default()
            cfg.credentials_provider = credentials_provider
            cfg.region = self._region
            cfg.account_id = self._account_id
            if self._endpoint:
                cfg.endpoint = self._endpoint

            self._vector_client = oss_vectors.Client(cfg)
            logger.info(f"阿里云 OSS Vector Client 初始化成功: region={self._region}")
            return self._vector_client

    # ------------------------------------------------------------------
    # 索引管理
    # ------------------------------------------------------------------

    def _ensure_index(self):
        """确保向量索引已创建 (幂等)"""
        if self._index_ensured:
            return

        import alibabacloud_oss_v2.vectors as oss_vectors

        client = self._get_vector_client()

        try:
            client.get_vector_index(oss_vectors.models.GetVectorIndexRequest(
                bucket=self._bucket_name,
                index_name=self.collection_name,
            ))
            self._index_ensured = True
            logger.debug(f"向量索引已存在: {self.collection_name}")
            return
        except Exception as e:
            if "NoSuchVectorIndex" not in str(e) and "404" not in str(e):
                logger.warning(f"检查向量索引时出错: {str(e)}")

        try:
            client.put_vector_index(oss_vectors.models.PutVectorIndexRequest(
                bucket=self._bucket_name,
                index_name=self.collection_name,
                dimension=self.vector_dimension,
                distance_metric=self.distance_metric,
                data_type="float32",
            ))
            self._index_ensured = True
            logger.info(
                f"创建向量索引: {self.collection_name}, "
                f"dimension={self.vector_dimension}"
            )
        except Exception as e:
            if "Already" in str(e) or "exist" in str(e).lower():
                self._index_ensured = True
            else:
                logger.error(f"创建向量索引失败: {str(e)}")
                raise

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def add_embeddings(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """批量添加向量到阿里云 OSS 向量索引"""
        if not embeddings:
            return []

        if len(embeddings) != len(texts):
            raise ValueError(f"向量数量 ({len(embeddings)}) 和文本数量 ({len(texts)}) 不一致")

        if not metadatas:
            metadatas = [{} for _ in range(len(embeddings))]

        import alibabacloud_oss_v2.vectors as oss_vectors

        self._ensure_index()
        client = self._get_vector_client()

        ids = []
        all_rows = []
        MAX_META_BYTES = 2000

        for i in range(len(embeddings)):
            text_hash = hashlib.md5(texts[i].encode("utf-8")).hexdigest()[:12]
            unique_id = f"{text_hash}_{uuid.uuid4().hex[:8]}"
            ids.append(unique_id)

            meta_dict = {}
            if metadatas[i]:
                for mk, mv in metadatas[i].items():
                    meta_dict[mk] = str(mv) if not isinstance(mv, str) else mv

            meta_dict["text"] = texts[i]
            meta_size = len(json.dumps(meta_dict, ensure_ascii=False).encode("utf-8"))

            if meta_size > MAX_META_BYTES:
                ratio = MAX_META_BYTES / max(meta_size, 1)
                text_len = max(1, int(len(texts[i]) * ratio) - 50)
                meta_dict["text"] = texts[i][:text_len]
                meta_size = len(json.dumps(meta_dict, ensure_ascii=False).encode("utf-8"))
                while meta_size > MAX_META_BYTES and text_len > 10:
                    text_len = int(text_len * 0.85)
                    meta_dict["text"] = texts[i][:text_len]
                    meta_size = len(json.dumps(meta_dict, ensure_ascii=False).encode("utf-8"))

            row = {
                "key": unique_id,
                "data": {"float32": embeddings[i]},
                "metadata": meta_dict,
            }
            all_rows.append(row)

        total = len(all_rows)
        uploaded = 0

        try:
            for batch_start in range(0, total, self.batch_size):
                batch = all_rows[batch_start:batch_start + self.batch_size]
                client.put_vectors(oss_vectors.models.PutVectorsRequest(
                    bucket=self._bucket_name,
                    index_name=self.collection_name,
                    vectors=batch,
                ))
                uploaded += len(batch)
                logger.debug(f"上传进度: {uploaded}/{total}")

            logger.info(f"成功写入 {uploaded}/{total} 个向量")
            return ids
        except Exception as e:
            logger.error(f"批量写入失败 ({uploaded}/{total}): {str(e)}")
            raise

    def search(
        self,
        query_embedding: List[float],
        k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[float, str, Dict[str, Any]]]:
        """
        阿里云 OSS 服务端 ANN 搜索

        返回:
            List[Tuple[float, str, Dict]]: (距离, 文本, 元数据) 列表
        """
        if not query_embedding:
            raise ValueError("查询向量不能为空")

        import alibabacloud_oss_v2.vectors as oss_vectors

        try:
            self._ensure_index()
            client = self._get_vector_client()

            query_vector = {"float32": query_embedding}

            result = client.query_vectors(oss_vectors.models.QueryVectorsRequest(
                bucket=self._bucket_name,
                index_name=self.collection_name,
                top_k=k,
                query_vector=query_vector,
                filter=filter,
                return_distance=True,
                return_metadata=True,
            ))

            search_results = []
            if result.vectors:
                for vec in result.vectors:
                    distance = vec.get("distance", 0.0)
                    metadata = vec.get("metadata", {})
                    text = metadata.pop("text", "")
                    search_results.append((float(distance), text, metadata))

            logger.debug(f"搜索完成: top_k={k}, 返回 {len(search_results)} 个结果")
            return search_results
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            raise

    def delete(self, ids: List[str]) -> bool:
        """删除指定向量"""
        if not ids:
            return True

        import alibabacloud_oss_v2.vectors as oss_vectors

        try:
            self._ensure_index()
            client = self._get_vector_client()

            for batch_start in range(0, len(ids), self.batch_size):
                batch = ids[batch_start:batch_start + self.batch_size]
                client.delete_vectors(oss_vectors.models.DeleteVectorsRequest(
                    bucket=self._bucket_name,
                    index_name=self.collection_name,
                    keys=batch,
                ))

            logger.info(f"成功删除 {len(ids)} 个向量")
            return True
        except Exception as e:
            logger.error(f"删除向量失败: {str(e)}")
            return False

    def clear(self) -> bool:
        """清空集合 (删除索引后重建)"""
        import alibabacloud_oss_v2.vectors as oss_vectors

        try:
            client = self._get_vector_client()
            try:
                client.delete_vector_index(oss_vectors.models.DeleteVectorIndexRequest(
                    bucket=self._bucket_name,
                    index_name=self.collection_name,
                ))
            except Exception as e:
                if "NoSuchVectorIndex" not in str(e) and "404" not in str(e):
                    raise

            self._index_ensured = False
            self._ensure_index()
            logger.info(f"已清空并重建: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"清空集合失败: {str(e)}")
            return False

    def count(self) -> int:
        """获取向量数量"""
        import alibabacloud_oss_v2.vectors as oss_vectors

        try:
            self._ensure_index()
            client = self._get_vector_client()
            total = 0
            next_token = None

            while True:
                result = client.list_vectors(oss_vectors.models.ListVectorsRequest(
                    bucket=self._bucket_name,
                    index_name=self.collection_name,
                    max_results=1000,
                    next_token=next_token,
                    return_data=False,
                    return_metadata=False,
                ))
                if result.vectors:
                    total += len(result.vectors)
                next_token = result.next_token
                if not next_token:
                    break

            return total
        except Exception as e:
            logger.error(f"获取向量数量失败: {str(e)}")
            return 0

    def is_healthy(self) -> bool:
        """检查阿里云 OSS 向量服务是否健康"""
        import alibabacloud_oss_v2.vectors as oss_vectors

        try:
            client = self._get_vector_client()
            client.get_vector_bucket(oss_vectors.models.GetVectorBucketRequest(
                bucket=self._bucket_name,
            ))
            return True
        except Exception as e:
            logger.warning(f"健康检查失败: {str(e)}")
            return False

    def get_by_ids(
        self,
        ids: List[str],
        return_data: bool = False,
        return_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """根据向量 key 精确检索"""
        if not ids:
            return []

        import alibabacloud_oss_v2.vectors as oss_vectors

        try:
            self._ensure_index()
            client = self._get_vector_client()
            all_results = []
            batch_size = min(self.batch_size, 100)

            for batch_start in range(0, len(ids), batch_size):
                batch_keys = ids[batch_start:batch_start + batch_size]
                result = client.get_vectors(oss_vectors.models.GetVectorsRequest(
                    bucket=self._bucket_name,
                    index_name=self.collection_name,
                    keys=batch_keys,
                    return_data=return_data,
                    return_metadata=return_metadata,
                ))
                if result.vectors:
                    all_results.extend(result.vectors)

            return all_results
        except Exception as e:
            logger.error(f"按 ID 检索失败: {str(e)}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            return {
                "collection": self.collection_name,
                "dimension": self.vector_dimension,
                "vector_count": self.count(),
                "bucket": self._bucket_name,
                "region": self._region,
                "backend": "aliyun_oss_vector",
            }
        except Exception as e:
            return {"collection": self.collection_name, "error": str(e)}
