"""规则学习流水线编排与报告生成。"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from app.agent.rule_learning.extraction import RuleExtractor
from app.agent.rule_learning.ingestion import FileRouter
from app.agent.rule_learning.normalization import RuleNormalizer
from app.agent.rule_learning.rule_repository import RuleRepository
from app.agent.rule_learning.validation import RuleValidator


class RuleLearningPipelineService:
    """流水线服务：输入解析 -> 候选提取 -> 归一化 -> 校验入库。"""

    def __init__(self, repo: Optional[RuleRepository] = None):
        self.repo = repo or RuleRepository()
        self.file_router = FileRouter()
        self.extractor = RuleExtractor()
        self.normalizer = RuleNormalizer()
        self.validator = RuleValidator(repo=self.repo)

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat()

    def _build_report(
        self,
        *,
        learning_id: str,
        source_name: str,
        ingest_result: Dict[str, Any],
        candidates: list[dict],
        normalized_rules: list[dict],
        validation_result: Dict[str, Any],
        started_at: float,
    ) -> Dict[str, Any]:
        accepted = validation_result.get("accepted", [])
        rejected = validation_result.get("rejected", [])
        conflicts = validation_result.get("conflicts", [])

        return {
            "learning_id": learning_id,
            "created_at": self._now(),
            "source": {
                "name": source_name,
                "input_type": ingest_result.get("input_type", "unknown"),
                "chunks_count": ingest_result.get("chunks_count", 0),
                "warnings": ingest_result.get("warnings", []),
            },
            "pipeline": {
                "candidates_count": len(candidates),
                "normalized_count": len(normalized_rules),
                "validated_total": validation_result.get("total", len(normalized_rules)),
            },
            "result": {
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "conflicts_count": len(conflicts),
                "accepted_rule_ids": [r.get("rule_id", "") for r in accepted],
                "rejected": rejected,
                "conflicts": conflicts,
            },
            "duration_ms": round((time.time() - started_at) * 1000, 1),
        }

    def learn_from_file(self, file_path: str) -> Dict[str, Any]:
        started_at = time.time()
        ingest_result = self.file_router.ingest(source=file_path)
        if not ingest_result.get("success"):
            return {
                "learning_id": str(uuid.uuid4()),
                "created_at": self._now(),
                "source": {
                    "name": ingest_result.get("file_name", file_path),
                    "input_type": ingest_result.get("input_type", "unknown"),
                    "chunks_count": 0,
                    "warnings": ingest_result.get("warnings", []),
                },
                "pipeline": {
                    "candidates_count": 0,
                    "normalized_count": 0,
                    "validated_total": 0,
                },
                "result": {
                    "accepted_count": 0,
                    "rejected_count": 0,
                    "conflicts_count": 0,
                    "accepted_rule_ids": [],
                    "rejected": [],
                    "conflicts": [],
                },
                "duration_ms": round((time.time() - started_at) * 1000, 1),
            }

        chunks = ingest_result.get("chunks", [])
        candidates = self.extractor.extract(chunks)
        normalized_rules = self.normalizer.normalize(candidates)
        validation_result = self.validator.validate_and_store(normalized_rules)
        return self._build_report(
            learning_id=str(uuid.uuid4()),
            source_name=ingest_result.get("file_name", file_path),
            ingest_result=ingest_result,
            candidates=candidates,
            normalized_rules=normalized_rules,
            validation_result=validation_result,
            started_at=started_at,
        )

    def learn_from_text(self, text: str, source_name: Optional[str] = None) -> Dict[str, Any]:
        started_at = time.time()
        ingest_result = self.file_router.ingest(source=text, source_name=source_name or "inline_text")
        chunks = ingest_result.get("chunks", [])
        candidates = self.extractor.extract(chunks)
        normalized_rules = self.normalizer.normalize(candidates)
        validation_result = self.validator.validate_and_store(normalized_rules)
        return self._build_report(
            learning_id=str(uuid.uuid4()),
            source_name=ingest_result.get("file_name", source_name or "inline_text"),
            ingest_result=ingest_result,
            candidates=candidates,
            normalized_rules=normalized_rules,
            validation_result=validation_result,
            started_at=started_at,
        )