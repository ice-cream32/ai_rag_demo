"""
文档加载器 - 支持 PDF/TXT/CSV/Markdown 文件加载和分块

简化版本: 使用 LangChain 加载器 + RecursiveCharacterTextSplitter
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyMuPDFLoader,
    TextLoader,
    CSVLoader,
    UnstructuredMarkdownLoader,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


class DocumentLoader:
    """文档加载和分块处理器"""

    # 支持的文件扩展名 → 加载器
    LOADERS = {
        ".pdf": PyMuPDFLoader,
        ".txt": TextLoader,
        ".csv": CSVLoader,
        ".md": UnstructuredMarkdownLoader,
    }

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        settings = get_settings()
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
        self.data_dir = settings.data_dir

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", ".", " ", ""],
        )

    def load_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        加载单个文件并分块

        参数:
            file_path: 文件路径

        返回:
            List[Dict]: [{"text": "...", "metadata": {...}}, ...]
        """
        ext = Path(file_path).suffix.lower()
        loader_cls = self.LOADERS.get(ext)

        if not loader_cls:
            logger.warning(f"不支持的文件类型: {ext}")
            return []

        try:
            if ext == ".txt":
                loader = loader_cls(file_path, encoding="utf-8")
            elif ext == ".csv":
                loader = loader_cls(file_path, encoding="utf-8")
            else:
                loader = loader_cls(file_path)

            documents = loader.load()
            chunks = self.splitter.split_documents(documents)

            results = []
            for i, chunk in enumerate(chunks):
                metadata = chunk.metadata.copy()
                metadata["source"] = os.path.basename(file_path)
                metadata["chunk_index"] = i
                metadata["file_path"] = file_path
                results.append({
                    "text": chunk.page_content,
                    "metadata": metadata,
                })

            logger.info(f"加载文件 {file_path}: {len(documents)} 页 → {len(results)} 块")
            return results

        except Exception as e:
            logger.error(f"加载文件失败 {file_path}: {str(e)}")
            return []

    def load_directory(self, dir_path: str = None) -> List[Dict[str, Any]]:
        """
        加载目录下所有支持的文件

        参数:
            dir_path: 目录路径，默认使用 data_dir 配置

        返回:
            List[Dict]: 所有文件的分块结果
        """
        dir_path = dir_path or self.data_dir

        if not os.path.exists(dir_path):
            logger.warning(f"目录不存在: {dir_path}")
            return []

        all_chunks = []
        supported_exts = set(self.LOADERS.keys())

        for root, _, files in os.walk(dir_path):
            for fname in sorted(files):
                ext = Path(fname).suffix.lower()
                if ext in supported_exts:
                    file_path = os.path.join(root, fname)
                    chunks = self.load_file(file_path)
                    all_chunks.extend(chunks)

        logger.info(f"从目录 {dir_path} 加载了 {len(all_chunks)} 个文本块")
        return all_chunks


def load_and_split(file_path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    便捷函数：加载文件并返回 (texts, metadatas) 元组

    参数:
        file_path: 文件路径

    返回:
        Tuple[List[str], List[Dict]]: (文本列表, 元数据列表)
    """
    loader = DocumentLoader()
    chunks = loader.load_file(file_path)
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    return texts, metadatas
