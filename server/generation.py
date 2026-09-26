"""生成阶段：拿着**已过滤**的上下文，自己调 LLM。

为什么要自己生成：LightRAG 的 `/query` 把"检索 + 生成"绑在一次调用里，
中间没有插过滤的缝。所以薄服务层拆成两段：

    ① POST /query(only_need_context=true)  → 拿到上下文与引用
    ② 按章节/版本裁剪上下文（filtering.py）
    ③ 本模块调 LLM 生成            → 流式回给前端

代价是生成用的提示词不再由 LightRAG 提供，因此下面这份提示词要自己维护；
它与 LightRAG 的 `rag_response` 意图一致（只用资料、标注 [n]、资料不足就说不足）。
**这是刻意的取舍**，记录在 server/README.md。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from . import config

SYSTEM_PROMPT = """你是《重返未来：1999》剧情档案的检索助手。

规则：
1. **只依据下面提供的「资料」回答**，不要使用资料之外的知识，也不要推测剧情。
2. 资料里的每个片段都标了 [序号]。引用时在相关句子末尾用 [序号] 标注；多个来源就并列写，例如 [2][5]。
3. 如果资料不足以回答，直接说明"资料不足"，并指出还缺什么，不要硬答。
4. 用简体中文回答；人物名、组织名、术语必须与资料里的写法完全一致。
5. 不要复述或罗列资料原文，要给出归纳后的答案；但关键台词可以原样引用。
"""


def build_user_prompt(query: str, context: str, *, filter_note: str | None = None) -> str:
    parts = []
    if filter_note:
        parts.append(f"（本次检索范围已限定：{filter_note}。资料之外的内容一律不要提。）")
    parts.append("资料：\n" + (context.strip() or "（没有检索到任何资料）"))
    parts.append("问题：" + query.strip())
    return "\n\n".join(parts)


async def stream_completion(
    query: str,
    context: str,
    *,
    filter_note: str | None = None,
    temperature: float = 0.3,
) -> AsyncIterator[str]:
    """流式产出答案增量。异常原样抛出，由调用方决定怎么报给前端。"""
    if not config.LLM_API_KEY:
        raise RuntimeError("缺少 LLM_BINDING_API_KEY，无法生成（见 .env）")

    payload = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(query, context, filter_note=filter_note)},
        ],
        "temperature": temperature,
        "stream": True,
    }
    url = f"{config.LLM_BINDING_HOST}/chat/completions"
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=httpx.Timeout(config.LLM_TIMEOUT, connect=20.0)) as c:
        async with c.stream("POST", url, json=payload, headers=headers) as r:
            if r.status_code >= 400:
                body = (await r.aread()).decode("utf-8", "replace")[:400]
                raise RuntimeError(f"LLM {r.status_code}: {body}")
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for choice in obj.get("choices") or []:
                    delta = (choice.get("delta") or {}).get("content")
                    if delta:
                        yield delta
