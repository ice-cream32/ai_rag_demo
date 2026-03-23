"""从候选网页中提取图片信息。"""

from __future__ import annotations

import re
from typing import Dict, List
from urllib.parse import urljoin

import httpx


class ImageSearcher:
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    @staticmethod
    def _normalize_img_url(source_url: str, raw_url: str) -> str:
        raw = (raw_url or "").strip().strip('"').strip("'")
        if not raw:
            return ""
        if raw.startswith("data:"):
            return ""
        return urljoin(source_url, raw)

    @staticmethod
    def _match_level(part_number: str, title: str, alt_text: str) -> str:
        hay = f"{title} {alt_text}".lower()
        pn = (part_number or "").lower()
        if pn and pn in hay:
            return "exact"
        if any(k in hay for k in ["package", "封装", "fbga", "bga", "tsop", "lga"]):
            return "package_only"
        return "similar"

    def search_images(self, part_number: str, brand: str, pages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        seen = set()

        for page in pages[:5]:
            source_url = page.get("url", "")
            title = page.get("title", "")
            if not source_url:
                continue
            try:
                resp = httpx.get(
                    source_url,
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                html = resp.text[:300000]
            except Exception:
                continue

            # 优先使用 og:image
            og_match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                html,
                flags=re.IGNORECASE,
            )
            if og_match:
                img_url = self._normalize_img_url(source_url, og_match.group(1))
                if img_url and img_url not in seen:
                    seen.add(img_url)
                    out.append(
                        {
                            "image_url": img_url,
                            "source_url": source_url,
                            "title": title,
                            "alt_text": "",
                            "match_level": self._match_level(part_number, title, ""),
                            "brand": brand,
                            "part_number": part_number,
                        }
                    )

            # 回退抓取前几个 <img>
            img_matches = re.findall(
                r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
                html,
                flags=re.IGNORECASE,
            )
            alt_matches = re.findall(
                r'<img[^>]+alt=["\']([^"\']*)["\'][^>]*>',
                html,
                flags=re.IGNORECASE,
            )
            for idx, raw in enumerate(img_matches[:4]):
                img_url = self._normalize_img_url(source_url, raw)
                if not img_url or img_url in seen:
                    continue
                seen.add(img_url)
                alt_text = alt_matches[idx] if idx < len(alt_matches) else ""
                out.append(
                    {
                        "image_url": img_url,
                        "source_url": source_url,
                        "title": title,
                        "alt_text": alt_text,
                        "match_level": self._match_level(part_number, title, alt_text),
                        "brand": brand,
                        "part_number": part_number,
                    }
                )
                if len(out) >= 8:
                    return out

        return out
