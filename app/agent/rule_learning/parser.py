"""本地优先的料号解析器。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.agent.rule_learning.local_matcher import LocalRuleMatcher
from app.agent.rule_learning.rule_updater import RuleUpdater
from app.agent.rule_learning.web_enricher import WebEnricher
from app.agent.rule_learning.schemas import MatchedRuleInfo, ParseResult, ParsedField, RuleRecord


class LocalRuleParser:
    def __init__(
        self,
        matcher: Optional[LocalRuleMatcher] = None,
        rule_updater: Optional[RuleUpdater] = None,
    ):
        self.matcher = matcher or LocalRuleMatcher()
        self.web_enricher = WebEnricher()
        self.rule_updater = rule_updater

    @staticmethod
    def _target_fields() -> List[str]:
        return [
            "brand",
            "category",
            "capacity",
            "bus_width",
            "process_node",
            "package",
            "speed",
            "temperature_range",
        ]

    @staticmethod
    def _resolve_value(expr: Any, part_number: str, groups: Dict[str, str], enums: Dict[str, Any]) -> Any:
        if expr is None:
            return ""
        if isinstance(expr, (int, float, bool)):
            return expr

        text = str(expr).strip()
        if not text:
            return ""

        # group:name -> 从正则命名分组取值
        if text.startswith("group:"):
            g = text.split(":", 1)[1].strip()
            return groups.get(g, "")

        # regex:<pattern>::<replace> -> 正则替换
        if text.startswith("regex:") and "::" in text:
            body = text.split(":", 1)[1]
            pattern, repl = body.split("::", 1)
            try:
                return re.sub(pattern.strip(), repl.strip(), part_number)
            except re.error:
                return ""

        # enum:key -> 从 enum_values 取映射值
        if text.startswith("enum:"):
            key = text.split(":", 1)[1].strip()
            return enums.get(key, "") if isinstance(enums, dict) else ""

        return text

    def parse(
        self,
        part_number: str,
        rules: List[RuleRecord],
        extension_rules: Optional[List[Dict[str, Any]]] = None,
        brand_hint: Optional[str] = None,
        enable_web_enrich: bool = True,
    ) -> ParseResult:
        pn = (part_number or "").strip().upper()
        if not pn:
            return ParseResult(
                part_number="",
                confidence=0.0,
                notes=["part_number 为空"],
            )

        extension_rules = extension_rules or []
        hit = self.matcher.match(part_number=pn, rules=rules, brand_hint=brand_hint)
        if not hit:
            ext_hit = self._match_extension_rule(pn, extension_rules, brand_hint=brand_hint)
            if ext_hit is not None:
                return self._build_extension_parse_result(part_number=pn, ext_hit=ext_hit)

            base = ParseResult(
                part_number=pn,
                confidence=0.0,
                notes=["本地规则未命中"],
            )
            if not enable_web_enrich:
                return base

            enriched = self.web_enricher.enrich(part_number=pn, brand_hint=brand_hint)
            web_fields = dict(enriched.get("fields") or {})
            for k, v in (enriched.get("fields") or {}).items():
                if v:
                    base.fields[k] = ParsedField(value=v, source="web_enriched_rule", rule_id="")
            base.images = list(enriched.get("images") or [])
            base.notes.append("已触发联网补全")
            if base.fields:
                base.confidence = 0.45
                base.notes.append("本地无命中，已使用联网补全缺失字段")
            else:
                base.notes.append("联网未检索到可用结构化字段")
            if base.images:
                base.notes.append(f"发现图片 {len(base.images)} 张")
            else:
                base.notes.append("未检索到可用图片")

            if self.rule_updater:
                update_result = self.rule_updater.update_from_web_enrichment(
                    part_number=pn,
                    brand=brand_hint or "",
                    matched_rule_id="",
                    local_fields={},
                    web_fields=web_fields,
                    field_sources=dict(enriched.get("field_sources") or {}),
                    images=base.images,
                )
                if update_result.get("updated"):
                    base.notes.append(f"已写入扩展规则层: {update_result.get('extension_rule_id')}")
                if update_result.get("conflicts"):
                    base.notes.append(f"检测到冲突: {len(update_result.get('conflicts') or [])} 项")
            return base

        rule = hit.rule
        fields: Dict[str, ParsedField] = {}
        mapping = rule.field_mapping or {}
        for field_name, expr in mapping.items():
            value = self._resolve_value(
                expr=expr,
                part_number=pn,
                groups=hit.groups,
                enums=rule.enum_values or {},
            )
            if value not in (None, ""):
                fields[str(field_name)] = ParsedField(
                    value=value,
                    source="local_xlsx_rule",
                    rule_id=rule.rule_id,
                )

        # 若无字段映射，至少返回规则基本信息
        if not fields:
            fields["brand"] = ParsedField(value=rule.brand or "", rule_id=rule.rule_id)
            fields["category"] = ParsedField(value=rule.category or "", rule_id=rule.rule_id)

        confidence = hit.score
        if len(fields) >= 3:
            confidence = min(0.99, confidence + 0.05)

        images: List[Dict[str, Any]] = []
        if enable_web_enrich:
            missing = [f for f in self._target_fields() if f not in fields]
            if missing:
                enriched = self.web_enricher.enrich(part_number=pn, brand_hint=brand_hint or rule.brand)
                ext_fields = enriched.get("fields") or {}
                for name in missing:
                    value = ext_fields.get(name)
                    if value:
                        # 不覆盖本地字段，仅补充缺失字段
                        fields[name] = ParsedField(
                            value=value,
                            source="web_enriched_rule",
                            rule_id=rule.rule_id,
                        )
                images = list(enriched.get("images") or [])
                if images:
                    confidence = min(0.99, confidence + 0.03)

                if self.rule_updater:
                    update_result = self.rule_updater.update_from_web_enrichment(
                        part_number=pn,
                        brand=rule.brand or (brand_hint or ""),
                        matched_rule_id=rule.rule_id,
                        local_fields={k: v for k, v in fields.items() if v.source == "local_xlsx_rule"},
                        web_fields=ext_fields,
                        field_sources=dict(enriched.get("field_sources") or {}),
                        images=images,
                    )
                    if update_result.get("updated"):
                        images_count = int(update_result.get("images_count") or 0)
                        confidence = min(0.99, confidence + (0.02 if images_count > 0 else 0.0))

        return ParseResult(
            part_number=pn,
            fields=fields,
            matched_rule=MatchedRuleInfo(
                rule_id=rule.rule_id,
                source_type="local_xlsx_rule",
                brand=rule.brand,
                category=rule.category,
                pattern=rule.pattern,
            ),
            images=images,
            confidence=round(confidence, 4),
            notes=[
                f"命中本地规则: {rule.rule_id}",
                f"本地规则字段: {len([f for f in fields.values() if f.source == 'local_xlsx_rule'])} 项",
                f"联网补全字段: {len([f for f in fields.values() if f.source == 'web_enriched_rule'])} 项",
                f"图片结果: {len(images)} 项",
            ],
        )

    @staticmethod
    def _match_extension_rule(
        part_number: str,
        extension_rules: List[Dict[str, Any]],
        brand_hint: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        pn = (part_number or "").strip().upper()
        hint = (brand_hint or "").strip().lower()

        for rule in extension_rules:
            status = str(rule.get("status", "")).strip().lower()
            if status == "rejected":
                continue

            brand = str(rule.get("brand", "")).strip().lower()
            if hint and brand and brand != hint:
                continue

            pattern = rule.get("pattern") if isinstance(rule.get("pattern"), dict) else {}
            match_type = str(pattern.get("match_type", "")).strip().lower()
            value = str(pattern.get("value", "")).strip()
            if not value:
                continue

            matched = False
            if match_type == "prefix":
                matched = pn.startswith(value.upper())
            elif match_type == "suffix":
                matched = pn.endswith(value.upper())
            elif match_type == "contains":
                matched = value.upper() in pn
            elif match_type == "regex":
                try:
                    matched = re.search(value, pn) is not None
                except re.error:
                    matched = False

            if matched:
                return rule

        return None

    @staticmethod
    def _build_extension_parse_result(part_number: str, ext_hit: Dict[str, Any]) -> ParseResult:
        output = ext_hit.get("output") if isinstance(ext_hit.get("output"), dict) else {}
        fields: Dict[str, ParsedField] = {}
        for name, value in output.items():
            if value in (None, ""):
                continue
            fields[str(name)] = ParsedField(
                value=value,
                source="web_enriched_rule",
                rule_id=str(ext_hit.get("rule_id", "")),
            )

        confidence = 0.5
        try:
            confidence = float(ext_hit.get("confidence", 0.5))
        except Exception:
            confidence = 0.5

        return ParseResult(
            part_number=part_number,
            fields=fields,
            matched_rule=MatchedRuleInfo(
                rule_id=str(ext_hit.get("rule_id", "")),
                source_type="web_enriched_rule",
                brand=str(ext_hit.get("brand", "")),
                category=str(ext_hit.get("category", "")),
                pattern=str((ext_hit.get("pattern") or {}).get("value", "")),
            ),
            images=[],
            confidence=max(0.0, min(1.0, confidence)),
            notes=["未命中人工主规则，已命中扩展规则层"],
        )
