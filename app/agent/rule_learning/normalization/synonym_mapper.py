"""Synonym mapper for field normalization (Phase 2)."""

from __future__ import annotations

import re
from typing import Dict

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
