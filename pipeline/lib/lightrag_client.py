#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
lightrag_client.py — LightRAG Server REST API 的最小客户端 (纯标准库)

已核实的端点 (lightrag/api/routers/document_routes.py):
    POST   /documents/scan                      触发扫描 INPUT_DIR, 返回 track_id
    GET    /documents/scan/status/{track_id}    扫描作业进度
    GET    /documents/pipeline_status           实时管线日志与 busy 状态
    GET    /documents/status_counts             各状态文档数
    POST   /documents/paginated                 分页文档列表(含 chunks_count)
    POST   /documents/delete_document           删除文档 + 清理 chunk 与图谱贡献
    GET    /documents/supported_file_types      实际生效的后缀→引擎映射
    GET    /documents/track_status/{track_id}   单次上传/文本插入的进度
    POST   /query                               检索/问答

鉴权: 若服务端设了 LIGHTRAG_API_KEY, 用 X-API-Key 头。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# Windows 控制台默认 GBK, 打印中文会变成乱码。库被 import 时顺手修好,
# 这样所有调用方的 inline 脚本都不必各自 reconfigure。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class LightRAGError(RuntimeError):
    pass


class LightRAGClient:
    def __init__(
        self,
        base_url: str = "http://localhost:9621",
        api_key: str = "",
        timeout: int = 180,
    ) -> None:
        self.base = base_url.rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    # ------------------------------------------------------------ 底层
    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{self.base}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:600]
            raise LightRAGError(f"{method} {path} -> HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise LightRAGError(
                f"{method} {path} -> 连接失败: {e.reason}\n"
                f"  (服务是否已启动? docker compose ps)"
            ) from None

        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self._request("POST", path, body if body is not None else {})

    # ------------------------------------------------------------ 健康与状态
    def health(self) -> dict:
        return self.get("/health") or {}

    def pipeline_status(self) -> dict:
        return self.get("/documents/pipeline_status") or {}

    def status_counts(self) -> dict:
        return self.get("/documents/status_counts") or {}

    def supported_file_types(self) -> Any:
        return self.get("/documents/supported_file_types")

    # ------------------------------------------------------------ 文档操作
    def scan(self) -> dict:
        """触发扫描 INPUT_DIR。返回 {status, track_id}。"""
        return self.post("/documents/scan", {})

    def scan_status(self, track_id: str) -> dict:
        return self.get(f"/documents/scan/status/{track_id}") or {}

    def track_status(self, track_id: str) -> dict:
        return self.get(f"/documents/track_status/{track_id}") or {}

    def documents_paginated(
        self,
        page: int = 1,
        page_size: int = 200,
        status_filter: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {"page": page, "page_size": page_size}
        if status_filter:
            body["status_filter"] = status_filter
        return self.post("/documents/paginated", body) or {}

    def delete_document(
        self,
        doc_ids: list[str],
        delete_file: bool = False,
        delete_llm_cache: bool = False,
    ) -> dict:
        """删除文档及其 chunk/向量/图谱贡献。

        ⚠️ 端点是 DELETE 方法且带请求体（不是 POST）—— 见
        document_routes.py:6497。delete_llm_cache 默认 False：
        抽取缓存是我们花过钱的成果，除非必要不要删。
        """
        return self._request(
            "DELETE",
            "/documents/delete_document",
            {
                "doc_ids": doc_ids,
                "delete_file": delete_file,
                "delete_llm_cache": delete_llm_cache,
            },
        ) or {}

    def query(
        self,
        question: str,
        mode: str = "mix",
        only_need_context: bool = False,
        include_references: bool = True,
        include_chunk_content: bool = False,
        top_k: int | None = None,
        chunk_top_k: int | None = None,
        enable_rerank: bool | None = None,
        user_prompt: str | None = None,
        timeout: int | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "query": question,
            "mode": mode,
            "only_need_context": only_need_context,
            "include_references": include_references,
            "include_chunk_content": include_chunk_content,
        }
        if top_k is not None:
            body["top_k"] = top_k
        if chunk_top_k is not None:
            body["chunk_top_k"] = chunk_top_k
        if enable_rerank is not None:
            body["enable_rerank"] = enable_rerank
        if user_prompt:
            body["user_prompt"] = user_prompt
        old = self.timeout
        if timeout:
            self.timeout = timeout
        try:
            return self.post("/query", body) or {}
        finally:
            self.timeout = old

    # ------------------------------------------------------------ 轮询辅助
    @staticmethod
    def _is_active(st: dict) -> bool:
        """管线是否仍在干活。

        ⚠️ 只看 busy 是不够的：scan 的"分类阶段"是在 scanning_exclusive 下跑的，
        此时 busy 仍为 False。漏判会导致 --watch 秒退，误以为已经跑完。
        """
        return bool(
            st.get("busy")
            or st.get("scanning")
            or st.get("scanning_exclusive")
            or st.get("destructive_busy")
            or (st.get("pending_enqueues") or 0) > 0
        )

    def wait_for_idle(self, poll: float = 5.0, timeout: float = 7200,
                      on_tick=None) -> dict:
        """等到管线完全空闲(含扫描分类阶段)。返回最后一次 pipeline_status。"""
        t0 = time.time()
        while True:
            st = self.pipeline_status()
            if on_tick:
                on_tick(st, time.time() - t0)
            if not self._is_active(st):
                return st
            if time.time() - t0 > timeout:
                raise LightRAGError(f"等待管线空闲超时 ({timeout}s)")
            time.sleep(poll)

    def wait_for_scan(self, track_id: str, poll: float = 3.0,
                      timeout: float = 600) -> dict:
        t0 = time.time()
        while True:
            st = self.scan_status(track_id)
            s = (st.get("status") or "").lower()
            if s in ("completed", "failed", "cancelled", "skipped"):
                return st
            if time.time() - t0 > timeout:
                return st
            time.sleep(poll)
