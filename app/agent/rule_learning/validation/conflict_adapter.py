"""Adapter to reuse existing conflict detection and repository baselines (Phase 3)."""

from __future__ import annotations

from typing import Any, Dict, List

from app.agent.rule_learning.rule_repository import RuleRepository


class ConflictAdapter:
    """Check candidate rules against manual layer and extension layer."""

    def __init__(self, repo: RuleRepository):
        self.repo = repo

    @staticmethod
    def _norm(x: Any) -> str:
        return ("" if x is None else str(x)).strip().lower()

    def _manual_rule_conflicts(self, candidate: Dict[str, Any], manual_rules: List[dict]) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        c_brand = self._norm(candidate.get("brand"))
        c_cat = self._norm(candidate.get("category"))
        c_pattern = candidate.get("pattern") if isinstance(candidate.get("pattern"), dict) else {}
        c_p_match = self._norm(c_pattern.get("match_type"))
        c_p_value = self._norm(c_pattern.get("value"))

        c_output = candidate.get("output") if isinstance(candidate.get("output"), dict) else {}

        for mr in manual_rules:
            m_brand = self._norm(mr.get("brand"))
            m_cat = self._norm(mr.get("category"))
            if c_brand and m_brand and c_brand != m_brand:
                continue
            if c_cat and m_cat and c_cat != m_cat:
                continue

            m_pattern = self._norm(mr.get("pattern"))
            if c_p_match == "regex" and c_p_value and m_pattern and c_p_value == m_pattern:
                conflicts.append(
                    {
                        "reason": "duplicate_with_manual_rule",
                        "manual_rule_id": mr.get("rule_id", ""),
                        "field": "pattern",
                        "manual_value": mr.get("pattern", ""),
                        "candidate_value": c_pattern,
                    }
                )

            # field-level check: candidate.output vs manual field_mapping expressions.
            fm = mr.get("field_mapping") if isinstance(mr.get("field_mapping"), dict) else {}
            for field_name, cand_value in c_output.items():
                if field_name not in fm:
                    continue
                manual_value = fm.get(field_name)
                if self._norm(cand_value) != self._norm(manual_value):
                    conflicts.append(
                        {
                            "reason": "candidate_conflicts_with_manual_field_mapping",
                            "manual_rule_id": mr.get("rule_id", ""),
                            "field": field_name,
                            "manual_value": manual_value,
                            "candidate_value": cand_value,
                        }
                    )

        return conflicts

    def _extension_rule_duplicates(self, candidate: Dict[str, Any], extension_rules: List[dict]) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        c_brand = self._norm(candidate.get("brand"))
        c_cat = self._norm(candidate.get("category"))
        c_rule_type = self._norm(candidate.get("rule_type"))
        c_pattern = candidate.get("pattern") if isinstance(candidate.get("pattern"), dict) else {}
        c_p_match = self._norm(c_pattern.get("match_type"))
        c_p_value = self._norm(c_pattern.get("value"))

        for er in extension_rules:
            if self._norm(er.get("status")) == "rejected":
                continue
            if c_brand and self._norm(er.get("brand")) and c_brand != self._norm(er.get("brand")):
                continue
            if c_cat and self._norm(er.get("category")) and c_cat != self._norm(er.get("category")):
                continue

            e_pattern = er.get("pattern") if isinstance(er.get("pattern"), dict) else {}
            e_p_match = self._norm(e_pattern.get("match_type"))
            e_p_value = self._norm(e_pattern.get("value"))
            e_rule_type = self._norm(er.get("rule_type"))

            if c_rule_type == e_rule_type and c_p_match == e_p_match and c_p_value and c_p_value == e_p_value:
                conflicts.append(
                    {
                        "reason": "duplicate_with_extension_rule",
                        "extension_rule_id": er.get("rule_id", ""),
                        "field": "pattern",
                        "manual_value": e_pattern,
                        "candidate_value": c_pattern,
                    }
                )
        return conflicts

    def check_conflicts(self, candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
        manual_rules = self.repo.get_manual_rules_raw()
        extension_rules = self.repo.get_extension_rules_raw()
        conflicts = []
        conflicts.extend(self._manual_rule_conflicts(candidate, manual_rules))
        conflicts.extend(self._extension_rule_duplicates(candidate, extension_rules))
        return conflicts
