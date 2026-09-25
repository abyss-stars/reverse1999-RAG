"""在容器内验证: extra_body 是否能经 LightRAG 的 LLM 函数透传到 DeepSeek。

从 /app/.env 读取真实配置, 避免把 key 写进命令行。
"""
import asyncio
import time

from dotenv import dotenv_values
from lightrag.llm.openai import openai_complete_if_cache

ENV = dotenv_values("/app/.env")
KEY = ENV["LLM_BINDING_API_KEY"]
BASE = ENV["LLM_BINDING_HOST"]
MODEL = ENV["LLM_MODEL"]
PROMPT = "用一句话解释什么是神秘学家"


async def run(label: str, **extra):
    t0 = time.time()
    out = await openai_complete_if_cache(
        model=MODEL,
        prompt=PROMPT,
        api_key=KEY,
        base_url=BASE,
        max_tokens=800,
        **extra,
    )
    dt = time.time() - t0
    text = out if isinstance(out, str) else str(out)
    print(f"  {label:<30} 耗时={dt:6.2f}s  返回长度={len(text):4}")
    print(f"      首 60 字: {text[:60]!r}")
    return dt


async def main():
    print(f"经 openai_complete_if_cache 调用 {MODEL} @ {BASE}")
    print(f"prompt: {PROMPT}   max_tokens=800\n")
    t_base = await run("A 基准(不传 extra_body)")
    t_off = await run("B extra_body thinking=disabled",
                      extra_body={"thinking": {"type": "disabled"}})
    t_low = await run("C thinking=enabled + effort=low",
                      extra_body={"thinking": {"type": "enabled"},
                                  "reasoning_effort": "low"})
    print()
    print(f"  B/A = {t_off / t_base:.2f}x   C/A = {t_low / t_base:.2f}x")
    print()
    if t_off < t_base * 0.75:
        print("  结论: extra_body 透传【成功】—— thinking=disabled 明显加速")
    else:
        print("  结论: extra_body 可能【未生效】—— 耗时没有明显差异")


asyncio.run(main())
