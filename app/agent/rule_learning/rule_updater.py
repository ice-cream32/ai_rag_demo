"""规则更新器：写入扩展规则与更新日志。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.agent.rule_learning.conflict_detector import ConflictDetector
from app.agent.rule_learning.rule_repository import RuleRepository
from app.agent.rule_learning.schemas import ParsedField


class RuleUpdater:
    def __init__(self, repo: RuleRepository):
        self.repo = repo
        self.conflict_detector = ConflictDetector()

    @staticmethod
    def _confidence(new_fields_count: int, image_count: int) -> float:
        base = 0.55
        base += min(0.25, new_fields_count * 0.05)
        base += min(0.10, image_count * 0.02)
        return round(min(0.95, base), 4)

    def update_from_web_enrichment(
        self,
        *,
        part_number: str,
        brand: str,
        matched_rule_id: str,
        local_fields: Dict[str, ParsedField],
        web_fields: Dict[str, Any],
        field_sources: Dict[str, str],
        images: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        conflicts = self.conflict_detector.detect(local_fields=local_fields, web_fields=web_fields)

        blocked_fields = {c["field"] for c in conflicts}
        new_fields: Dict[str, Any] = {}
        for k, v in web_fields.items():
            if not v:
                continue
            if k in blocked_fields:
                continue
            if k in local_fields:
                # 手工规则字段不可被覆盖
                continue
            new_fields[k] = v

        if conflicts:
            self.repo.append_conflicts(
                [
                    {
                        "part_number": part_number,
                        "matched_rule_id": matched_rule_id,
                        "detected_at": now,
                        **c,
                    }
                    for c in conflicts
                ]
            )

        if not new_fields and not images:
            event = {
                "event_type": "no_update",
                "part_number": part_number,
                "matched_rule_id": matched_rule_id,
                "created_at": now,
                "new_fields": {},
                "images_count": 0,
                "conflicts_count": len(conflicts),
                "note": "no new non-conflicting fields or images",
            }
            self.repo.append_update_log(event)
            return {
                "updated": False,
                "extension_rule_id": "",
                "new_fields_count": 0,
                "images_count": 0,
                "conflicts": conflicts,
            }

        extension_rule_id = f"ext_{matched_rule_id or 'unmatched'}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        extension_rule = {
            "rule_id": extension_rule_id,
            "base_rule_id": matched_rule_id,
            "part_number": part_number,
            "brand": brand,
            "fields": new_fields,
            "field_sources": {k: field_sources.get(k, "") for k in new_fields.keys()},
            "images": images,
            "source_type": "web_enriched_rule",
            "source_urls": sorted({u for u in field_sources.values() if u}),
            "confidence": self._confidence(len(new_fields), len(images)),
            "approved": False,
            "status": "candidate",
            "created_at": now,
            "updated_at": now,
        }
        self.repo.upsert_extension_rule(extension_rule)

        event = {
            "event_type": "extension_rule_created",
            "part_number": part_number,
            "matched_rule_id": matched_rule_id,
            "extension_rule_id": extension_rule_id,
            "created_at": now,
            "new_fields": new_fields,
            "images_count": len(images),
            "conflicts_count": len(conflicts),
        }
        self.repo.append_update_log(event)

        return {
            "updated": True,
            "extension_rule_id": extension_rule_id,
            "new_fields_count": len(new_fields),
            "images_count": len(images),
            "conflicts": conflicts,
        }
