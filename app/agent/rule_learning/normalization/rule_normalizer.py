"""Normalize extracted candidates to unified rule objects (Phase 2)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List

from app.agent.rule_learning.utils import norm_header


class SynonymMapper:
    """Map heterogeneous field names to canonical semantic keys."""

    DEFAULT_MAP: Dict[str, set[str]] = {
        "brand": {"品牌", "品牌名", "品牌中文名称", "manufacturer", "厂商", "brand"},
        "category": {"类别", "分类", "产品类型", "type", "category"},
        "sub_category": {"子类别", "子类型", "subtype", "sub_category"},
        "field": {"字段", "目标字段", "field", "field_name"},
        "pattern": {"规则", "匹配规则", "regex", "pattern", "rule"},
        "output": {"输出", "映射值", "结果", "output", "mapping"},
        "examples": {"示例", "样例", "example", "examples"},
        "rule_type": {"规则类型", "type_of_rule", "ruletype", "rule_type"},
        "capacity": {"容量", "容量字符串", "density", "capacity"},
        "wafer_model": {"晶圆型号", "wafer model", "wafer_model"},
        "bus_width": {"位宽", "宽度", "bus width", "bus_width"},
        "speed": {"速度", "频率", "speed", "frequency"},
        "temperature_range": {"温度", "温度范围", "temperature", "temperature_range"},
        "package": {"封装", "ball", "球位", "package"},
        "prefix": {"前缀", "prefix"},
        "suffix": {"后缀", "suffix"},
    }

    def __init__(self, custom_map: Dict[str, set[str]] | None = None):
        merged = dict(self.DEFAULT_MAP)
        if custom_map:
            for k, v in custom_map.items():
                merged[k] = set(merged.get(k, set())) | set(v)
        self._map = {
            canonical: {norm_header(x) for x in aliases | {canonical}}
            for canonical, aliases in merged.items()
        }

    def normalize_key(self, key: str) -> str:
        raw = norm_header(key)
        for canonical, aliases in self._map.items():
            if raw in aliases:
                return canonical
        return re.sub(r"\s+", "_", (key or "").strip().lower()) or "unknown"

    def normalize_record_keys(self, record: Dict[str, object]) -> Dict[str, object]:
        return {self.normalize_key(k): v for k, v in record.items()}


class RuleNormalizer:
    """Convert heterogeneous extracted candidates into canonical rule schema."""

    def __init__(self, synonym_mapper: SynonymMapper | None = None):
        self.synonym_mapper = synonym_mapper or SynonymMapper()

    @staticmethod
    def _gen_rule_id(seed: str) -> str:
        digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
        return f"generated_{digest}"

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            f = float(value)
            return max(0.0, min(1.0, f))
        except Exception:
            return 0.5

    def normalize_one(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        c = self.synonym_mapper.normalize_record_keys(candidate)
        src = c.get("source", {}) if isinstance(c.get("source"), dict) else {}

        now = datetime.utcnow().isoformat()
        seed = "|".join(
            [
                str(c.get("brand", "")),
                str(c.get("category", "")),
                str(c.get("rule_type", "")),
                str(c.get("pattern", "")),
                str(src.get("file_name", "")),
                str(src.get("chunk_id", "")),
            ]
        )

        return {
            "rule_id": c.get("rule_id") or self._gen_rule_id(seed),
            "brand": c.get("brand", ""),
            "category": c.get("category", ""),
            "sub_category": c.get("sub_category", ""),
            "rule_type": c.get("rule_type", "generic_rule"),
            "field": c.get("field", ""),
            "pattern": c.get("pattern", {}),
            "output": c.get("output", {}),
            "examples": c.get("examples", []),
            "source": {
                "source_type": src.get("source_type", "unknown"),
                "file_name": src.get("file_name", ""),
                "sheet_name": src.get("sheet_name"),
                "page": src.get("page"),
                "raw_text": src.get("raw_text", ""),
                "chunk_id": src.get("chunk_id", ""),
            },
            "confidence": self._clamp_confidence(c.get("confidence", 0.5)),
            "status": c.get("status", "candidate"),
            "priority": int(c.get("priority", 50) or 50),
            "version": int(c.get("version", 1) or 1),
            "created_at": c.get("created_at", now),
            "updated_at": now,
            "approved_by_human": bool(c.get("approved_by_human", False)),
        }

    def normalize(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.normalize_one(c) for c in candidates]
