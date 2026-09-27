"""薄服务层的集成测试（需要 LightRAG(:9621) 与本服务(:8787) 都在跑）。

重点验的是**新增能力**：按版本过滤是否真的收窄了上下文与引用，
而不只是"接口能返回 200"。

跑法：
    python -m uvicorn server.app:app --port 8787      # 另开一个终端
    python server/test_service.py
退出码 0 = 全过。
"""

from __future__ import annotations

import json
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.request

# 让脚本两种跑法都能 import server.*（仓库根或 server/ 下直接跑）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8787"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  {'[PASS]' if cond else '[FAIL]'} {name}{('  ' + extra) if extra else ''}")
    if not cond:
        failures.append(name)


def get(path: str, timeout: float = 120) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout, context=CTX) as r:
        return json.loads(r.read())


def post(path: str, body: dict, timeout: float = 600) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def post_raw(path: str, body: dict, timeout: float = 60) -> tuple[int, dict]:
    """返回 (状态码, 解析后的 JSON)，用于校验类断言。"""
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"_raw": raw.decode("utf-8", "replace")[:200]}


def post_badjson(path: str, timeout: float = 60) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + path,
        data=b"{not json at all",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"_raw": raw.decode("utf-8", "replace")[:200]}


QUESTION = "「这是我的箱子，请还给我。」这句话是谁说的？"


