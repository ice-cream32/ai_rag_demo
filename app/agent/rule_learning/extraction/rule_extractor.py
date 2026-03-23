"""Rule extractor from ingestion chunks (Phase 2)."""

from __future__ import annotations

import re
from typing import Any, Dict, List


class RuleExtractor:
    """Extract rule candidates from chunk raw text using pattern heuristics."""

    BRAND_KEYWORDS = {
        "micron": "Micron",
        "samsung": "Samsung",
        "hynix": "SK Hynix",
        "kioxia": "Kioxia",
        "spectek": "Spectek",
    }

    def _detect_brand(self, text: str) -> str:
        low = text.lower()
        for k, v in self.BRAND_KEYWORDS.items():
            if k in low:
                return v
        return ""

    def _detect_rule_type(self, text: str) -> str:
        low = text.lower()
        if "prefix" in low or "前缀" in text:
            return "prefix_match"
        if "suffix" in low or "后缀" in text:
            return "suffix_match"
        if "regex" in low or "正则" in text:
            return "regex_match"
        if "映射" in text or "map" in low:
            return "enum_mapping"
        if "示例" in text or "example" in low:
            return "example_mapping"
        if "公式" in text or "formula" in low:
            return "formula_rule"
        return "generic_rule"

    def _extract_pattern(self, text: str) -> Dict[str, Any]:
        # Regex literal
        regex = re.search(r"(\^.{2,120}\$)", text)
        if regex:
            return {"match_type": "regex", "value": regex.group(1)}

        # Prefix / suffix hints
        prefix = re.search(r"(?:prefix|前缀)\s*[:：]?\s*([A-Za-z0-9_-]{1,16})", text, re.IGNORECASE)
        if prefix:
            return {"match_type": "prefix", "value": prefix.group(1)}

        suffix = re.search(r"(?:suffix|后缀)\s*[:：]?\s*([A-Za-z0-9_-]{1,16})", text, re.IGNORECASE)
        if suffix:
            return {"match_type": "suffix", "value": suffix.group(1)}

        # Fallback by part number like token
        token = re.search(r"\b[A-Z]{2,6}[0-9A-Z\-]{3,40}\b", text)
        if token:
            return {"match_type": "contains", "value": token.group(0)}

        return {"match_type": "text", "value": text[:80]}

    def _extract_examples(self, text: str) -> List[str]:
        tokens = re.findall(r"\b[A-Z]{2,8}[0-9A-Z\-]{4,48}\b", text)
        uniq: List[str] = []
        for t in tokens:
            if t not in uniq:
                uniq.append(t)
            if len(uniq) >= 5:
                break
        return uniq

    def extract(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        for idx, chunk in enumerate(chunks):
            raw_text = str(chunk.get("raw_text", "")).strip()
            if not raw_text:
                continue

            # Heuristic: only keep rule-like chunks
            low = raw_text.lower()
            if not any(k in low for k in ["rule", "regex", "prefix", "suffix", "mapping", "example"]) and not any(k in raw_text for k in ["规则", "前缀", "后缀", "映射", "示例"]):
                continue

            candidates.append(
                {
                    "candidate_id": f"cand_{idx}",
                    "brand": self._detect_brand(raw_text),
                    "category": "",
                    "sub_category": "",
                    "rule_type": self._detect_rule_type(raw_text),
                    "field": "",
                    "pattern": self._extract_pattern(raw_text),
                    "output": {},
                    "examples": self._extract_examples(raw_text),
                    "source": {
                        "source_type": chunk.get("input_type", "unknown"),
                        "file_name": chunk.get("file_name", ""),
                        "sheet_name": chunk.get("sheet_name"),
                        "page": chunk.get("page"),
                        "raw_text": raw_text,
                        "chunk_id": chunk.get("chunk_id", ""),
                    },
                    "confidence": 0.55,
                    "status": "candidate",
                }
            )

        return candidates
