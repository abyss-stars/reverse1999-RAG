"""章节表与「按章节/版本过滤」的判定。

数据源是 `state/chapter_index.json`（由 pipeline 侧生成，81 章，
每章有 order / chapter_no / title / category / version / version_source）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from . import config


@lru_cache(maxsize=1)
def load_index() -> dict:
    return json.loads(config.CHAPTER_INDEX.read_text(encoding="utf-8"))


def chapters() -> list[dict]:
    return load_index().get("chapters", [])


def _basename(p: str) -> str:
    return (p or "").replace("\\", "/").split("/")[-1].strip()


@lru_cache(maxsize=1)
def file_to_chapter() -> dict[str, dict]:
    return {c["filename"]: c for c in chapters()}


def resolve_file(file_path: str) -> dict | None:
    return file_to_chapter().get(_basename(file_path))


@dataclass
class FilterSpec:
    """检索范围限定。所有字段为空 = 不过滤。"""

    categories: list[str] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    chapters: list[str] = field(default_factory=list)
    min_order: int | None = None
    max_order: int | None = None

    @classmethod
    def from_payload(cls, d: dict | None) -> "FilterSpec":
        d = d or {}
        return cls(
            categories=[str(x) for x in (d.get("categories") or [])],
            versions=[str(x) for x in (d.get("versions") or [])],
            sources=[str(x) for x in (d.get("sources") or [])],
            chapters=[str(x) for x in (d.get("chapters") or [])],
            min_order=d.get("min_order"),
            max_order=d.get("max_order"),
        )

    def is_active(self) -> bool:
        return bool(
            self.categories
            or self.versions
            or self.sources
            or self.chapters
            or self.min_order is not None
            or self.max_order is not None
        )

    def describe(self) -> str:
        parts: list[str] = []
        if self.categories:
            parts.append("分类=" + "/".join(self.categories))
        if self.versions:
            parts.append("版本=" + "/".join(self.versions))
        if self.sources:
            parts.append("来源=" + "/".join(self.sources))
        if self.chapters:
            parts.append("章号=" + "/".join(self.chapters))
        if self.min_order is not None or self.max_order is not None:
            lo = self.min_order if self.min_order is not None else 1
            hi = self.max_order if self.max_order is not None else "末"
            parts.append(f"阅读顺序={lo}~{hi}")
        return " 且 ".join(parts) if parts else "不过滤"

    def match(self, ch: dict) -> bool:
        if self.categories and ch.get("category") not in self.categories:
            return False
        if self.versions and (ch.get("version") or "") not in self.versions:
            return False
        if self.sources and (ch.get("version_source") or "null") not in self.sources:
            return False
        if self.chapters and str(ch.get("chapter_no")) not in self.chapters:
            return False
        order = ch.get("order")
        if isinstance(order, int):
            if self.min_order is not None and order < self.min_order:
                return False
            if self.max_order is not None and order > self.max_order:
                return False
        return True


def allowed_files(spec: FilterSpec) -> set[str]:
    """返回过滤后允许参与检索的**文件名**集合。空集合表示"没有任何章节命中"。"""
    return {c["filename"] for c in chapters() if spec.match(c)}


def matched_chapters(spec: FilterSpec) -> list[dict]:
    return [c for c in chapters() if spec.match(c)]


def chunk_total_from_manifest() -> int | None:
    """从 index_manifest.json 汇总 chunks_count —— 比问后端便宜且离线可算。

    真实结构是 `{"docs": {"<文件名>": {..., "chunks_count": N}}}`（其余顶层键是
    format/generated_at/corpus/config_fingerprint/counts 等元信息，**没有** chunks_count）。
    这里对几种可能形状都兜一下，兜不到就返回 None（前端回退常量），不猜。
    """
    try:
        data = json.loads(config.INDEX_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    candidates: list[Any] = []
    docs = data.get("docs")
    if isinstance(docs, dict):
        candidates = list(docs.values())
    elif isinstance(docs, list):
        candidates = docs
    else:
        # 老/别的形状：chapters 列表，或本身就是 {文件名: {...}}
        alt = data.get("chapters")
        if isinstance(alt, list):
            candidates = alt
        elif all(isinstance(v, dict) for v in data.values()):
            candidates = list(data.values())

    total = 0
    found = False
    for it in candidates:
        if isinstance(it, dict) and isinstance(it.get("chunks_count"), int):
            total += it["chunks_count"]
            found = True
    return total if found else None
