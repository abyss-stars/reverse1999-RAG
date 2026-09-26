# server/ — 薄服务层（L3b）

给前端提供的唯一入口。承载四件事：**版本/章节过滤**、**预设下发**、**章节表/统计**、**生产同源托管**。

依据：`website.md` A1 = L3b（`next.md` §3.3 指出"版本过滤只能在服务层做"）。

---

## 为什么需要它

LightRAG 的 `/query` **把"检索"和"生成"绑在一次调用里**，中间没有插过滤的缝：

```
POST /query  →  [关键词抽取] → [向量/图检索] → [拼上下文] → [调 LLM 生成] → 返回
                                  ↑
                        版本过滤本该插在这里，但插不进去
```

所以本服务把这条链拆成三段：

```
① POST /query (only_need_context=true)   → 只拿上下文 + references
② filtering.prune_context(...)           → 按章节/版本裁剪
③ generation.stream_completion(...)      → 自己调 LLM 生成，流式回传
```

代价是**生成的提示词由本服务维护**（不再由 LightRAG 提供）。这是刻意的取舍，写在 `generation.py` 顶部。

---

## 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 自身状态 + LightRAG 可达性 + **能力声明**（含"KG 不可过滤"） |
| GET | `/api/presets` | 五档预设，**从 `pipeline/lib/query_planner.py` 导入**，不复制 |
| GET | `/api/chapters` | 81 章章节表（前端不必再拷 `chapter_index.json`） |
| GET | `/api/stats` | 索引规模。能实时算的实时算，算不出的如实 `null` |
| POST | `/api/query` | 非流式（脚本/回归用） |
| POST | `/api/query/stream` | **流式 NDJSON**，前端用它 |

请求体（`/api/query*`）：

```jsonc
{
  "query": "…",
  "preset": "pinpoint",             // 五档之一
  "mode": "naive",                  // 可选：覆盖预设
  "top_k": 40, "chunk_top_k": 40,   // 可选：覆盖预设
  "max_entity_tokens": 2000, "max_relation_tokens": 2000, "max_total_tokens": 32000,
  "enable_rerank": true,
  "filter": {                       // 可选：不传 = 不过滤
    "versions": ["1.0"],
    "categories": ["mainline"],
    "sources": ["metadata"],
    "chapters": ["101"],
    "min_order": 1, "max_order": 16
  },
  "keep_kg": false                  // 见下
}
```

流式响应是 NDJSON，**只按键分派，不依赖行序**（但实际行序是固定的）：

```
{"progress": "filtering"}          ← 立刻发，保证"点下去就有反馈"
{"filter": {…裁剪统计…}}
{"references": […只保留范围内的…]}
{"progress": "generating"}
{"response": "增量"}  × N
{"response_time": 5.2}
```

---

## 过滤：能做与不能做（重要）

| 部分 | 能否按章节过滤 | 原因 |
|---|---|---|
| **Document Chunks + Reference List** | ✅ 能 | chunk 带 `reference_id`，而 `references[]` 给出 `reference_id → file_path`，可精确裁剪 |
| **Knowledge Graph（实体/关系）** | ❌ **不能** | 上下文里的实体/关系行**只有 `entity`/`type`/`description`，没有任何来源字段**（实测自 `scripts/dump_context_format.py`） |

因此**启用过滤时默认整段丢弃 KG**（`keep_kg=false`），而不是"留着让模型看到范围外的事实"。
宁可少，不可越界 —— 这是安全方向的选择。代价：`chain`（mix）这类依赖图谱的档位在过滤下会退化。

想保留图谱就传 `keep_kg: true`，但**你要接受图谱部分可能来自范围外的章节**（引用仍只会有范围内的）。

> **升级路径（未做）**：实体→章节的反查其实存在——DB 里有
> `lightrag_entity_chunks(entity_name, chunk_id)` 与 `lightrag_doc_chunks`，
> 顺着 chunk→doc→章节就能算出每个实体的章节集合，从而真正按章节过滤 KG。
> 需要给服务层加一个 PG 驱动（当前刻意零 DB 依赖）。

