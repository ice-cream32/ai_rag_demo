"""文档管理端点 - 上传文档并索引到向量库"""

import os
import shutil
import logging
from typing import Optional, Union

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.loader import DocumentLoader
from app.retriever import get_vector_retriever

router = APIRouter()
logger = logging.getLogger(__name__)


class UploadResponse(BaseModel):
    code: int           # 业务状态码: 200 成功 / 400 参数错误 / 500 服务异常
    message: str        # 人类可读描述
    filename: Optional[str] = None
    chunks: Optional[int] = None
    vectors: Optional[int] = None


def _err(code: int, msg: str, filename: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"code": code, "message": msg, "filename": filename,
                 "chunks": None, "vectors": None},
    )


async def handle_document_upload(file: UploadFile, category: Optional[str] = None) -> Union[UploadResponse, JSONResponse]:
    settings = get_settings()

    # 检查文件类型
    allowed_exts = {".pdf", ".txt", ".csv", ".md"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        return _err(400, f"不支持的文件类型: {ext}，支持: {', '.join(allowed_exts)}", file.filename)

    # 保存到本地
    os.makedirs(settings.data_dir, exist_ok=True)
    save_path = os.path.join(settings.data_dir, file.filename)

    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(f"文件已保存: {save_path}")
    except Exception as e:
        return _err(500, f"文件保存失败: {str(e)}", file.filename)

    # 加载并分块
    try:
        loader = DocumentLoader()
        chunks = loader.load_file(save_path)

        if not chunks:
            return _err(400, "文件内容为空或无法解析", file.filename)

        # 添加 category 到元数据
        if category:
            for chunk in chunks:
                chunk["metadata"]["category"] = category

        texts = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        # 向量化并上传
        retriever = get_vector_retriever()
        ids = retriever.add_documents(texts, metadatas)

        return UploadResponse(
            code=200,
            message=f"成功: {len(chunks)} 个文本块已向量化并上传到云端向量库",
            filename=file.filename,
            chunks=len(chunks),
            vectors=len(ids),
        )

    except Exception as e:
        logger.error(f"文档处理失败: {str(e)}", exc_info=True)
        return _err(500, f"文档处理失败: {str(e)}", file.filename)


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
):
    """
    上传文档 → 分块 → 本地 Embedding → 存入阿里云向量库

    支持格式: PDF, TXT, CSV, Markdown

    响应体 code 说明:
      200 - 上传成功
      400 - 文件类型不支持 / 内容为空
      500 - 保存失败 / 向量化失败
    """
    return await handle_document_upload(file=file, category=category)


@router.post("/documents/index-directory")
async def index_directory(dir_path: Optional[str] = None):
    """索引整个目录的文档到向量库"""
    settings = get_settings()
    target_dir = dir_path or settings.data_dir

    if not os.path.exists(target_dir):
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": f"目录不存在: {target_dir}", "chunks": 0, "vectors": 0},
        )

    try:
        loader = DocumentLoader()
        all_chunks = loader.load_directory(target_dir)

        if not all_chunks:
            return {"code": 200, "message": "目录中没有可处理的文档", "chunks": 0, "vectors": 0}

        texts = [c["text"] for c in all_chunks]
        metadatas = [c["metadata"] for c in all_chunks]

        retriever = get_vector_retriever()
        ids = retriever.add_documents(texts, metadatas)

        return {
            "code": 200,
            "message": f"成功索引 {len(ids)} 个向量到云端",
            "directory": target_dir,
            "chunks": len(all_chunks),
            "vectors": len(ids),
        }

    except Exception as e:
        logger.error(f"目录索引失败: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": f"索引失败: {str(e)}", "chunks": 0, "vectors": 0},
        )


@router.get("/documents/stats")
async def documents_stats():
    """获取文档和向量库统计"""
    try:
        retriever = get_vector_retriever()
        stats = retriever.get_stats()
        return {"code": 200, "message": "success", **stats}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": str(e)},
        )
