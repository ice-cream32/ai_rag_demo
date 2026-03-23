"""本地规则匹配器。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from app.agent.rule_learning.schemas import RuleRecord


@dataclass
class MatchHit:
    rule: RuleRecord
    score: float
    groups: dict[str, str]


class LocalRuleMatcher:
    """使用本地 xlsx 规则匹配料号。"""

    def match(
        self,
        part_number: str,
        rules: List[RuleRecord],
        brand_hint: Optional[str] = None,
    ) -> Optional[MatchHit]:
        pn = (part_number or "").strip().upper()
        if not pn:
            return None

        candidates = rules
        if brand_hint:
            hint = brand_hint.strip().lower()
            candidates = [r for r in rules if (r.brand or "").strip().lower() == hint] or rules

        best: Optional[MatchHit] = None
        for rule in candidates:
            pattern = (rule.pattern or "").strip()
            if not pattern:
                continue
            try:
                m = re.match(pattern, pn)
            except re.error:
                continue
            if not m:
                continue

            # 基础得分：正则命中 + 品牌提示加成 + 字段映射数量加成
            score = 0.60
            if brand_hint and (rule.brand or "").strip().lower() == brand_hint.strip().lower():
                score += 0.15
            if rule.field_mapping:
                score += min(0.25, len(rule.field_mapping) * 0.03)

            hit = MatchHit(
                rule=rule,
                score=min(score, 0.99),
                groups={k: (v or "") for k, v in m.groupdict().items()},
            )
            if best is None or hit.score > best.score:
                best = hit

        return best
