"""Rule validator for normalized learned rules (Phase 3)."""

from __future__ import annotations

from datetime import datetime
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


class RuleValidator:
    """Validate normalized rules and save candidates into extension layer."""

    def __init__(self, repo: RuleRepository):
        self.repo = repo
        self.conflict_adapter = ConflictAdapter(repo=repo)

    @staticmethod
    def _required_check(rule: Dict[str, Any]) -> List[str]:
        issues: List[str] = []
        for field in ["rule_id", "rule_type", "pattern", "source"]:
            if field not in rule or rule.get(field) in (None, "", {}):
                issues.append(f"missing_required_field:{field}")

        source = rule.get("source") if isinstance(rule.get("source"), dict) else {}
        if not source.get("source_type"):
            issues.append("missing_source_type")
        if not source.get("file_name") and source.get("source_type") != "manual":
            issues.append("missing_source_file_name")
        return issues

    @staticmethod
    def _quality_check(rule: Dict[str, Any]) -> List[str]:
        issues: List[str] = []
        confidence = 0.0
        try:
            confidence = float(rule.get("confidence", 0.0))
        except Exception:
            issues.append("invalid_confidence")
        if confidence < 0.35:
            issues.append("low_confidence")
        examples = rule.get("examples")
        if not isinstance(examples, list) or len(examples) == 0:
            issues.append("missing_examples")
        return issues

    def validate_and_store(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        conflict_items: List[Dict[str, Any]] = []

        now = datetime.utcnow().isoformat()

        for rule in rules:
            issues = []
            issues.extend(self._required_check(rule))
            issues.extend(self._quality_check(rule))

            conflicts = self.conflict_adapter.check_conflicts(rule)
            if conflicts:
                issues.append("conflict_detected")
                for c in conflicts:
                    conflict_items.append(
                        {
                            "detected_at": now,
                            "rule_id": rule.get("rule_id", ""),
                            "brand": rule.get("brand", ""),
                            **c,
                        }
                    )

            if issues:
                rejected.append(
                    {
                        "rule_id": rule.get("rule_id", ""),
                        "issues": issues,
                        "status": "rejected",
                    }
                )
                continue

            candidate = dict(rule)
            candidate["status"] = candidate.get("status") or "validated"
            candidate["updated_at"] = now
            self.repo.upsert_extension_rule(candidate)
            accepted.append(candidate)

        if conflict_items:
            self.repo.append_conflicts(conflict_items)

        self.repo.append_update_log(
            {
                "event_type": "rule_validation_batch",
                "created_at": now,
                "total": len(rules),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "conflicts": len(conflict_items),
                "accepted_rule_ids": [r.get("rule_id", "") for r in accepted],
                "rejected_rule_ids": [r.get("rule_id", "") for r in rejected],
            }
        )

        return {
            "total": len(rules),
            "accepted": accepted,
            "rejected": rejected,
            "conflicts": conflict_items,
        }