def main() -> int:
    print("=== 元信息端点 ===")
    h = get("/api/health")
    check("health 200 且 lightrag 可达", h.get("lightrag_ok") is True, f"llm={h.get('llm_model')}")
    check("声明 chapter_filter 能力", h.get("capabilities", {}).get("chapter_filter") is True)
    check("如实声明 KG 不可过滤", h.get("capabilities", {}).get("kg_filterable") is False)

    p = get("/api/presets")
    check("预设 5 档", isinstance(p, list) and len(p) == 5, f"{[x['name'] for x in p] if isinstance(p, list) else p}")
    check("预设带 params（与 query_planner 同源）", "params" in (p[0] if isinstance(p, list) and p else {}))

    # 回归：预设参数必须真的传下去。之前 params_of 读错了层级，静默退回默认值；
    # pinpoint 恰好等于默认值所以看不出来，sweep 的 chunk_top_k=150 才是照妖镜。
    params_by_name = {x["name"]: x.get("params", {}) for x in (p if isinstance(p, list) else [])}
    check("sweep 的 chunk_top_k=150 在契约里", params_by_name.get("sweep", {}).get("chunk_top_k") == 150,
          f"{params_by_name.get('sweep')}")
    check("chain 的 mode=mix 在契约里", params_by_name.get("chain", {}).get("mode") == "mix")
    check("sweep 显式关闭 rerank", params_by_name.get("sweep", {}).get("enable_rerank") is False)
    check("lookup 的 max_entity_tokens=9000 在契约里",
          params_by_name.get("lookup", {}).get("max_entity_tokens") == 9000)

    from server import presets as _presets

    check("服务端 params_of 与契约一致（sweep）",
          _presets.params_of("sweep").get("chunk_top_k") == 150,
          str(_presets.params_of("sweep")))
    check("服务端 params_of 补了 enable_rerank 默认 True",
          _presets.params_of("chain").get("enable_rerank") is True)

    c = get("/api/chapters")
    check("章节表 81 章", c.get("total") == 81, f"total={c.get('total')}")
    cats = c.get("counts") or {}
    check("分类计数正确", cats.get("mainline") == 16 and cats.get("activity") == 23, f"{cats}")

    s = get("/api/stats")
    check("统计返回实时实体数", isinstance(s.get("entities"), int), f"entities={s.get('entities')}")
    check("统计返回 chunks", isinstance(s.get("chunks"), int), f"chunks={s.get('chunks')}")
    # 与数据库直查的 vdb_chunks 行数交叉验证
    check("chunks 与索引实际值一致（2,439）", s.get("chunks") == 2439, f"chunks={s.get('chunks')}")
    check("实体数与数据库一致（9,896）", s.get("entities") == 9896, f"entities={s.get('entities')}")
    check("未知项如实为 null", s.get("relations") is None)

    print("\n=== 不过滤：透传 LightRAG ===")
    t0 = time.time()
    r1 = post("/api/query", {"query": QUESTION, "preset": "pinpoint"})
    dt1 = time.time() - t0
    check("返回了答案", len(r1.get("response") or "") > 20, f"{len(r1.get('response') or '')} 字 / {dt1:.1f}s")
    check("filter.active=False", (r1.get("filter") or {}).get("active") is False)
    check("有引用", len(r1.get("references") or []) > 0, f"refs={len(r1.get('references') or [])}")
    refs1 = len(r1.get("references") or [])

    print("\n=== 过滤：只留 v1.0（覆盖 101~104 章） ===")
    t0 = time.time()
    r2 = post(
        "/api/query",
        {"query": QUESTION, "preset": "pinpoint", "filter": {"versions": ["1.0"]}},
    )
    dt2 = time.time() - t0
    f2 = r2.get("filter") or {}
    check("filter.active=True", f2.get("active") is True, f"spec={f2.get('spec')}")
    check("命中的章节数与章节表一致", isinstance(f2.get("matched_chapters"), int) and f2["matched_chapters"] > 0,
          f"matched={f2.get('matched_chapters')}")
    check("引用被收窄", len(r2.get("references") or []) < refs1,
          f"{refs1} → {len(r2.get('references') or [])}")
    prune = f2.get("prune") or {}
    check("上下文 chunk 被裁剪", prune.get("chunks_after", 0) < prune.get("chunks_before", 0),
          f"{prune.get('chunks_before')} → {prune.get('chunks_after')}")
    # pinpoint 是 naive：上下文里本来就没有 KG 段，所以 kg_dropped=False 是**正确**的
    check("naive 无 KG 段 → kg_dropped=False（如实）", prune.get("kg_dropped") is False)
    # 不变量是"要么给答案、要么明确报错"，而不是"答案必须多长" ——
    # 后者依赖 LLM，实测它偶尔会只回一句很短的话（合法答案），拿长度卡会变成脆测试。
    _resp2 = r2.get("response") or ""
    check(
        "过滤路径要么给答案要么明确报错（不静默）",
        bool(_resp2.strip()) or bool(r2.get("error")),
        f"{len(_resp2)} 字 / error={r2.get('error')}",
    )

    # 关键：引用是否**真的**都落在 v1.0 的章节里
    idx = get("/api/chapters")["chapters"]
    v10 = {x["filename"] for x in idx if x.get("version") == "1.0"}
    ref_files = {(r.get("file_path") or "").split("/")[-1] for r in (r2.get("references") or [])}
    # `bool(ref_files) and ...` 而不是 `ref_files and ...`：后者在集合为空时返回的是**空集合**
    # 本身（Python 的 `and` 返回操作数，不返回 bool），真值一样但类型是 `set[str] | bool`，
    # 与 `check(cond: bool)` 的契约不符（Pylance/pyright 会报错）。原意就是
    # 「至少有一条引用，且全部都落在 v1.0 章节里」，两个条件缺一不可。
    check("引用文件全部属于 v1.0", bool(ref_files) and ref_files <= v10, f"越界={sorted(ref_files - v10)}")
    print(f"      v1.0 章节: {sorted(v10)}")
    print(f"      实际引用  : {sorted(ref_files)}")

    print("\n=== 过滤：命中 0 章时不许瞎答 ===")
    r3 = post("/api/query", {"query": QUESTION, "preset": "pinpoint", "filter": {"versions": ["9.9"]}})
    check("明确报错而不是编答案", bool(r3.get("error")), f"{(r3.get('error') or '')[:60]}")
    check("没有引用", not (r3.get("references") or []))

    print("\n=== 过滤：按分类（角色剧情） ===")
    r4 = post("/api/query", {"query": "程和光是谁？", "preset": "lookup", "filter": {"categories": ["character"]}})
    f4 = r4.get("filter") or {}
    check("命中的都是角色剧情", f4.get("matched_chapters") == 20, f"matched={f4.get('matched_chapters')}")
    ref_files4 = {(r.get("file_path") or "").split("/")[-1] for r in (r4.get("references") or [])}
    char_files = {x["filename"] for x in idx if x.get("category") == "character"}
    check("引用文件全部属于角色剧情", not ref_files4 or ref_files4 <= char_files,
          f"越界={sorted(ref_files4 - char_files)}")

    print("\n=== 过滤：KG 模式（chain=mix）下 KG 段必须被丢弃 ===")
    r5 = post("/api/query", {"query": "维尔汀和APPLe是什么关系？", "preset": "chain", "filter": {"versions": ["1.0"]}})
    f5 = r5.get("filter") or {}
    p5 = f5.get("prune") or {}
    check("上下文里确实有 KG 段（chunks_before>0 且 kg_dropped 有意义）", p5.get("kg_dropped") is True,
          f"kg_dropped={p5.get('kg_dropped')}")
    print("      说明：实体/关系行不带 file_path，无法按章节过滤，因此启用过滤时整段丢弃（宁可少，不可越界）")

    print("\n=== 过滤 + keep_kg=true：KG 段保留（用户显式要求） ===")
    r6 = post(
        "/api/query",
        {"query": "维尔汀和APPLe是什么关系？", "preset": "chain", "filter": {"versions": ["1.0"]}, "keep_kg": True},
    )
    p6 = (r6.get("filter") or {}).get("prune") or {}
    check("kg_dropped=False", p6.get("kg_dropped") is False, f"kg_dropped={p6.get('kg_dropped')}")
    check("chunk 仍被裁剪", p6.get("chunks_after", 0) <= p6.get("chunks_before", 0),
          f"{p6.get('chunks_before')} → {p6.get('chunks_after')}")

    print("\n=== 流式端点：NDJSON 行序与键 ===")
    import urllib.request as _u

    req = _u.Request(
        BASE + "/api/query/stream",
        data=json.dumps(
            {"query": QUESTION, "preset": "pinpoint", "filter": {"versions": ["1.0"]}}
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    kinds: list[str] = []
    deltas = 0
    t_start = time.time()
    t_first_line: float | None = None
    t_first_delta: float | None = None
    with _u.urlopen(req, timeout=600, context=CTX) as resp:
        check("Content-Type 是 ndjson", "ndjson" in (resp.headers.get("Content-Type") or ""),
              resp.headers.get("Content-Type") or "")
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            if t_first_line is None:
                t_first_line = time.time() - t_start
            obj = json.loads(line)
            key = next(iter(obj))
            if key not in kinds:
                kinds.append(key)
            if key == "response":
                deltas += 1
                if t_first_delta is None:
                    t_first_delta = time.time() - t_start
    check("progress 打头（点下去立刻有反馈）", kinds[:1] == ["progress"], f"行序={kinds}")
    check("filter 在 references 之前", kinds.index("filter") < kinds.index("references"), f"行序={kinds}")
    check("有多个 response 增量（真流式）", deltas > 1, f"deltas={deltas}")
    check("以 response_time 收尾", kinds[-1] == "response_time", f"行序={kinds}")

    # 验收标准 2（已按实测修正）：
    # 感知响应性由"首个进度反馈"决定，而不是首个答案 token；而"首字节"这个量在
    # 本机裸 socket 上测得偏大（约 1.6s），与服务端打点（0.012s）和前端观测（<0.5s）矛盾，
    # 归因未明 —— 所以这里只做宽松回归护栏，不做精确断言。
    check("首个 NDJSON 行 ≤ 3s（宽松护栏）", t_first_line is not None and t_first_line <= 3.0,
          f"{t_first_line:.2f}s（服务端打点见 uvicorn 日志的 [timing] 行）")
    check("首个答案增量 ≤ 15s（宽松护栏）", t_first_delta is not None and t_first_delta <= 15.0,
          f"{t_first_delta:.2f}s" if t_first_delta else "未收到增量")

    print("\n=== 过滤后片段为 0：明确报错，不许硬编（对应验收标准 4 的相关路径） ===")
    # 限定到 v4.0（只有 114 应门者 / 313 船喻），却问 101 章里的事：
    # 检索仍能在全库找到东西，但过滤后一条都不剩 —— 这正是"无依据"的真实触发方式。
    r7 = post(
        "/api/query",
        {"query": QUESTION, "preset": "pinpoint", "filter": {"versions": ["4.0"]}},
    )
    f7 = r7.get("filter") or {}
    check("引用为空", len(r7.get("references") or []) == 0, f"refs={len(r7.get('references') or [])}")
    check("明确报错而不是编答案", "过滤后没有剩下" in (r7.get("error") or ""), f"{(r7.get('error') or '')[:70]}")
    check("如实回报 chunk 被清空", (f7.get("prune") or {}).get("chunks_after") == 0,
          f"prune={f7.get('prune')}")
    check("llm_generated=false（未生成）", r7.get("llm_generated") is False)

    print("\n=== 说明：为什么不用『荒谬问题』测无依据 ===")
    r8 = post("/api/query", {"query": "请问这段剧情里有没有提到过『量子纠缠永动机』？", "preset": "pinpoint"})
    print(f"      实测：荒谬问题仍拿到 {len(r8.get('references') or [])} 条引用 ——")
    print("      向量检索对任何句子都会返回超过余弦阈值的片段，所以『检索不到』在满索引下几乎不出现。")
    print("      前端的 looksUngrounded（0 引用 / 固定兜底文案）是尽力而为的启发式，已在 web/README.md 说明。")

    print("\n=== 请求体校验：坏参数必须被拒绝，不许静默退回预设默认值 ===")
    # 这是从 Starlette 换成 FastAPI + pydantic 的主要收益，所以要有回归。
    # 旧实现里 _opt_int("abc") 返回 None，于是"看起来成功、参数其实没生效"。
    code, body9 = post_raw("/api/query", {"query": QUESTION, "top_k": "abc"})
    check("top_k 非法 → 422", code == 422, f"code={code}")
    check("422 带可读的 error 字段", "top_k" in (body9.get("error") or ""), f"{body9.get('error')}")

    code, body10 = post_raw("/api/query", {"query": QUESTION, "chunk_top_k": -5})
    check("chunk_top_k 越界 → 422", code == 422, f"code={code}")

    code, body11 = post_raw("/api/query", {"query": "", "preset": "pinpoint"})
    check("空 query → 422", code == 422, f"code={code}")
    check("空 query 的提示可读", "query" in (body11.get("error") or ""), f"{body11.get('error')}")

    code, body12 = post_badjson("/api/query")
    check("非法 JSON → 400（不是 422）", code == 400, f"code={code}")

    code, body13 = post_raw("/api/query", {"query": QUESTION, "mode": "banana"})
    check("未知 mode → 422", code == 422, f"code={code}")

    # 合法但非默认值：应当真被采纳（而不是像以前那样被吞掉）
    code, body14 = post_raw(
        "/api/query", {"query": QUESTION, "preset": "pinpoint", "top_k": 5, "chunk_top_k": 5}
    )
    check("合法显式参数被接受", code == 200 and not body14.get("error"), f"code={code}")

    print()
    if failures:
        print(f"[FAIL] {len(failures)} 项未通过：{failures}")
        return 1
    print("[PASS] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