---

## 设计取舍：两条生成路径

| 情况 | 走哪条 | 为什么 |
|---|---|---|
| **不设过滤** | **原样透传** LightRAG 的 `/query/stream` | 保住已被 `smoke_test.py` 验证过的生成质量，零回归风险 |
| **设了过滤** | 本服务的「裁剪 + 自己生成」 | 没有别的办法在生成前收窄上下文 |

两条路在同一端点下，前端不必知道区别（响应里 `filter.active` 会说明走了哪条）。
**副作用：答案风格在两种情况下可能不同** —— 这是已知的、明示的代价。

---

## 跑起来

本服务有**自己的 venv**（`server/.venv`），**不要**用全局 Python 起 —— 原因见下。

```powershell
# 仓库根目录

# ① 建环境（只需一次）
python -m venv server\.venv
server\.venv\Scripts\python.exe -m pip install -r server\requirements.txt

# ② 起服务
server\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8787
```

**依赖**：`fastapi` + `starlette` + `pydantic` + `uvicorn` + `httpx`，
精确版本钉在 `server/requirements.txt`（当前实测组合：**fastapi 0.141.1 + starlette 1.7.0 + pydantic 2.13.5**）。

> **为什么要自带 venv，而不是装进全局 Python。**
> 本机全局环境已经有 **9 处 `pip check` 冲突**，其中 fastapi 与 starlette 的可用区间
> 甚至**不相交**：`gradio` 要 `starlette<1.0`、`sse-starlette` 要 `starlette>=0.49.1`、
> 而旧的 `fastapi 0.115.6` 要 `starlette<0.42`。也就是说无论怎么调，全局环境都不可能
> 同时满足三方；装 FastAPI 进全局一定会连累别的项目。
> 自带 venv 让本服务的依赖与全局**完全隔离**，两边都不用妥协。

> **框架选型：FastAPI（先前是 Starlette）。**
> 最初用 Starlette 是因为全局环境里 `fastapi 0.115.6` 与 `starlette 1.0.0` 不兼容
> （`Router.__init__() got an unexpected keyword argument 'on_startup'`），
> 而当时不想碰全局环境。有了 venv 之后这个约束消失，就换成了 FastAPI ——
> 换来的具体收益是**请求体校验**：
>
> | 请求 | 旧（Starlette + 手写 `_opt_int`） | 新（FastAPI + pydantic） |
> |---|---|---|
> | `{"query": "...", "top_k": "abc"}` | **静默吞掉**，退回预设默认值，返回 200 | **422**，并指出是 `top_k` |
> | `{"query": "...", "chunk_top_k": -5}` | 原样传给 LightRAG | **422** |
> | `{"query": ""}` | 422 | 422（同上，提示更可读） |
> | 请求体不是合法 JSON | 400 | 400（`json_invalid` 单独分支） |
> | `{"mode": "banana"}` | 转给 LightRAG 后才报错 | **422**（`Literal` 拦在入口） |
> | `{"enable_rerank": "false"}` | `bool("false")` → **True**（反了） | 正确解析为 `False` |
>
> "静默退回默认值"是最糟的一类 bug：请求成功、参数没生效、没有任何迹象。
> `server/test_service.py` 末尾有一节专门回归这几种情况。
>
> ⚠️ 出口处**刻意关闭了响应模型推断**（`response_model=None`）：本服务的 JSON 形状是
> 与前端生成代码对齐过的契约，不能让框架在出口静默改写。实测踩过 ——
> `h_presets` 标了 `-> dict` 却返回 list，FastAPI 直接 500 `ResponseValidationError`。
> 校验的收益在入口，出口保持逐字节原样。

---

## 测试

