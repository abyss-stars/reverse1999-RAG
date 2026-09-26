"""薄服务层（L3b）—— FastAPI 应用。

> **为什么现在能用 FastAPI 了**：本机**全局** Python 里 fastapi 0.115.6 与已装的
> starlette 1.0.0 不兼容（`Router.__init__() got an unexpected keyword argument
> 'on_startup'`），而全局环境另有 9 处 pip 依赖冲突（gradio 要 starlette<1.0、
> sse-starlette 要 >=0.49.1 …… 两边区间不相交），**去动它只会连累别的项目**。
> 所以本服务自带 venv（`server/.venv`，见 requirements.txt），
> 在里面钉死一对实测兼容的版本：**fastapi 0.141.1 + starlette 1.7.0**。
> 这样既拿到 pydantic 的请求体校验，又完全不碰全局环境。
>
> 换取的东西很具体：以前 `{"top_k": "abc"}` 会被 `_opt_int` **静默吞掉**、
> 退回预设默认值，请求看着成功、参数却没生效；现在 pydantic 直接回 422。

职责（L3b）：
  1. **版本/章节过滤**：LightRAG 的 `/query` 把检索与生成绑在一起，中间插不进过滤，
     所以这里拆成「取上下文 → 裁剪 → 自己生成」三段（filtering.py / generation.py）。
  2. **预设下发**：从 `pipeline/lib/query_planner.py` 导入，与 pipeline 同源。
  3. **章节表 / 索引统计**：前端不必再拷一份 chapter_index.json。
  4. **生产同源托管**：有 `web/dist` 就一并静态服务 → 前端与 API 同源、无 CORS。

设计取舍：**不设过滤时直接透传 LightRAG 的流**（保住已验证的生成质量），
**设了过滤才走「裁剪 + 自己生成」**。两条路都在同一端点下，前端不必知道区别。

> ⚠️ 本文件只负责 **Web 层**。`config / chapters / presets / lightrag / filtering /
> generation` 是框架无关的纯逻辑，重写多少次都不要动它们。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import chapters as ch
from . import config, generation, lightrag, presets
from .filtering import filter_references, prune_context

log = logging.getLogger("uvicorn.error")

# LightRAG 的检索模式全集（写全是为了让"打错的 mode"在入口就被拦下，
# 而不是转给 LightRAG 之后才报一个难懂的错）。
Mode = Literal["naive", "local", "global", "hybrid", "mix", "bypass"]

# 参数上界取得很宽：目的是拦住"明显写错"的值，不是替用户定策略。
# 参考：sweep 档的 max_total_tokens 已经开到 140000。
TopK = Annotated[int, Field(ge=1, le=5000)]
TokenBudget = Annotated[int, Field(ge=0, le=200_000)]
TotalBudget = Annotated[int, Field(ge=0, le=1_000_000)]


# ────────────────────────────── 请求体 ──────────────────────────────


class FilterPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    categories: list[str] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    chapters: list[str] = Field(default_factory=list)
    min_order: int | None = None
    max_order: int | None = None

    def to_spec(self) -> ch.FilterSpec:
        return ch.FilterSpec(
            categories=self.categories,
            versions=self.versions,
            sources=self.sources,
            chapters=self.chapters,
            min_order=self.min_order,
            max_order=self.max_order,
        )


class QueryPayload(BaseModel):
    """`filter` 缺省即 None = 不过滤 = 走透传。"""

    model_config = ConfigDict(extra="ignore")

    query: str
    preset: str = "pinpoint"
    mode: Mode | None = None
    top_k: TopK | None = None
    chunk_top_k: TopK | None = None
    max_entity_tokens: TokenBudget | None = None
    max_relation_tokens: TokenBudget | None = None
    max_total_tokens: TotalBudget | None = None
    enable_rerank: bool | None = None
    filter: FilterPayload | None = None
    keep_kg: bool = config.KEEP_KG_DEFAULT
    include_progress: bool = True

    @field_validator("query")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("query 不能为空")
        return v

    def retrieval_params(self) -> dict:
        """预设打底，显式字段覆盖。"""
        base = presets.params_of(self.preset)
        for k in (
            "mode",
            "top_k",
            "chunk_top_k",
            "max_entity_tokens",
            "max_relation_tokens",
            "max_total_tokens",
            "enable_rerank",
        ):
            v = getattr(self, k)
            if v is not None:
                base[k] = v
        base.setdefault("mode", "naive")
        base.setdefault("top_k", 40)
        base.setdefault("chunk_top_k", 40)
        base.setdefault("max_entity_tokens", 2000)
        base.setdefault("max_relation_tokens", 2000)
        base.setdefault("max_total_tokens", 32000)
        base.setdefault("enable_rerank", True)
        return base


def _ndjson(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _spec_of(payload: QueryPayload) -> ch.FilterSpec:
    return payload.filter.to_spec() if payload.filter else ch.FilterSpec()


# ────────────────────────────── 元信息端点 ──────────────────────────────


async def h_health() -> dict:
    try:
        lr = await lightrag.health()
        lr_ok = True
    except Exception as e:
        lr, lr_ok = {"error": str(e)[:200]}, False
    return {
        "status": "ok",
        "lightrag_ok": lr_ok,
        "lightrag": lr,
        "llm_model": config.LLM_MODEL,
        "llm_configured": bool(config.LLM_API_KEY),
        "capabilities": {
            "chapter_filter": True,
            # KG 段没有来源字段，无法按章节过滤 —— 启用过滤时默认整段丢弃
            "kg_filterable": False,
            "keep_kg_default": config.KEEP_KG_DEFAULT,
        },
    }


async def h_presets() -> list[dict]:
    return presets.for_ui()


async def h_chapters() -> dict:
    idx = ch.load_index()
    return {
        "total": idx.get("total", len(ch.chapters())),
        "counts": idx.get("counts", {}),
        "chapters": ch.chapters(),
    }


async def h_stats() -> dict:
    """索引规模：能实时算的实时算，算不出来的如实标 null（前端回退常量）。"""
    entities = await lightrag.entity_count()
    counts = await lightrag.status_counts()
    return {
        "chapters": len(ch.chapters()),
        "documents": (counts or {}).get("processed"),
        "entities": entities,
        "chunks": ch.chunk_total_from_manifest(),
        "relations": None,  # 没有便宜的实时来源（见 server/README.md）
        "sources": {
            "chapters": "state/chapter_index.json",
            "documents": "lightrag /documents/status_counts",
            "entities": "lightrag /graph/label/list",
            "chunks": "state/index_manifest.json 汇总",
        },
    }


# ────────────────────────────── 查询 ──────────────────────────────


async def _passthrough(payload: QueryPayload) -> AsyncIterator[str]:
    """不过滤：把请求原样转给 LightRAG 的流式端点，逐行中继。"""
    p = payload.retrieval_params()
    body = {
        "query": payload.query,
        "mode": p["mode"],
        "top_k": p["top_k"],
        "chunk_top_k": p["chunk_top_k"],
        "max_entity_tokens": p["max_entity_tokens"],
        "max_relation_tokens": p["max_relation_tokens"],
        "max_total_tokens": p["max_total_tokens"],
        "enable_rerank": p["enable_rerank"],
        "include_references": True,
        "include_chunk_content": True,
        "include_progress": payload.include_progress,
        "stream": True,
    }
    yield _ndjson({"filter": {"active": False, "note": "未设过滤：直接使用 LightRAG 的检索与生成"}})
    try:
        async with lightrag.client() as c:
            async with c.stream("POST", "/query/stream", json=body, timeout=600.0) as r:
                if r.status_code >= 400:
                    text = (await r.aread()).decode("utf-8", "replace")[:300]
                    yield _ndjson({"error": f"LightRAG {r.status_code}: {text}"})
                    return
                async for line in r.aiter_lines():
                    if line.strip():
                        yield line + "\n"
    except Exception as e:
        yield _ndjson({"error": f"无法连接 LightRAG：{str(e)[:200]}"})


async def _filtered(payload: QueryPayload, spec: ch.FilterSpec) -> AsyncIterator[str]:
    """设了过滤：取上下文 → 裁剪 → 自己生成。"""
    t0 = time.perf_counter()

    # ⚠️ 必须先发一行，再做检索。
    # 否则客户端要干等 LightRAG 检索完（实测 2s+）才看到任何东西 ——
    # 而"点下去立刻有反馈"正是这条链路最容易被忽视的体验点。
    yield _ndjson({"progress": "filtering"})

    allowed = ch.allowed_files(spec)
    matched = ch.matched_chapters(spec)

    if not allowed:
        yield _ndjson(
            {
                "filter": {
                    "active": True,
                    "spec": spec.describe(),
                    "matched_chapters": 0,
                    "error": "过滤条件没有匹配到任何章节，请放宽范围。",
                }
            }
        )
        yield _ndjson({"references": []})
        yield _ndjson({"error": "过滤后没有任何章节，未执行检索。"})
        return

    try:
        ctx = await lightrag.fetch_context(payload.query, **payload.retrieval_params())
    except Exception as e:
        yield _ndjson({"filter": {"active": True, "spec": spec.describe(), "matched_chapters": len(matched)}})
        yield _ndjson({"error": f"检索失败：{str(e)[:300]}"})
        return

    kept_refs, _ = filter_references(ctx["references"], allowed)
    keep_ids = {str(r.get("reference_id")) for r in kept_refs if r.get("reference_id") is not None}
    pruned, stats = prune_context(ctx["context"], keep_ids, drop_kg=not payload.keep_kg)

    info = {
        "active": True,
        "spec": spec.describe(),
        "matched_chapters": len(matched),
        "chapters": [f"{c['chapter_no']} {c['title']}" for c in matched][:40],
        "prune": stats.as_dict(),
        "retrieval_seconds": round(time.perf_counter() - t0, 2),
    }

    if stats.chunks_after == 0:
        yield _ndjson({"filter": info})
        yield _ndjson({"references": []})
        yield _ndjson({"error": "过滤后没有剩下任何可引用的片段——检索命中的章节都落在范围之外。"})
        return

    yield _ndjson({"filter": info})
    yield _ndjson({"references": kept_refs})
    yield _ndjson({"progress": "generating"})

    try:
        async for delta in generation.stream_completion(payload.query, pruned, filter_note=spec.describe()):
            yield _ndjson({"response": delta})
    except Exception as e:
        yield _ndjson({"error": f"生成失败：{str(e)[:300]}"})
        return

    yield _ndjson({"response_time": round(time.perf_counter() - t0, 2)})


async def h_query_stream(request: Request, payload: QueryPayload) -> Response:
    # 进入 handler 时 body 早已被框架解析完，所以"解析耗时"必须靠 middleware
    # 在请求刚到时钉下的时刻来算（见下方 _stamp_entry），否则这条打点会恒为 0。
    _t_entry = getattr(request.state, "t_entry", None) or time.perf_counter()
    _t_parsed = time.perf_counter()

    spec = _spec_of(payload)
    base = _filtered(payload, spec) if spec.is_active() else _passthrough(payload)

    # 打点：确认"首行到底什么时候产生的"。首字节延迟的排查见 server/README.md。
    async def timed() -> AsyncIterator[str]:
        first = True
        async for chunk in base:
            if first:
                first = False
                log.info(
                    "[timing] entry→parsed %.3fs, entry→first_chunk %.3fs",
                    _t_parsed - _t_entry,
                    time.perf_counter() - _t_entry,
                )
            yield chunk

    return StreamingResponse(
        timed(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def h_query(payload: QueryPayload) -> Response:
    """非流式版本：把流拼起来返回，方便脚本与回归用。"""
    spec = _spec_of(payload)
    refs: list[dict] = []
    text: list[str] = []
    filter_info: dict | None = None
    error: str | None = None
    rt: float | None = None

    async for line in (_filtered(payload, spec) if spec.is_active() else _passthrough(payload)):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "filter" in obj:
            filter_info = obj["filter"]
        elif "references" in obj:
            refs = obj["references"]
        elif "response" in obj:
            text.append(obj["response"])
        elif "response_time" in obj:
            rt = obj["response_time"]
        elif "error" in obj:
            error = obj["error"]

    if error:
        # 形状与非错误响应保持一致：客户端不必为错误分支写特例
        return JSONResponse(
            {"error": error, "filter": filter_info, "response": "", "references": refs,
             "response_time": rt, "llm_generated": False},
            status_code=502,
        )
    return JSONResponse(
        {
            "response": "".join(text),
            "references": refs,
            "response_time": rt,
            "filter": filter_info,
            "llm_generated": bool(text),
        }
    )


# ────────────────────────────── 组装 ──────────────────────────────

app = FastAPI(title="1999RAG 薄服务层", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发期前端在 :5173；生产同源时用不到
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _stamp_entry(request: Request, call_next):
    """在请求刚进应用时钉一个时刻，供流式端点计算"解析耗时"。"""
    request.state.t_entry = time.perf_counter()
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def _on_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """把校验失败压成与其它错误一致的 `{"error": ...}` 形状。

    - 非法 JSON → 400（原来是 Starlette 里手写的分支，这里靠 FastAPI 的 json_invalid）
    - 字段不合法 → 422，并指出是哪个字段（不再静默退回预设默认值）
    """
    errors = exc.errors()
    if any(e.get("type") == "json_invalid" for e in errors):
        return JSONResponse({"error": "请求体不是合法 JSON"}, status_code=400)
    first = errors[0] if errors else {}
    loc = ".".join(str(x) for x in first.get("loc", ()) if x != "body")
    return JSONResponse(
        {
            "error": f"参数不合法：{loc or 'body'} —— {first.get('msg', '校验未通过')}",
            "errors": [
                {"loc": ".".join(str(x) for x in e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
                for e in errors
            ],
        },
        status_code=422,
    )


# ⚠️ `response_model=None` 是刻意的：FastAPI 默认会拿「返回类型标注」当**响应模型**，
# 于是会对返回值再做一遍校验+重序列化。本服务的 JSON 形状是已经和前端生成代码
# 对齐过的契约（web/src/api/presets.ts 等），不能让框架在出口处静默改写。
# 实测踩过：h_presets 标了 `-> dict` 却返回 list，直接 500 ResponseValidationError。
# 校验的收益在**入口**（请求体 422），出口保持逐字节原样。
app.add_api_route("/api/health", h_health, methods=["GET"], response_model=None)
app.add_api_route("/api/presets", h_presets, methods=["GET"], response_model=None)
app.add_api_route("/api/chapters", h_chapters, methods=["GET"], response_model=None)
app.add_api_route("/api/stats", h_stats, methods=["GET"], response_model=None)
app.add_api_route("/api/query/stream", h_query_stream, methods=["POST"], response_model=None)
app.add_api_route("/api/query", h_query, methods=["POST"], response_model=None)

# 生产形态：有构建产物就同源托管（放在最后，位置通配不要抢在 /api 前面）
if config.WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(config.WEB_DIST), html=True), name="web")
