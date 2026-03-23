"""Rules API - Phase 1 (xlsx import + list local rules)."""

from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import datetime
from typing import Optional, Union

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agent.rule_learning.rule_learning_service import RuleLearningPipelineService
from app.agent.rule_learning import RuleLearningService
from app.agent.rule_learning.schemas import ParseRequest

router = APIRouter()
logger = logging.getLogger(__name__)

service = RuleLearningService()
learning_service = RuleLearningPipelineService()


class RuleImportResponse(BaseModel):
    code: int
    message: str
    source_file: str
    imported_at: str
    total_rows: int
    parsed_rows: int
    skipped_rows: int
    created_rules: int
    updated_rules: int
    by_brand: dict


class LearnFromTextRequest(BaseModel):
    text: str
    source_name: Optional[str] = None


def _json_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": status_code, "message": message})


async def handle_rules_import_xlsx(file: UploadFile) -> Union[RuleImportResponse, JSONResponse]:
    start = time.time()
    filename = file.filename or "rules.xlsx"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".xlsx"}:
        return _json_error(400, "仅支持 .xlsx 文件")

    os.makedirs("./data/rule_learning/imports", exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    save_path = f"./data/rule_learning/imports/{ts}_{filename}"

    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        report = service.import_xlsx(save_path)
        ms = (time.time() - start) * 1000
        logger.info(
            "rules import success | file=%s total=%s parsed=%s created=%s updated=%s duration_ms=%.1f",
            report.source_file,
            report.stats.total_rows,
            report.stats.parsed_rows,
            report.stats.created_rules,
            report.stats.updated_rules,
            ms,
        )

        return RuleImportResponse(
            code=200,
            message="success",
            source_file=report.source_file,
            imported_at=report.imported_at.isoformat(),
            total_rows=report.stats.total_rows,
            parsed_rows=report.stats.parsed_rows,
            skipped_rows=report.stats.skipped_rows,
            created_rules=report.stats.created_rules,
            updated_rules=report.stats.updated_rules,
            by_brand=report.stats.by_brand,
        )
    except Exception as exc:
        logger.error("rules import failed: %s", exc, exc_info=True)
        return _json_error(500, f"导入失败: {exc}")


async def handle_learn_from_file_upload(file: UploadFile) -> Union[dict, JSONResponse]:
    filename = file.filename or "learning_source"
    os.makedirs("./data/rule_learning/learn_uploads", exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    save_path = f"./data/rule_learning/learn_uploads/{ts}_{filename}"

    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        report = learning_service.learn_from_file(save_path)
        return {"code": 200, "message": "success", "report": report}
    except Exception as exc:
        logger.error("rules learn-from-file failed: %s", exc, exc_info=True)
        return _json_error(500, f"学习失败: {exc}")


def handle_learn_from_text_payload(text: str, source_name: Optional[str] = None) -> Union[dict, JSONResponse]:
    content = (text or "").strip()
    if not content:
        return _json_error(400, "text 不能为空")

    try:
        report = learning_service.learn_from_text(text=content, source_name=source_name)
        return {"code": 200, "message": "success", "report": report}
    except Exception as exc:
        logger.error("rules learn-from-text failed: %s", exc, exc_info=True)
        return _json_error(500, f"学习失败: {exc}")


@router.post("/rules/import-xlsx", response_model=RuleImportResponse)
async def import_rules_xlsx(file: UploadFile = File(...)):
    return await handle_rules_import_xlsx(file)


@router.get("/rules")
async def list_rules(brand: Optional[str] = Query(default=None, description="品牌过滤，可选")):
    try:
        resp = service.list_rules(brand=brand)
        return {"code": 200, "message": "success", **resp.model_dump(mode="json")}
    except Exception as exc:
        logger.error("rules list failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"code": 500, "message": f"查询失败: {exc}"})


@router.post("/rules/parse")
async def parse_part_number_local(payload: ParseRequest):
    """Phase 2: 仅使用本地规则解析料号。"""
    pn = (payload.part_number or "").strip()
    if not pn:
        return JSONResponse(status_code=400, content={"code": 400, "message": "part_number 不能为空"})

    try:
        result = service.parse_local(
            part_number=pn,
            brand_hint=payload.brand_hint,
            enable_web_enrich=payload.enable_web_enrich,
        )
        return {"code": 200, "message": "success", **result.model_dump(mode="json")}
    except Exception as exc:
        logger.error("rules parse failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"code": 500, "message": f"解析失败: {exc}"})


@router.post("/rules/learn-from-file")
async def learn_from_file(file: UploadFile = File(...)):
    return await handle_learn_from_file_upload(file)


@router.post("/rules/learn-from-text")
async def learn_from_text(payload: LearnFromTextRequest):
    return handle_learn_from_text_payload(text=payload.text, source_name=payload.source_name)
