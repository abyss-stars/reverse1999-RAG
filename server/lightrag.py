"""LightRAG 后端的异步客户端（只用到三个端点）。"""

from __future__ import annotations

import httpx

from . import config


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if config.LIGHTRAG_API_KEY:
        h["X-API-Key"] = config.LIGHTRAG_API_KEY
    return h


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=config.LIGHTRAG_BASE, headers=_headers(), timeout=300.0)


async def health() -> dict:
    async with client() as c:
        r = await c.get("/health")
        r.raise_for_status()
        return r.json()


async def fetch_context(
    query: str,
    *,
    mode: str,
    top_k: int,
    chunk_top_k: int,
    max_entity_tokens: int,
    max_relation_tokens: int,
    max_total_tokens: int,
    enable_rerank: bool,
) -> dict:
    """只取检索上下文（`only_need_context`），不做生成 —— 生成由本服务负责。

    返回 `{context, references, response_time}`。
    """
    body = {
        "query": query,
        "mode": mode,
        "top_k": top_k,
        "chunk_top_k": chunk_top_k,
        "max_entity_tokens": max_entity_tokens,
        "max_relation_tokens": max_relation_tokens,
        "max_total_tokens": max_total_tokens,
        "enable_rerank": enable_rerank,
        "only_need_context": True,
        "include_references": True,
        "include_chunk_content": True,
    }
    async with client() as c:
        r = await c.post("/query", json=body)
        r.raise_for_status()
        data = r.json()
    return {
        "context": data.get("response") or "",
        "references": data.get("references") or [],
        "response_time": data.get("response_time"),
    }


async def entity_count() -> int | None:
    """实体总数：`/graph/label/list` 返回全部实体名，取长度即可（比连 DB 省事）。"""
    try:
        async with client() as c:
            r = await c.get("/graph/label/list")
            r.raise_for_status()
            labels = r.json()
        return len(labels) if isinstance(labels, list) else None
    except Exception:
        return None


async def status_counts() -> dict | None:
    try:
        async with client() as c:
            r = await c.get("/documents/status_counts")
            r.raise_for_status()
            return r.json().get("status_counts")
    except Exception:
        return None
