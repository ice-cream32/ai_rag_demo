"""规则学习工具函数。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Optional


def norm_header(name: str) -> str:
    text = (name or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    return text


def pick_first(d: Dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return default


def parse_loose_mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    text = str(value).strip()
    if not text:
        return {}

    # 优先按 JSON 解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 回退解析：a:b; c:d 或 a=b, c=d
    out: Dict[str, Any] = {}
    chunks = re.split(r"[;；\n,，]", text)
    for chunk in chunks:
        part = chunk.strip()
        if not part:
            continue
        if ":" in part:
            k, v = part.split(":", 1)
        elif "=" in part:
            k, v = part.split("=", 1)
        else:
            continue
        key = k.strip()
        val = v.strip()
        if key:
            out[key] = val
    return out


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_rule_id(brand: str, category: str, pattern: str, sheet: str, row: int) -> str:
    base = "_".join(
        x for x in [brand.strip().lower(), category.strip().lower(), pattern.strip().lower()] if x
    )
    base = re.sub(r"[^a-z0-9_]+", "_", base).strip("_")
    if not base:
        base = f"rule_{sheet.lower()}_{row}"
    return base[:96]
