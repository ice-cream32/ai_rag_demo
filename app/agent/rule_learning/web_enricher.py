"""联网补全器：补齐缺失字段并抓取图片。"""

from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.agent.rule_learning.image_searcher import ImageSearcher


class WebEnricher:
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self.image_searcher = ImageSearcher(timeout=timeout)

    @staticmethod
    def _clean_text(html: str) -> str:
        text = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\\s+", " ", text)
        return text.strip()

    @staticmethod
    def _unwrap_ddg_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            if "uddg" in qs and qs["uddg"]:
                return unquote(qs["uddg"][0])
        except Exception:
            pass
        return url

    def _search_pages(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        pages: List[Dict[str, str]] = []
        try:
            resp = httpx.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            html = resp.text
        except Exception:
            return pages

        # DDG 结果链接通常在 result__a 这个 class 中
        for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([\\s\\S]*?)</a>', html, re.IGNORECASE):
            raw_url, title_html = m.group(1), m.group(2)
            url = self._unwrap_ddg_url(raw_url)
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            if url.startswith("http"):
                pages.append({"url": url, "title": title})
            if len(pages) >= limit:
                break
        return pages

    @staticmethod
    def _extract_brand(text: str) -> str:
        t = text.lower()
        if "micron" in t:
            return "Micron"
        if "samsung" in t:
            return "Samsung"
        if "sk hynix" in t or "hynix" in t:
            return "SK Hynix"
        if "kioxia" in t:
            return "Kioxia"
        return ""

    @staticmethod
    def _extract_first(patterns: List[str], text: str) -> str:
        for p in patterns:
            m = re.search(p, text, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    def _extract_fields(self, text: str) -> Dict[str, str]:
        return {
            "brand": self._extract_brand(text),
            "capacity": self._extract_first([r"\\b(\\d+(?:\\.\\d+)?\\s?(?:TB|GB|MB|Kb|Mb|Gb))\\b"], text),
            "bus_width": self._extract_first([r"\\b(x\\s?\\d{1,2})\\b", r"\\b(\\d{1,2}-bit)\\b"], text),
            "process_node": self._extract_first([r"\\b(\\d{1,3}\\s?nm)\\b"], text),
            "package": self._extract_first([r"\\b(FBGA\\s?\\d*|BGA\\s?\\d*|TSOP|LGA|QFN)\\b"], text),
            "speed": self._extract_first([r"\\b(\\d{3,5}\\s?MHz)\\b", r"\\b(\\d{3,5}\\s?MT/s)\\b"], text),
            "temperature_range": self._extract_first([r"(-?\\d+\\s?°?C\\s?(?:to|~|-)\\s?\\+?\\d+\\s?°?C)"], text),
        }

    def enrich(self, part_number: str, brand_hint: Optional[str] = None) -> Dict[str, object]:
        query = f"{part_number} datasheet package image {brand_hint or ''}".strip()
        pages = self._search_pages(query=query, limit=5)

        merged: Dict[str, str] = {}
        evidence: Dict[str, str] = {}
        for p in pages:
            try:
                resp = httpx.get(
                    p["url"],
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                text = self._clean_text(resp.text[:300000])
            except Exception:
                continue

            fields = self._extract_fields(text)
            for k, v in fields.items():
                if v and not merged.get(k):
                    merged[k] = v
                    evidence[k] = p["url"]

        images = self.image_searcher.search_images(
            part_number=part_number,
            brand=merged.get("brand") or (brand_hint or ""),
            pages=pages,
        )

        return {
            "fields": merged,
            "field_sources": evidence,
            "images": images,
            "pages": pages,
        }
