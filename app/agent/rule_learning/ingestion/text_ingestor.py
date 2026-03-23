"""TXT/MD/raw text ingestor (Phase 1)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


KEYWORDS = ["规则", "映射", "后缀", "前缀", "字段", "示例", "pattern", "regex", "rule"]


def _split_text_blocks(text: str) -> List[str]:
    blocks = re.split(r"\n\s*\n+", text)
    out: List[str] = []
    for b in blocks:
        t = re.sub(r"\s+", " ", b).strip()
        if t:
            out.append(t)
    return out


class TextIngestor:
    """Ingest txt/md/raw text into unified rule-learning chunks."""

    def ingest(self, text: str, file_name: Optional[str] = None, input_type: str = "text") -> Tuple[List[Dict[str, Any]], List[str]]:
        extracted_at = datetime.utcnow().isoformat()
        chunks: List[Dict[str, Any]] = []
        warnings: List[str] = []

        content = (text or "").strip()
        if not content:
            return [], ["文本内容为空"]

        blocks = _split_text_blocks(content)
        current_section = "Text"
        chunk_idx = 0

        for block in blocks:
            # Markdown heading as section title.
            if block.startswith("#"):
                current_section = re.sub(r"^#+\s*", "", block).strip() or current_section

            quality = "rule_like" if any(k.lower() in block.lower() for k in KEYWORDS) else "plain"
            chunks.append(
                {
                    "chunk_id": f"{input_type}::{file_name or 'inline'}::{chunk_idx}",
                    "input_type": input_type,
                    "file_name": file_name or "inline_text",
                    "sheet_name": None,
                    "page": None,
                    "section_title": current_section,
                    "raw_text": block,
                    "metadata": {
                        "quality": quality,
                        "length": len(block),
                    },
                    "extracted_at": extracted_at,
                }
            )
            chunk_idx += 1

        if not chunks:
            warnings.append("文本未提取到任何 chunk")

        return chunks, warnings

    def ingest_file(self, file_path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文本文件不存在: {file_path}")
        suffix = path.suffix.lower()
        input_type = "md" if suffix == ".md" else "text"
        text = path.read_text(encoding="utf-8", errors="ignore")
        return self.ingest(text=text, file_name=path.name, input_type=input_type)
