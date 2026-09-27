# 1999RAG · 《重返未来：1999》剧情检索

以 **LightRAG** 为检索内核、面向**简体中文剧情文本**的本地知识库问答系统。

语料来自 [Reverse1999-Story-Compendium](https://github.com/VioletWilde/Reverse1999-Story-Compendium)。

**本文件只讲"这是什么、怎么从零跑起来"。** 动手改动代码或跑管线之前，
先读下面的「动手前的铁律」——那几条踩过坑，顺序错了要重建索引。

> 公开仓库只包含**能跑起来的代码 + 运行说明**（本文件、[`server/README.md`](server/README.md)、
> [`web/README.md`](web/README.md)）。开发过程中的工作笔记与推导记录不入库，
> 只存在于作者本机；下文提到它们时会标为「本机文档」。

---

## 它能做什么

围绕《重返未来：1999》简体中文剧情文本做**带引用的问答**，检索结果由图谱（实体/关系）
与向量混合召回，并支持按**游戏版本**筛选章节。

已通过 10 题回归（`python scripts/smoke_test.py`），覆盖五类能力：

| 类型 | 示例问题 | 表现 |
|---|---|---|
| 单点事实 | 维尔汀在序章对十四行诗说了什么 | 定位到 3 处对话并引用原文 |
| 跨章汇总 | 苏芙比的完整经历 | 串起庄园→瓦尔登湖→密道→逃脱全脉络 |
| 人物关系 | 维尔汀和 APPLe 的关系 | 说明是会说话的苹果同伴 |
| 说话人归属 | 「这是我的箱子，请还给我」谁说的 | 答出「维尔汀」 |
| 跨章伏笔 | 维尔汀「实验体」身份如何揭示 | 串起 112 章琥珀屋 + 102 章 + 第277号实验 |

验收标准（引用必须落到正确章节，说话人不得丢失）：

| 验收点 | 期望 |
|---|---|
| 引用落到正确章节 | `references` 的 `file_path` 应是 `101-在我们的时代里.md` 这类 |
| 说话人未丢 | 第 4 题必须答出「维尔汀」 |
| 跨章汇总 | 第 2 题应跨多个剧情单元汇总 |
| 分块真的用了 P | `data/inputs/__parsed__/*.parsed/*.blocks.jsonl` 存在且 heading 层级正确 |

---

## 已确认的范围

- **全部使用云端模型**：DeepSeek（抽取/回答）+ 阿里云百炼（Embedding / Rerank）
- **只做简体中文**（`readable/story_reader_linked/zh-CN/`）
- **不做防剧透** —— 索引里就是全部剧情，提问即可能刷到后文
- **自建前端 + 薄服务层**（`web/` + `server/`，见「前端与薄服务层」一节）。
  原生 `/workspace` 仍可用，但它做不到两件本项目需要的事：**按游戏版本/章节限定检索范围**、
  **把五档预设做成可点选的档位**
- 存储：**PostgreSQL 四件套**（单容器承担 KV / 向量 / 图 / 文档状态）

---

## 动手前的铁律

这几条是本项目真踩过坑之后定下的，**违反会破坏已花过钱的索引**。

### 灌库顺序不能颠倒

```
build_inputs.py  →  ingest.py --scan  →  ingest.py --watch  →  ingest.py --backfill
```

**根因**：LightRAG 处理完一份文件后，会把它从 `data/inputs/` **移动**到
`data/inputs/__parsed__/`（连同 `.parsed/` sidecar）。所以顶层会变空，
**第二次扫描只会得到 `0 discovered`**。
`ingest.py --scan` 已加护栏：顶层为空时直接提示"需要重新铺入"，而不是静默返回 0。

### 不可逆决策（改了就得重建整个索引）

| 项 | 冻结值 | 后果 |
|---|---|---|
| Embedding 模型 | `text-embedding-v4` | 换模型或维度 = 全部向量失效 |
| `EMBEDDING_DIM` | `1024` | 同上 |
| 存储后端 | PostgreSQL 四件套 | LightRAG **加入文档后不能更换存储实现** |
| 分块策略 | `md:native-P` | 换分块 = 全部 chunk 与图谱贡献重算 |

云端抽取是花过钱的（81 章 8,749 行 LLM 缓存）。**动这几个值之前先想清楚。**

### 保命规则

- `delete_document` **永远传 `delete_llm_cache=False`** —— 缓存是花过钱的资产
- 语料**不要**改成 submodule、不要入库（第三方版权，见「版权与许可」）
- 重灌章节用 `pipeline/reindex.py`，**不要**手动删 `data/inputs/` 里的文件
- 改了 `build_inputs.py` 的头部渲染后，要跑一次 `pipeline/ingest.py --backfill`
  （清单状态按清洗后正文的 sha256 判定，正文一变状态会被清空；索引本身没坏）
- 删文档是破坏性作业，同时只受理一个，**忙时返回 `busy` 而不抛异常** ——
  必须检查 `resp["status"] == "deletion_started"`，否则会**静默漏删**
  （`reindex.py` / `update_index.py` 已封装正确做法）

---

## 语料实况（已核实）

```
corpus/Reverse1999-Story-Compendium @ f6e18439
└── readable/story_reader_linked/zh-CN/
    ├── README.md       ← 权威目录（含阅读顺序）
    ├── mainline/       16 章   3.19 MB
    ├── activity/       23 章   4.08 MB
    ├── character/      20 章   1.29 MB
    └── anecdote/       22 章   1.04 MB
                          共 81 章 / 9.61 MB
```

正文层级（`P` 分块器直接吃这个结构）：

```markdown
# 101 · 在我们的时代里          ← 章
> 主线剧情 · 章节 101 · 阅读顺序 1 · 游戏版本 1.0 · 16 个剧情单元 · 23 条小径
## 10101 · 恶童坏种             ← 剧情单元
### 段落 1 · `script 100010`    ← 场景
**维尔汀**：这是我的箱子，请还给我。   ← 对话（说话人在粗体里）
### 小径 · 投机倒把和烂糖果      ← 小径
```

清洗时剥掉了：阅读导航块、`## 目录`、`<a id>` 锚点。

> **语料的版本信息是残缺的**：`exports/chapter_metadata.json` 只覆盖 25/81 章，
> 且主线章节号与游戏版本号没有算术关系。本项目用「显式对照表 + 章节号规则」
> 补到 80/81，并给每章标注了来源与可信度：

| `version_source` | 章数 | 来源与可信度 |
|---|---|---|
| `metadata` | 25 | 游戏自身导出字段，最权威 |
| `wiki` | 5 | 灰机 wiki 逐章实测，三方互证 |
| `number_rule` | 50 | 章节号前两位规则。**活动已验证 15/15；角色/轶事无权威字段可校验，置信度较低** |
| `null` | 1 | 313 特别篇《船喻》，无任何来源 |

> ⚠️ `number_rule` 对轶事的结果值得留意：**22 篇轶事全部落在 v1.9**。
> 这更像 `19XX` 是"内容系列编号"而非发布版本。
> **没有权威字段前，不要把这批数据当发布版本用。**
>
> 主线用显式对照表（`105=1.4 … 114=4.0`），因为主线是顺序编号而版本发布不连续；
> 活动/角色/轶事的章节号前两位即版本（`20101`→2.0）。改那张表要拿新证据，别为提高覆盖率去猜。

---

## 三个关键决策与理由

### 1. INPUT_DIR 必须扁平，一章一个文件

LightRAG 的文档身份由 **basename** 决定。源码依据：

- `document_routes.py:6222` — *"Delete only files in the current directory, preserve files in subdirectories"*
- `find_existing_file_by_file_path()` 只 `iterdir()` 顶层且跳过非文件
- 扫描分类里 `source_file == file_path.name` 判定"同一物理来源"

所以 81 章 `.md` 直接平铺在 `data/inputs/`，不建子目录。
章号前缀（`101-`、`11101-`…）已验证全局唯一，不会撞名。

### 2. 存储用 PostgreSQL 四件套，而不是默认的文件型

```bash
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_GRAPH_STORAGE=PGTableGraphStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage
```

理由：

1. 上游 `LightRAG/AGENTS.md` 自己写着，五个文件型存储
   *"are supported for **small-scale testing and validation only**"*
2. `NetworkXStorage` 每次图编辑都要**重写整份 GraphML**（20 万节点约 17s）
3. **LightRAG 加入文档后不能更换存储实现**，而云端抽取要花钱 —— 选错就是重新索引一遍
4. `PGTableGraphStorage` 是纯表实现，**不需要 Apache AGE**，
   官方 `pgvector/pgvector:pg18` 镜像就够

### 3. 分块用 `md:native-P`

```bash
LIGHTRAG_PARSER=md:native-P,*:legacy-R
CHUNK_P_SIZE=2000
```

`native` 引擎解析 Markdown 时产出 `.blocks.jsonl`（含 `heading` / `level` /
`parent_headings`），`P`（段落语义）分块器按**标题边界**切块、章节之间不重叠、
保留完整标题路径 —— 正好匹配「章 → 剧情单元 → 段落」和对话体的大量短段落。

> ⚠️ 若 sidecar 没生成，`P` 会**静默降级为 R**。灌完第一批后用
> `python pipeline/ingest.py --check-parser` 验证路由。

---

## 目录结构

```
1999RAG/
├── LightRAG/                     # 上游源码（独立 clone，不进 git）
├── corpus/                       # 语料（独立 clone，不进 git）
├── .env / .env.example           # 配置（.env 含密钥，不进 git）
├── .gitattributes                # 换行符策略（Dockerfile 续行 / CRLF 坑）
├── .gitignore
├── docker-compose.yml            # postgres + lightrag 编排
├── README.md                     # ← 本文件：简介与从零复现
├── docs/
│   └── (开发笔记不入库，见下)
├── pipeline/                     # 数据管线
│   ├── chapter_index.py          #   语料目录 → state/chapter_index.json
│   ├── build_inputs.py           #   语料 → data/cleaned/ + data/inputs/ + manifest
│   ├── ingest.py                 #   灌库 / 看进度 / 回填 / 校验解析器
│   ├── update_index.py           #   语料更新后的增量重索引（含布局熔断）
│   ├── reindex.py                #   强制重灌指定章节（清洗逻辑变更后用）
│   └── lib/
│       ├── lightrag_client.py    #   REST 客户端（纯标准库）
│       └── query_planner.py      #   五档检索预设的**唯一真源**
├── server/                       # 薄服务层（L3b）：版本过滤 + 生成 + 同源托管
│   ├── README.md                 #   ← 服务层说明：接口契约、为什么用 venv + FastAPI
│   ├── app.py                    #   FastAPI 路由与请求体校验
│   ├── filtering.py              #   上下文裁剪（纯逻辑，可单测）
│   ├── generation.py             #   裁剪后的自定义生成
│   ├── presets.py                #   从 pipeline 导入预设，保证同源
│   ├── requirements.txt          #   精确钉版本（装在 server/.venv）
│   ├── test_filtering.py         #   纯逻辑单测（不联网）
│   └── test_service.py           #   集成测试（需服务在跑）
├── web/                          # 前端：React 18 + Vite 6 + TS，手写 CSS 令牌
│   ├── README.md                 #   ← 前端说明：怎么起、令牌在哪、为什么用 hash 路由
│   ├── src/api/presets.ts        #   由 query_planner 生成，不进手改
│   ├── src/styles/tokens.css     #   设计令牌唯一处（换肤只改这里）
│   ├── scripts/verify-app.mjs    #   CDP 端到端验证（真起浏览器、轮询 DOM）
│   └── public/                   #   背景图/台词数据等第三方素材（不进 git）
├── state/                        # 状态清单（进 git）
│   ├── corpus.lock.json          #   语料 commit 锁定
│   ├── chapter_index.json        #   81 章的序号/分类/标题/版本 + 来源
│   └── index_manifest.json       #   每章 sha256 + doc_id + 索引状态
├── data/                         # 运行时数据（不进 git）
│   ├── inputs/                   #   ← INPUT_DIR（81 章平铺 + __parsed__）
│   ├── cleaned/                  #   清洗后正文
│   ├── rag_storage/              #   ← WORKING_DIR
│   ├── prompts/entity_type/      #   实体类型定义
│   ├── ui_templates/             #   品牌定制包（可选，空则惰性）
│   └── pgdata/                   #   PostgreSQL 数据目录（≈970 MB，绝不入库）
├── deploy/
│   ├── initdb/01-vector.sql      #   CREATE EXTENSION vector
│   └── Dockerfile.lightrag       #   由 build-image.ps1 使用
└── scripts/
    ├── build-image.ps1           # 构建镜像（绕开 syntax 联网问题 + .sh 转 LF）
    ├── up.ps1 / down.ps1         # 启停
    ├── status.ps1 / logs.ps1     # 巡检 / 日志
    ├── smoke_test.py             # 回归题库
    ├── preset_matrix.py          # 预设参数标定矩阵
    └── gen_web_presets.py        # 预设 → web/src/api/presets.ts
```

> **开发笔记不入库。** 除了上面列出的三份 README，其余 `.md`
> （协作约定与踩坑手册、交接记录、网站设计推导、检索参数标定证据、选型报告、
> 分层架构）都是**本机文档**：仍在作者工作区里，但不在版本历史中，新 clone 不会有。
> 公开仓库只保留**能跑起来的代码 + 运行说明**。

---

## 怎么跑（从零开始）

### 0. 取语料与上游源码

前置：Docker Desktop、Python 3.10+、git（Windows 建议用 PowerShell 7）。

```powershell
git clone https://github.com/abyss-stars/reverse1999-RAG.git
cd reverse1999-RAG

# ① 语料：第三方版权内容，本仓库不含原文，必须单独 clone
git clone https://github.com/VioletWilde/Reverse1999-Story-Compendium.git corpus/Reverse1999-Story-Compendium
cd corpus/Reverse1999-Story-Compendium
git checkout f6e18439        # 锁定到 state/corpus.lock.json 记录的版本
cd ../..

# ② 上游 LightRAG 源码（构建镜像要用）
git clone https://github.com/HKUDS/LightRAG.git LightRAG
```

> 语料仓库仍在更新，`f6e18439` 是本项目索引时用的版本。
> 要换新版本，**先**跑 `python pipeline/update_index.py --check` 看差异再决定 ——
> 该语料曾把 1977 个单元文件重构成 82 个章节文件 —— **朴素 diff 会变成"删 81 加 1977"的灾难**，
> 所以脚本内置布局变更熔断（文件数变化超 30%，或新版本匹配数为 0 时直接中止，
> 提示改走全量重建；需 `--force-layout` 才强行增量）。

### 1. 填 `.env`

```powershell
copy .env.example .env
notepad .env
```

本项目**同时用了两家云服务商**，所以要**两把不同的 Key**：

| 角色 | 服务商 | 变量 | 模型 |
|---|---|---|---|
| 抽取 / 关键词 / 回答 | DeepSeek | `LLM_BINDING_API_KEY` | `deepseek-flash` |
| Embedding | 阿里云百炼 | `EMBEDDING_BINDING_API_KEY` | `text-embedding-v4` |
| Rerank | 阿里云百炼 | `RERANK_BINDING_API_KEY` | `gte-rerank-v2` |

把 `.env` 里所有 `sk-REPLACE_ME` 换成对应服务商的 Key ——
**别把 DeepSeek 的 Key 填进百炼那几栏**，两家不通用。
顺手把 `POSTGRES_PASSWORD` 从默认值改掉。

其余关键项已按实测配置写好，一般不用动：

| 变量 | 值 | 备注 |
|---|---|---|
| `LLM_BINDING_HOST` | `https://api.deepseek.com/v1` | |
| `EMBEDDING_BINDING_HOST` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | |
| `EMBEDDING_DIM` | `1024` | |
| `EMBEDDING_BATCH_NUM` | `10` | **百炼单次上限就是 10，填 16 会报 400** |
| `LIGHTRAG_PARSER` | `md:native-P,*:legacy-R` | 见「决策 3」 |
| `CHUNK_P_SIZE` | `2000` | |
| `EXTRACT_`/`KEYWORD_OPENAI_LLM_EXTRA_BODY` | `{"thinking":{"type":"disabled"}}` | 推理模型按角色关思考，3.3× 提速 |

> ⚠️ **Embedding 模型/维度、存储后端、分块策略一旦灌了数据就不能改**，
> 改了等于重建整个索引（云端抽取要再花一次钱）。
> 完整的不可逆清单见上面「动手前的铁律」。

### 2. 构建镜像并启动

```powershell
.\scripts\build-image.ps1     # 首次构建 lightrag-1999:local（含前端，约 10 分钟）
.\scripts\up.ps1              # 启动 postgres + lightrag
```

Windows 上**不要**直接用 `docker compose build`：BuildKit 不走 Docker Desktop 的代理，
且上游 `Dockerfile` 的 `# syntax=` 指令会触发联网拉前端镜像 —— 两者都会让构建超时。
`build-image.ps1` 已处理这两件事（去掉该指令 + 预拉基础镜像 + 带代理 build-arg），
另外它还会把构建上下文里的 `.sh` 转成 LF：容器里 CRLF 的 shebang 会变成
`#!/bin/sh\r`，内核找不到 `sh\r` 这个解释器，于是 `restart: unless-stopped` 会无限重启。

### 3. 确认服务在跑

```powershell
.\scripts\status.ps1
```

应该看到 `core_version: 1.5.8`、PG 里 13 张表、`pipeline_busy: False`。
若没起来：`.\scripts\up.ps1`（镜像不存在时会自动构建）。

启动后：

- WebUI 管理端　<http://localhost:9621/webui>
- 问答入口　　　<http://localhost:9621/workspace>
- API 文档　　　<http://localhost:9621/docs>

### 4. 灌库（先主线 16 章验证）

⚠️ **顺序不能颠倒**：LightRAG 处理完会把源文件归档进 `__parsed__/`，
所以**每次扫描前都要先重新铺入**。

```powershell
python pipeline/build_inputs.py --categories mainline   # ① 先铺进 INPUT_DIR
python pipeline/ingest.py --scan                        # ② 触发扫描入队
python pipeline/ingest.py --watch                       # ③ 盯进度
python pipeline/ingest.py --backfill                    # ④ 回填 doc_id/状态/chunks
```

先只灌主线 16 章是省钱验证路径（实测约 27 分钟）。确认验收通过后再全量，见第 6 步。

### 5. 验收

```powershell
python scripts/smoke_test.py            # 一次跑完所有题目并给出 PASS/FAIL
python scripts/smoke_test.py --only 4   # 只跑第 4 题（说话人归属，有硬性判据）
```

四条硬性验收点见上面「它能做什么」下的表。

### 6. 全量灌库

```powershell
python pipeline/build_inputs.py --categories mainline,activity,character,anecdote
python pipeline/ingest.py --scan
python pipeline/ingest.py --watch
python pipeline/ingest.py --backfill
```

**规模与耗时**（用于评估磁盘和 API 预算）：

| | 首次验证（主线 16 章） | 全量 81 章 |
|---|---|---|
| 实体 / 关系 | 3,783 / 6,090 | **9,896 / 16,737** |
| chunks | 837 | **2,439** |
| LLM 抽取缓存 | 2,302 行 | **8,749 行** |
| 数据库 | 212 MB | **630 MB** |
| 耗时 | ≈27 分钟 | ≈112 分钟 |

> 「全量」列是 2026-09-26 对 `rag` 库直查的结果（`graph_nodes` / `graph_edges` /
> `lightrag_doc_chunks` / `lightrag_llm_cache`）。「首次验证」列是当时实测，
> 只作量级参考，未随全量索引更新。
>
> 其中向量约占 **470 MB**（关系 269 + 实体 159 + chunk 42）——
> 这也是为什么存储必须用 PG + pgvector，而不是文件型。

已 PROCESSED 的章节源文件重新铺入后会被判为 `already processed` 并再次归档，
**不会重复抽取**（缓存命中）。

---

## 前端与薄服务层

原生 `/workspace` 能用，但它**没有**两样本项目需要的能力：按游戏版本/章节限定检索范围、
把五档检索预设做成可点选的档位。所以有了 `web/`（前端）+ `server/`（薄服务层）。

**为什么必须要一层服务端**：LightRAG 的 `/query` 把**检索与生成绑在一起**，
中间插不进过滤。所以过滤只能在服务层做 —— 拆成「取上下文 → 裁剪 → 自己生成」三段。
不设过滤时则**原样透传** LightRAG 的流，以保住已被 `smoke_test.py` 验证过的生成质量。

### 起三个进程

```powershell
# ① LightRAG 后端（:9621）—— 见上面「怎么跑」
.\scripts\up.ps1

# ② 薄服务层（:8787）—— 有自己的 venv，不要用全局 Python（全局有 9 处依赖冲突）
python -m venv server\.venv
server\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
server\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8787

# ③ 前端（:5173）
cd web; npm install; npm run dev
```

开发期 `/api` 由 Vite 代理到 :8787，全链路同源、不依赖 CORS。
**上线**时 `web/dist` 由薄服务层一并托管（`server/app.py` 末尾的 `StaticFiles`），
也是同源 —— 注意此时**不能**把前端挂进 LightRAG 容器的 `webui` 目录，
那样它就调不到本服务的 `/api/*` 了。

### 验证

```powershell
server\.venv\Scripts\python.exe server\test_filtering.py   # 纯逻辑单测（不联网）
server\.venv\Scripts\python.exe server\test_service.py     # 集成测试（需 :9621 + :8787）
node web\scripts\verify-app.mjs                            # 端到端：真起浏览器轮询 DOM
python scripts\smoke_test.py                               # 整库 10 题验收
```

`verify-app.mjs` 用 CDP（不是 `--screenshot`，那会被定时器烧掉虚拟时钟）真起一个
headless 浏览器、**轮询 DOM 直到回答落地**再断言，并留一张截图在 `docs/ref/`。
它验的是"能力真的有"而不只是"返回 200"：引用卡默认最多 4 条、
点正文里 >4 的角标能把对应卡片提升为可见。

> **这里抓到一个真 bug（值得记下来）**：引用区默认只渲染前 4 条，
> 但答案正文里可能写着 `[21]` —— 卡片不存在时点角标**毫无反应**。
> 于是加了"点角标即临时提升该条为可见"。第一版在 `running` 由 true 变 false（流结束）
> 时无条件清空提升状态，看起来没问题，但 E2E 偶发失败：答案落地后立刻点角标，
> 提升被 completion 的那次重置抹掉了。根因是 `Page.captureScreenshot`
> （整页截图，正文很长时很慢）阻塞渲染进程，把 React 的 passive effect 冲刷**推迟到了点击之后**。
> 修法是只在"新一轮**开始**"时清状态，不在结束时清 —— 顺带修掉了
> "流式过程中展开引用，答案一落地就被自动收起"这个真实可见的问题。
> 教训：**探针的读数本身也要被怀疑**。中途我曾以为是 `Boolean(getElementById(...))`
> 读不到 DOM 节点，专门写了个最小实验证明它是对的（存在→`{}`→true，不存在→`null`→false），
> 才把方向转回代码。

---

## 增量更新（游戏发新版本时）

```powershell
python pipeline/update_index.py --check      # 上游有没有更新
python pipeline/update_index.py --plan       # 看要动哪些章（只读）
python pipeline/update_index.py --apply      # 执行
```

脚本封装了 delete → stage → scan → backfill → 更新 `corpus.lock.json` 全流程，
删除时保持 `delete_llm_cache=False`，**未被改动的 chunk 重灌时直接命中缓存**。

**必须"先删后传"**（均已在 LightRAG 源码核实）：同名上传返回 409、
内容 hash 会被判重、`process_options`/`chunk_options` 在入队时就冻结。

> ⚠️ 这个语料的目录布局**结构性变过**（v1.1.0 的 1977 个单元文件 → v1.2.0 的 82 个章节文件），
> 朴素 diff 会变成"删 81 加 1977"的灾难。`update_index.py` 因此内置**布局变更熔断**，
> 布局熔断的触发条件与演练结果见上。

改了清洗/渲染逻辑后需要刷新索引正文时，用 `pipeline/reindex.py`
（扫描不会重灌已 PROCESSED 的文档，必须先删后传；删除时固定 `delete_llm_cache=False`）。

---

## 后续可做

- **上服务器**：Nginx + TLS；迁移只需 `pg_dump` + `data/inputs/` + `state/`
- ~~接上 UI~~：**已完成** —— `web/` 自建前端 + `server/` 薄服务层，见「前端与薄服务层」。
  原生 `/workspace` 与 `/webui` 仍保留可用（管理端在后者的图形界面里最方便）
- ~~检索预设~~：**已完成** —— 五档预设已是前端可点选的档位，
  参数唯一真源是 `pipeline/lib/query_planner.py`，前端契约由 `scripts/gen_web_presets.py` 生成
- **KG 按章节过滤**：目前启用范围限定时会**整段丢弃图谱上下文**
  （实体/关系行不带来源字段，无法按章节过滤）。彻底方案要按 DB 的
  `lightrag_entity_chunks` + `lightrag_doc_chunks` 反查实体所属章节
- **多轮对话**：现在是单轮问答，历史不进上下文

---

## 版权与许可

| 范围 | 许可 / 归属 |
|---|---|
| **本仓库代码**（`pipeline/` `scripts/` `deploy/` `server/` `web/src/` 等） | [MIT](LICENSE) |
| **剧情文本** | 版权归其权利人所有。本仓库**不含**语料原文 —— 语料独立 clone 且被 `.gitignore` 排除，仅用于本地个人检索 |
| **上游 LightRAG** | `LightRAG/` 为独立 clone，遵循其自身许可（MIT），不纳入本仓库 |
| **第三方美术素材** | `web/public/bg/`（整站背景图）、`docs/ref/`（比对用截图）均为**官方美术资源**，被 `.gitignore` 排除、**不随仓库分发**，仅供本机自用。上线需换自制素材 —— 换图只需改 [`web/src/main.tsx`](web/src/main.tsx) 里的 `BG_FILE` 一处 |

---

## 相关文档

公开仓库里的文档只有这三份：

| 文档 | 内容 |
|---|---|
| **本文件** | 项目简介、前置条件、从零复现、动手前的铁律、版权 |
| [`server/README.md`](server/README.md) | 薄服务层：为什么用 venv + FastAPI、接口契约、请求体校验、已知测量 |
| [`web/README.md`](web/README.md) | 前端：怎么起、设计令牌在哪、为什么用 hash 路由 |

> 开发过程的笔记（协作约定与踩坑手册、交接记录、网站设计推导、检索参数标定证据、
> 选型报告、分层架构与里程碑）**不入库**，只存在于作者本机工作区。
> 其中会影响正确使用的硬约束，已内联进本文件（见「动手前的铁律」「语料实况」）。
