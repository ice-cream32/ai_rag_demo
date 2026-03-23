"""手工规则与联网补全候选之间的冲突检测。"""

from __future__ import annotations

from typing import Any, Dict, List

from app.agent.rule_learning.schemas import ParsedField


class ConflictDetector:
    """检测冲突：低优先级的联网值不能覆盖手工值。"""

    def detect(
        self,
        local_fields: Dict[str, ParsedField],
        web_fields: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        for field_name, web_value in web_fields.items():
            local = local_fields.get(field_name)
            if local is None:
                continue
            local_value = "" if local.value is None else str(local.value).strip()
            current_web = "" if web_value is None else str(web_value).strip()
            if local_value and current_web and local_value != current_web:
                conflicts.append(
                    {
                        "field": field_name,
                        "local_value": local_value,
                        "candidate_value": current_web,
                        "reason": "candidate_conflicts_with_manual_rule",
                    }
                )
        return conflicts
