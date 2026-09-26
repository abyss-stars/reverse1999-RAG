# 1999RAG · 《重返未来：1999》剧情检索

以 **LightRAG** 为检索内核、面向**简体中文剧情文本**的本地知识库问答系统。

语料来自 [Reverse1999-Story-Compendium](https://github.com/VioletWilde/Reverse1999-Story-Compendium)。

**本文件只讲"这是什么、怎么从零跑起来"。**
动手改动代码或跑管线之前，请先读 [`AGENTS.md`](AGENTS.md)——
那里有操作顺序铁律、踩过的坑、数据可信度分级和排障手册。

---

## 它能做什么

围绕《重返未来：1999》简体中文剧情文本做**带引用的问答**，检索结果由图谱（实体/关系）
与向量混合召回，并支持按**游戏版本**筛选章节。

已通过 10 题回归（`python scripts/smoke_test.py`），覆盖四类能力：

| 类型 | 示例问题 | 表现 |
|---|---|---|
| 单点事实 | 维尔汀在序章对十四行诗说了什么 | 定位到 3 处对话并引用原文 |
| 跨章汇总 | 苏芙比的完整经历 | 串起庄园→瓦尔登湖→密道→逃脱全脉络 |
| 人物关系 | 维尔汀和 APPLe 的关系 | 说明是会说话的苹果同伴 |
| 说话人归属 | 「这是我的箱子，请还给我」谁说的 | 答出「维尔汀」 |
| 跨章伏笔 | 维尔汀「实验体」身份如何揭示 | 串起 112 章琥珀屋 + 102 章 + 第277号实验 |

验收标准（引用必须落到正确章节，说话人不得丢失）见 [`AGENTS.md` §4.5](AGENTS.md#45-验收回归)。

---

## 已确认的范围

- **全部使用云端模型**：DeepSeek（抽取/回答）+ 阿里云百炼（Embedding / Rerank）
- **只做简体中文**（`readable/story_reader_linked/zh-CN/`）
- **不做防剧透** —— 直接用 LightRAG 原生 WebUI 问答，不自建前端
- 存储：**PostgreSQL 四件套**（单容器承担 KV / 向量 / 图 / 文档状态）

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
> 补到 80/81，并给每章标注了来源与可信度。详见 [`AGENTS.md` §2.8 / §3](AGENTS.md#28-主线版本号推不出来只能查表)。

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
├── AGENTS.md                     # 约定 / 坑 / 手册（动手前必读）
├── 流程与架构.md                  # 分层架构、数据流、决策推导、里程碑
├── docs/
│   └── RAG选型报告.md             # 为什么选 LightRAG
├── pipeline/                     # 数据管线
│   ├── chapter_index.py          #   语料目录 → state/chapter_index.json
│   ├── build_inputs.py           #   语料 → data/cleaned/ + data/inputs/ + manifest
│   ├── ingest.py                 #   灌库 / 看进度 / 回填 / 校验解析器
│   ├── update_index.py           #   语料更新后的增量重索引（含布局熔断）
│   ├── reindex.py                #   强制重灌指定章节（清洗逻辑变更后用）
│   └── lib/lightrag_client.py    #   REST 客户端（纯标准库）
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
│   └── pgdata/                   #   PostgreSQL 数据目录（871 MB，绝不入库）
├── deploy/
│   ├── initdb/01-vector.sql      #   CREATE EXTENSION vector
│   └── Dockerfile.lightrag       #   由 build-image.ps1 使用
└── scripts/
    ├── build-image.ps1           # 构建镜像（绕开 syntax 联网问题 + .sh 转 LF）
    ├── up.ps1 / down.ps1         # 启停
    ├── status.ps1 / logs.ps1     # 巡检 / 日志
    └── smoke_test.py             # 回归题库
```

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
> 该语料曾把 1977 个单元文件重构成 82 个章节文件（见 [`AGENTS.md` §4.3](AGENTS.md#43-增量更新游戏发新版本时)）。

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
> 完整的不可逆清单见 [`AGENTS.md` §0.2](AGENTS.md#02-不可逆决策改了就得重建整个索引)。

### 2. 构建镜像并启动

```powershell
.\scripts\build-image.ps1     # 首次构建 lightrag-1999:local（含前端，约 10 分钟）
.\scripts\up.ps1              # 启动 postgres + lightrag
```

Windows 上**不要**直接用 `docker compose build`：BuildKit 不走 Docker Desktop 的代理，
且上游 `Dockerfile` 的 `# syntax=` 指令会触发联网拉前端镜像。
原因与修法见 [`AGENTS.md` §1.3 / §1.4](AGENTS.md#13-docker-compose-build-必失败)。

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

四条硬性验收点见 [`AGENTS.md` §4.5](AGENTS.md#45-验收回归)。

### 6. 全量灌库

```powershell
python pipeline/build_inputs.py --categories mainline,activity,character,anecdote
python pipeline/ingest.py --scan
python pipeline/ingest.py --watch
python pipeline/ingest.py --backfill
```

**预期规模与耗时**（用于评估磁盘和 API 预算）：

| | 主线 16 章 | 全量 81 章 |
|---|---|---|
| 实体 / 关系 | 3,783 / 6,090 | **9,935 / 16,768** |
| chunks | 837 | **2,439** |
| LLM 抽取缓存 | 2,302 行 | **≈6,700 行** |
| 数据库 | 212 MB | **560 MB** |
| 耗时 | ≈27 分钟 | **≈112 分钟** |

> 其中向量约占 423 MB（关系 234 + 实体 149 + chunk 40）——
> 这也是为什么存储必须用 PG + pgvector，而不是文件型。

已 PROCESSED 的章节源文件重新铺入后会被判为 `already processed` 并再次归档，
**不会重复抽取**（缓存命中）。

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
> 详情与演练结果见 [`AGENTS.md` §4.3](AGENTS.md#43-增量更新游戏发新版本时)。

改了清洗/渲染逻辑后需要刷新索引正文时，用 `pipeline/reindex.py`（详见 [AGENTS.md §4.4](AGENTS.md#44-强制重灌指定章节)）。

---

## 后续可做

- **上服务器**：Nginx + TLS；迁移只需 `pg_dump` + `data/inputs/` + `state/`
- **接上 UI**：直接用 LightRAG 原生 `/workspace`（问答）与 `/webui`（管理）；
  想换品牌可用 `UI_TEMPLATES_DIR`（compose 已挂好 `./data/ui_templates`），**无需重建前端**
- **查询规划器**：宽泛聚合类问题（如「2.0~3.0 之间有哪些重大事件」）的瓶颈是
  `max_total_tokens` 而非 `chunk_top_k`，可按问题类型自动调参。见 [AGENTS.md §6](AGENTS.md#6-已知未修问题)

---

## 版权与许可

| 范围 | 许可 / 归属 |
|---|---|
| **本仓库代码**（`pipeline/` `scripts/` `deploy/` 等） | [MIT](LICENSE) |
| **剧情文本** | 版权归其权利人所有。本仓库**不含**语料原文 —— 语料独立 clone 且被 `.gitignore` 排除，仅用于本地个人检索 |
| **上游 LightRAG** | `LightRAG/` 为独立 clone，遵循其自身许可（MIT），不纳入本仓库 |

---

## 相关文档

| 文档 | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | 操作铁律、环境修复记录、配置与行为坑、数据可信度、操作手册、已知未修问题 |
| [`流程与架构.md`](流程与架构.md) | 分层架构、数据流、五个关键决策、部署形态、里程碑 M0-M8 |
| [`docs/RAG选型报告.md`](docs/RAG选型报告.md) | 为什么选 LightRAG，与其他框架的对比 |