```powershell
# 纯逻辑单元测试（不联网、不起服务）—— 全局或 venv 的 python 都行
server\.venv\Scripts\python.exe server\test_filtering.py

# 集成测试（需 LightRAG:9621 与本服务:8787 都在跑）
server\.venv\Scripts\python.exe server\test_service.py
```

`test_filtering.py` 覆盖上下文裁剪的边界：只留指定 id、KG 整段丢弃、空 keep 集合、
引用表缺失时退化、**未在引用表声明的 id 一律丢弃**、真实 83K 上下文样本上的表现。

`test_service.py` 覆盖**新增能力是否有真效果**，而不只是"接口返回 200"：

- 过滤把引用从 21 收到 3，且**引用文件全部落在 v1.0 章节内（越界=[]）**
- 分类过滤后引用全部属于角色剧情
- KG 模式（chain=mix）过滤时 `kg_dropped=true`；`keep_kg=true` 时保留
- **过滤后片段为 0 时明确报错，不硬编答案**（`llm_generated=false`）
- 统计值与数据库直查一致（chunks 2439 / 实体 9896）
- 预设参数回归：`sweep` 的 `chunk_top_k=150` 必须真的传下去
- **请求体校验回归**：非法 `top_k` / 越界 `chunk_top_k` / 空 `query` / 未知 `mode` →
  422 且 `error` 里能看出是哪个字段；非法 JSON → 400（不是 422）

> **这个回归不是形式主义**：开发中它抓到一个真 bug —— `presets.params_of()` 一开始读的是
> `PRESETS[name]["params"]`，但 `PRESETS` 里的参数是**平铺**的、没有 `params` 子字典，
> 于是预设参数被静默丢掉、退回 naive 默认值。`pinpoint` 恰好等于那组默认值所以看不出来，
> 是 `chain`（应为 mix）暴露了它。

---

## 生产形态：同源托管

有 `web/dist`（`npm run build` 的产物）时，本服务会**一并静态托管**，
于是前端与 API 同源、不需要 CORS：

```
浏览器 ──► 薄服务层 :8787  ──/api/*──► 本服务（过滤 + 生成/透传）──► LightRAG :9621
              └── 其余路径 ──► web/dist/
```

> ⚠️ **这一条修正了 `website.md` A2(b) 的写法。**
> A2(b) 原方案是"把前端挂进 LightRAG 容器的 `webui` 目录"——那是**纯静态形态（L3a）**的做法，
> 它拿到同源的方式是"和 `/query` 同一个 origin"。
> 但带薄服务层时，前端必须调**本服务**的 `/api/*`，挂到 LightRAG 容器里就调不到了。
> 所以 L3b 下的同源必须由**本服务或反代**提供。目标（同源、免 CORS）没变，实现者变了。

---

## 一个未完全解释的测量

`server/test_service.py` 里量到"客户端观测到的首个 NDJSON 行 ≈ 1.4s"，但：

| 测量方式 | 结果 |
|---|---|
| 服务端打点（`h_query_stream` 的 `[timing]` 日志） | **entry→first_chunk 0.012s** |
| 最小 Starlette 应用（同样先 yield 再 await 2s，裸 socket 探针） | 首正文 **0.024s** |
| 前端 E2E 轮询（每 500ms） | 首个阶段 **≤ 0.5s** 出现 |
| 本服务的裸 socket 探针（长连接响应） | 首正文 **~1.6s** ← 与其他三项矛盾 |

裸 socket 探针读出的 1.6s 我**没能归因**（已排除：httptools 与 h11 都是 1.6s、
`Connection: close` 与 keep-alive 都是 1.6s、CORSMiddleware 不是原因、服务端打点证明首块早已产生）。

因此测试里对"首字节"只留**宽松回归护栏（≤3s）**，不做精确断言 ——
真实验收依据是服务端打点与前端观测这两条一致的证据。
如果你以后查明了这 1.6s 的成因，请回来修这段说明。
