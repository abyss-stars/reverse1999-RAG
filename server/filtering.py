"""按章节/版本裁剪 LightRAG 的检索上下文。

这是薄服务层**唯一真正新增的逻辑**，所以单独成模块并带单元测试
（`server/test_filtering.py`，不联网、不起服务）。

上下文形状（实测自 `scripts/dump_context_format.py`）::

    Knowledge Graph Data (Entity):
    ```json
    {"entity": "箱子", "type": "location", "description": "…"}     ← 每行一个 JSON
    ```

    Knowledge Graph Data (Relationship):
    ```json
    {"entity1": …, "entity2": …, "description": …}
    ```

    Document Chunks (Each entry has a reference_id refer to the `Reference Document List`; …):
    ```json
    {"reference_id": "2", "content": "…"}                          ← 同一 reference_id 可多行
    ```

    Reference Document List (Each entry starts with a [reference_id] …):
    ```json
    [1] 36101-人们向何处去.md                                       ← 一文件一条
    ```

两个关键事实（决定了本模块的做法）：

1. **Document Chunks 带 `reference_id`**，而 `references[]` 给出 `reference_id → file_path`，
   于是能精确地把 chunk 过滤到"只保留目标章节"。
2. **KG 段不带任何来源字段** —— 实体/关系行里没有 `file_path`、没有 `reference_id`。
   所以**图谱部分无法只靠上下文按章节过滤**。本模块在启用过滤时**整段丢弃 KG**，
   并在返回的 stats 里如实标注；这比"留着让模型看到范围外的事实"更安全。
   （更彻底的做法是按 DB 里 `lightrag_entity_chunks` / `lightrag_doc_chunks` 反查实体所属章节，
   见 server/README.md 的「后续升级」。）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# 段标记：用**前缀**匹配，避免上游改文案就失效
SEC_ENTITY = "Knowledge Graph Data (Entity)"
SEC_RELATION = "Knowledge Graph Data (Relationship)"
SEC_CHUNKS = "Document Chunks"
SEC_REFLIST = "Reference Document List"

_REF_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")


@dataclass
class PruneStats:
    """裁剪前后的规模，随响应回给前端（便于用户知道"过滤掉多少"）。"""

    chunks_before: int = 0
    chunks_after: int = 0
    refs_before: int = 0
    refs_after: int = 0
    kg_dropped: bool = False
    dropped_ref_ids: list[str] = field(default_factory=list)
    kept_ref_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "chunks_before": self.chunks_before,
            "chunks_after": self.chunks_after,
            "refs_before": self.refs_before,
            "refs_after": self.refs_after,
            "kg_dropped": self.kg_dropped,
            "dropped_ref_ids": self.dropped_ref_ids,
            "kept_ref_ids": self.kept_ref_ids,
        }


def _section_of(line: str) -> str | None:
    """判断某一行是不是段标题；是则返回归一化段名。"""
    s = line.strip()
    if s.startswith(SEC_ENTITY):
        return SEC_ENTITY
    if s.startswith(SEC_RELATION):
        return SEC_RELATION
    if s.startswith(SEC_CHUNKS):
        return SEC_CHUNKS
    if s.startswith(SEC_REFLIST):
        return SEC_REFLIST
    return None


def split_sections(text: str) -> dict[str, list[str]]:
    """把上下文按段拆开，返回 {段名: 行列表}（含段标题行本身）。"""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        sec = _section_of(line)
        if sec:
            current = sec
            out.setdefault(current, []).append(line)
            continue
        if current is None:
            out.setdefault("__head__", []).append(line)
        else:
            out[current].append(line)
    return out


def _ref_id_of_chunk_line(line: str) -> str | None:
    s = line.strip()
    if not s.startswith("{"):
        return None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    rid = obj.get("reference_id")
    return str(rid) if rid is not None else None


def prune_context(text: str, keep_ids: set[str], *, drop_kg: bool = True) -> tuple[str, PruneStats]:
    """只保留 `keep_ids` 里的引用对应的 chunk 与引用行。

    Args:
        text: LightRAG `only_need_context` 返回的上下文。
        keep_ids: 允许保留的 reference_id 字符串集合。
        drop_kg: 是否丢弃 KG 两段（实体/关系无来源字段，无法按章节过滤）。

    Returns:
        (裁剪后的上下文, 统计)。若上下文里没有可识别的 Document Chunks 段，
        则**原样返回**并置 `chunks_before=chunks_after=0` —— 这时候过滤是失效的，
        调用方必须据此判断（宁可不过滤，也不要返回一段被截坏的东西）。
    """
    stats = PruneStats()
    secs = split_sections(text)
    if SEC_CHUNKS not in secs:
        return text, stats  # 无法识别 → 不动

    # 先统计"原始引用行"，并据此算出被丢掉哪些 id
    raw_ref_ids: list[str] = []
    for line in secs.get(SEC_REFLIST, []):
        m = _REF_LINE_RE.match(line.strip())
        if m:
            raw_ref_ids.append(m.group(1))
    stats.refs_before = len(raw_ref_ids)

    kept_ref_lines: list[str] = []
    kept_declared: list[str] = []
    for line in secs.get(SEC_REFLIST, []):
        m = _REF_LINE_RE.match(line.strip())
        if not m:
            kept_ref_lines.append(line)
            continue
        if m.group(1) in keep_ids:
            kept_ref_lines.append(line)
            kept_declared.append(m.group(1))

    stats.refs_after = len(kept_declared)
    stats.kept_ref_ids = kept_declared
    stats.dropped_ref_ids = [r for r in raw_ref_ids if r not in keep_ids]

    # chunk 行的合法性以引用表为权威：引用表非空时，未声明的 id 一律丢弃
    # （引用表为空/缺失时无法校验，退化为只按 keep_ids 过滤，避免把整段清空）
    declared = set(raw_ref_ids)
    validate_against_refs = bool(raw_ref_ids)

    # 段内重写：chunk 行按 id 过滤，代码围栏与说明行保留
    chunk_lines: list[str] = []
    for line in secs[SEC_CHUNKS]:
        rid = _ref_id_of_chunk_line(line)
        if rid is None:
            chunk_lines.append(line)
            continue
        stats.chunks_before += 1
        if rid in keep_ids and (not validate_against_refs or rid in declared):
            chunk_lines.append(line)
            stats.chunks_after += 1

    out: list[str] = []
    out.extend(secs.get("__head__", []))
    if drop_kg:
        stats.kg_dropped = bool(secs.get(SEC_ENTITY) or secs.get(SEC_RELATION))
    else:
        out.extend(secs.get(SEC_ENTITY, []))
        out.extend(secs.get(SEC_RELATION, []))
    out.extend(chunk_lines)
    out.extend(kept_ref_lines)

    return "\n".join(out), stats


def filter_references(refs: list[dict], keep_files: set[str]) -> tuple[list[dict], dict[str, str]]:
    """按 file_path 过滤引用列表，返回 (保留的引用, reference_id → file_path)。

    `keep_files` 是允许保留的**文件名**（如 `101-在我们的时代里.md`）集合；
    传空集合表示不过滤（全部保留）。
    """
    id_to_file: dict[str, str] = {}
    for r in refs:
        rid = r.get("reference_id")
        fp = r.get("file_path") or ""
        if rid is not None:
            id_to_file[str(rid)] = fp

    if not keep_files:
        return list(refs), id_to_file

    kept = [r for r in refs if _basename(r.get("file_path") or "") in keep_files]
    return kept, id_to_file


def _basename(p: str) -> str:
    return p.replace("\\", "/").split("/")[-1].strip()
