"""PDF ingestor with page-preserving chunking (Phase 1)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz


def _split_paragraphs(text: str) -> List[str]:
    blocks = re.split(r"\n\s*\n+", text)
    chunks: List[str] = []
    for block in blocks:
        item = re.sub(r"\s+", " ", block).strip()
        if item:
            chunks.append(item)
    return chunks


class PdfIngestor:
    """Ingest pdf pages into unified rule-learning chunks."""

    def ingest(self, file_path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"pdf 文件不存在: {file_path}")

        extracted_at = datetime.utcnow().isoformat()
        chunks: List[Dict[str, Any]] = []
        warnings: List[str] = []
        chunk_idx = 0

        doc = fitz.open(str(path))
        try:
            for i, page in enumerate(doc):
                page_num = i + 1
                text = page.get_text("text") or ""
                paragraphs = _split_paragraphs(text)

                if not paragraphs:
                    warnings.append(f"page={page_num}: 无可提取文本")
                    continue

                # 普通段落
                for para in paragraphs:
                    chunks.append(
                        {
                            "chunk_id": f"pdf::{path.name}::p{page_num}::{chunk_idx}",
                            "input_type": "pdf",
                            "file_name": path.name,
                            "sheet_name": None,
                            "page": page_num,
                            "section_title": f"Page {page_num}",
                            "raw_text": para,
                            "metadata": {
                                "parser": "fitz.text",
                                "page_index": page_num,
                            },
                            "extracted_at": extracted_at,
                        }
                    )
                    chunk_idx += 1

                # 简易表格线索（包含 | 或连续多空格）
                table_like = [ln.strip() for ln in text.splitlines() if ("|" in ln or re.search(r"\S\s{2,}\S", ln))]
                if table_like:
                    chunks.append(
                        {
                            "chunk_id": f"pdf::{path.name}::p{page_num}::table::{chunk_idx}",
                            "input_type": "pdf",
                            "file_name": path.name,
                            "sheet_name": None,
                            "page": page_num,
                            "section_title": f"Page {page_num} TableLike",
                            "raw_text": "\n".join(table_like[:120]),
                            "metadata": {
                                "parser": "fitz.table_like",
                                "page_index": page_num,
                                "line_count": len(table_like),
                            },
                            "extracted_at": extracted_at,
                        }
                    )
                    chunk_idx += 1
        finally:
            doc.close()

        if not chunks:
            warnings.append("pdf 未提取到任何 chunk")

        return chunks, warnings
