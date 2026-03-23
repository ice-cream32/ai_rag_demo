"""统一上传端点 - 聚合文档上传与规则学习/导入相关文件接口。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.api.documents import handle_document_upload
from app.api.rules import (
    handle_learn_from_file_upload,
    handle_learn_from_text_payload,
    handle_rules_import_xlsx,
)

router = APIRouter()
logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {
    "document_upload",
    "rules_import_xlsx",
    "rules_learn_file",
    "rules_learn_text",
}


@router.post("/uploads/unified")
async def unified_upload(
    request: Request,
    action: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    category: Optional[str] = Form(default=None),
    text: Optional[str] = Form(default=None),
    source_name: Optional[str] = Form(default=None),
):
    """
    统一上传/学习入口。

    action 说明:
      - document_upload: 文档上传并向量化（file 必填，可选 category）
      - rules_import_xlsx: 规则 xlsx 导入（file 必填）
      - rules_learn_file: 规则文件学习（file 必填）
      - rules_learn_text: 文本学习（text 必填，可选 source_name）

    为兼容文本学习，支持 JSON 请求体：
      {"action":"rules_learn_text","text":"...","source_name":"..."}
    """
    resolved_action = action
    resolved_text = text
    resolved_source_name = source_name

    # 允许 rules_learn_text 使用 application/json 调用，减少客户端改造。
    content_type = request.headers.get("content-type", "")
    if (not resolved_action or (resolved_action == "rules_learn_text" and not resolved_text)) and "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not resolved_action:
            resolved_action = payload.get("action")
        if not resolved_text:
            resolved_text = payload.get("text")
        if not resolved_source_name:
            resolved_source_name = payload.get("source_name")

    if not resolved_action:
        return JSONResponse(status_code=400, content={"code": 400, "message": "action 不能为空"})

    if resolved_action not in SUPPORTED_ACTIONS:
        return JSONResponse(
            status_code=400,
            content={
                "code": 400,
                "message": f"不支持的 action: {resolved_action}",
                "supported_actions": sorted(SUPPORTED_ACTIONS),
            },
        )

    if resolved_action == "document_upload":
        if file is None:
            return JSONResponse(status_code=400, content={"code": 400, "message": "file 不能为空"})
        return await handle_document_upload(file=file, category=category)

    if resolved_action == "rules_import_xlsx":
        if file is None:
            return JSONResponse(status_code=400, content={"code": 400, "message": "file 不能为空"})
        return await handle_rules_import_xlsx(file=file)

    if resolved_action == "rules_learn_file":
        if file is None:
            return JSONResponse(status_code=400, content={"code": 400, "message": "file 不能为空"})
        return await handle_learn_from_file_upload(file=file)

    return handle_learn_from_text_payload(text=resolved_text or "", source_name=resolved_source_name)
