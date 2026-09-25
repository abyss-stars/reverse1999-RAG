# 1999RAG · 《重返未来：1999》剧情检索

以 **LightRAG** 为检索内核、面向**简体中文剧情文本**的本地知识库问答系统。
语料来自 [Reverse1999-Story-Compendium](https://github.com/VioletWilde/Reverse1999-Story-Compendium)。

---

## 当前进度

| 步骤 | 状态 |
|---|---|
| ① 环境诊断 | ✅ Docker Desktop（`E:\Docker\Program`）+ 本地代理 `127.0.0.1:7890` |
| ② 修 Docker 插件 | ✅ `docker compose` / `docker buildx` 可用（见「环境修复记录」） |
| ③ 语料 clone | ✅ `corpus/Reverse1999-Story-Compendium` @ `f6e18439` |
| ④ 章节索引 | ✅ 81 章 |
| ⑤ 语料清洗 | ✅ `data/cleaned/` 81 章；`data/inputs/` 已铺入**主线 16 章** |
| ⑥ PostgreSQL | ✅ 运行中（PG 18.6 + pgvector 0.8.6，端口 5433） |
| ⑦ 实体类型定义 | ✅ `data/prompts/entity_type/entity_type_prompt.yml` |
| ⑧ LightRAG 镜像 | ✅ `lightrag-1999:local`（v1.5.8，从本地源码构建） |
| ⑨ 服务启动 | ✅ <http://localhost:9621> 已就绪，PG 13 张表已建 |
| ⑩ P 分块验证 | ✅ 离线解析 101 章 → 58 blocks，层级正确（`{1:1, 2:16, 3:41}`） |
| ⑪ 填 API Key | ✅ DeepSeek(LLM) + 百炼(Embedding/Rerank) |
| ⑫ 单章冒烟测试 | ✅ 101 章：22 chunks / 200 实体 / 302 关系 |
| ⑬ 验收四类问题 | ✅ **4/4 通过** |
| ⑭ 抽取关推理优化 | ✅ `EXTRACT/KEYWORD` 关思考 → **3.3× 提速**，质量不降 |
| ⑮ **主线 16 章灌完** | ✅ 3783 实体 / 6090 关系 / 837 chunks |
| ⑯ 增量更新脚本 | ✅ `pipeline/update_index.py`（按 blob 比对 + 布局变更熔断） |
| ⑰ **全语料 81 章灌完** | ✅ **9935 实体 / 16768 关系 / 2439 chunks / 560 MB** |
| ⑱ 验收回归 | ✅ **10/10 通过** |

### 全语料索引规模（81 章 / 9.49 MB 清洗后文本）

| 指标 | 值 |
|---|---|
| 文档 | **81 / 81 PROCESSED** |
| 图节点（实体） | **9,935** |
| 图边（关系） | **16,768** |
| chunks | **2,439** |
| 向量写入 | entity 9935 / relation 16768 / chunk 2439 —— 全成功 |
| LLM 抽取缓存 | **6,660** 行（≈81 MB，重灌时几乎全命中） |
| 数据库 | **560 MB** |

各表占用：

| 表 | 大小 | 说明 |
|---|---|---|
| `lightrag_vdb_relation_...` | 234 MB | 关系向量 + 关系描述文本 |
| `lightrag_vdb_entity_...` | 149 MB | 实体向量 + 实体描述文本 |
| `lightrag_llm_cache` | 81 MB | 抽取缓存（花过钱的，别删） |
| `lightrag_vdb_chunks_...` | 40 MB | chunk 向量 |
| `lightrag_graph_edges` | 11 MB | 图边 |
| `lightrag_doc_chunks` | 11 MB | chunk 正文 |

### 主线 16 章灌库实测

| 指标 | 值 |
|---|---|
| 文档 | 16 / 16 PROCESSED |
| 图节点（实体） | **3,783** |
| 图边（关系） | **6,090** |
| chunks | **837** |
| 向量写入 | entity 3783 / relation 6090 / chunk 837 —— 全成功 |
| LLM 抽取缓存 | **2,302** 行（重灌时几乎全命中） |
| DB 大小 | 212 MB |
| 耗时 | **约 27 分钟**（14 章，3.0 MB） |

### 单章冒烟测试实测数据（101 章 · 98 KB）

| 指标 | 值 |
|---|---|
| 解析 block 数 | 58（`{level1:1, level2:16, level3:41}`） |
| 切分 chunk 数 | 22（P 分块器把同父标题下的短段落合并到接近 2000 token） |
| 抽出实体 / 关系 | 200 / 302 |
| 实体类型分布 | character 47 · item 38 · location 32 · term 27 · organization 19 · timeperiod 9 · work 9 · event 8 · creature 8 |
| 向量写入 | entity 200 / relation 302 / chunk 22 —— 全部成功 |
| LLM 抽取缓存 | 55 → 56 行（**重扫几乎全部命中缓存**） |
| 首轮耗时 | 约 3 分钟（抽取 ~80s + 合并 ~100s） |
| 问答耗时 | 2.9 ~ 27.8 s（mix 模式 + rerank） |

### 验收结果

| # | 类型 | 问题 | 结果 |
|---|---|---|---|
| 1 | 单点事实 | 维尔汀在序章对十四行诗说了什么 | ✅ 定位到 3 处对话并引用原文 |
| 2 | 跨章汇总 | 苏芙比的完整经历 | ✅ 串起庄园→瓦尔登湖→密道→逃脱全脉络 |
| 3 | 人物关系 | 维尔汀和 APPLe 的关系 | ✅ 说明是会说话的苹果同伴 |
| 4 | 说话人归属 | 「这是我的箱子，请还给我」谁说的 | ✅ 答出「维尔汀」 |
| 5 | 跨主线·人物 | 阿尔卡纳是谁？和维尔汀发生过什么 | ✅ 串起 102/105/107/110/112/113 六章 |
| 6 | 跨主线·世界观 | 「暴雨」是什么？有什么影响 | ✅ 汇总机制/症候/影响/各方立场/免疫手段 |
| 7 | 跨主线·伏笔 | 维尔汀「实验体」身份如何揭示 | ✅ 串起 112 章琥珀屋 + 102 章 + 第277号实验 |
| 8 | 角色剧情分类 | 角色剧情《打虎记》讲了什么 | ✅ 完整复述程和光/秀郎中/白虎/万两会票结局 |
| 9 | 轶事分类 | 轶事《塞梅尔维斯》讲了什么 | ✅ 破案线 + 血食怪挣扎 + 多瑙黎明号 |
| 10 | 活动分类 | 活动《飞驰！明日之城》梗概 | ✅ **主动声明只检索到 13 个剧情单元中的 1 个，未编造** |

> 第 8/9/10 题分别压测三个新分类；第 7 题是跨主线伏笔题。
>
> 第 10 题的表现值得单独说：它没有硬编一个梗概，而是明确说
> "上下文中只提供了 `2010101 · 周末狂热` 一个单元……其余 12 个未出现，
> 因此无法给出完整梗概"。**这种"承认不知道"的行为比编造答案有价值得多。**
> 想让这类"整体梗概"问题答得更全，可以临时调高 `CHUNK_TOP_K` 或改用 `global` 模式。

## 已确认的范围

- **全部使用云端模型**：阿里云百炼 / DashScope（Qwen）
- **只做简体中文**（`readable/story_reader_linked/zh-CN/`）
- **不做防剧透** —— 直接用 LightRAG 原生 WebUI 问答，不自建前端
- 存储：**PostgreSQL 四件套**
- 首次灌库：**只灌主线 16 章**，验证达标后再加灌其余 65 章

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
3. **LightRAG 加入文档后不能更换存储实现**，而云端抽取要花钱 ——
   选错就是重新索引一遍
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
> `python pipeline/ingest.py --check-parser` 验证路由，并检查
> `data/inputs/__parsed__/` 下是否真有 `.blocks.jsonl`。

---

## 环境修复记录（排障用）

这台机器上有三个坑，都已修好：

### ① `docker compose` 不可用

Docker Desktop 自带插件在 `E:\Docker\Program\resources\cli-plugins\`，
但没注册到用户插件目录，且**重启 Docker Desktop 会重置**
`~/.docker/cli-plugins`。持久修法写进 docker CLI 配置：

```json
// ~/.docker/config.json
"cliPluginsExtraDirs": ["E:\\Docker\\Program\\resources\\cli-plugins"]
```

### ② Docker 守护进程不走代理

Docker Hub 被墙（`auth.docker.io` 超时），而系统代理没被 Docker 继承。
写入 Docker Desktop 设置并重启：

```json
// %APPDATA%\Docker\settings-store.json
"ProxyHttpMode": "manual",
"OverrideProxyHTTP": "http://127.0.0.1:7890",
"OverrideProxyHTTPS": "http://127.0.0.1:7890",
"OverrideProxyExclude": "localhost,127.0.0.1,*.local,192.168.*,10.*,172.16.*"
```

重启：`& "E:\Docker\Program\DockerCli.exe" -Shutdown` 然后启动
`Docker Desktop.exe`。（备份在 `settings-store.json.bak-1999rag`）

### ③ `docker compose build` 必失败

上游 Dockerfile 第一行 `# syntax=docker/dockerfile:1` 会让 BuildKit 去
Docker Hub 拉 frontend 镜像，而 **BuildKit 不走上面那个代理**，必然超时。

修法：用 `scripts/build-image.ps1`。它把该指令去掉（BuildKit 内建 frontend
支持 cache mount，功能不受影响），并把基础镜像预拉本地化，再带代理 build-arg 构建。

### ④ 容器起来就无限重启：`exec ... no such file or directory`

```
1999rag-lightrag | exec /usr/local/bin/docker-entrypoint.sh: no such file or directory
Status=restarting  ExitCode=255
```

文件明明 COPY 进镜像了。真正原因是 **CRLF 行尾**：

- 本机 `git config core.autocrlf=true`，checkout 出来的 `docker-entrypoint.sh` 是 CRLF
- 进到 Linux 容器后 shebang 变成 `#!/bin/sh\r`
- 内核找不到名为 `sh\r` 的解释器 → 报告"文件不存在"，`restart: unless-stopped`
  于是无限重启

修法：`scripts/build-image.ps1` 在构建前把构建上下文里所有 `.sh` 转成 LF。
（`autocrlf=true` 下 git 比较会做 CRLF→LF 归一，所以转完之后
`LightRAG` 工作区在 `git status` 里依然是干净的，不污染上游 checkout。）

---

## 配置与行为坑（灌库时踩到的，都已修好）

### ① `EMBEDDING_BATCH_NUM=16` → 400 错误

```
<400> InternalError.Algo.InvalidParameter: Value error,
      batch size is invalid, it should not be larger than 10.: input.contents
```

**百炼的 OpenAI 兼容 embedding 接口单次上限正好是 10 条**（实测 10 通过、11 失败）。
本机 `.env` 已改为 `EMBEDDING_BATCH_NUM=10`。

> 症状具有迷惑性：抽取阶段（实体/关系）全部成功，只在最后写向量时报
> `PGVectorStorage[entities] index flush failed`，看起来像数据库问题，其实是 embedding 批量超限。

### ② LightRAG 会把源文件**归档**进 `__parsed__/`

处理完一份文件后，`data/inputs/xxx.md` 会被移动到
`data/inputs/__parsed__/xxx.md`（连同 `.parsed/` sidecar）。
所以**第二次扫描会得到 `0 discovered`** —— 顶层已经没有文件了。

**规矩：每次 `scan` 之前都要先重新铺入。**

```powershell
python pipeline/build_inputs.py --categories mainline   # 先铺
python pipeline/ingest.py --scan                        # 再灌
```

`ingest.py --scan` 已加护栏：顶层为空时直接提示"需要重新铺入"而不是静默 0。

### ③ `--watch` 只看 `busy` 会秒退

scan 的**分类阶段**跑在 `scanning_exclusive` 下，此时 `busy` 仍是 `False`。
只判 `busy` 会在扫描刚启动时误判成"已完成"。

已修：`LightRAGClient._is_active()` 同时判
`busy / scanning / scanning_exclusive / destructive_busy / pending_enqueues`，
且 `--watch` 要求连续两次空闲才退出（避开分类↔处理之间的空档）。

### ④ `delete_document` 是 DELETE 方法且带请求体

不是 POST。请求体：

```json
{ "doc_ids": ["doc-..."], "delete_file": false, "delete_llm_cache": false }
```

⚠️ **`delete_llm_cache` 默认就是 `false`，务必保持** ——
抽取缓存是花过钱的成果（101 章 = 55 行缓存）。删文档不会删缓存，
重灌时几乎全部命中，只花 embedding 的钱。

### ⑤ API 返回的文档状态是**小写**

`processed` / `failed` / `pending`，不是 `PROCESSED`。
回填清单时要做大小写归一（`pipeline/ingest.py --backfill` 已处理）。

### ⑥ 容器里没有 curl/wget

最终镜像阶段只装了 `gosu`/`libcairo2`，healthcheck 不能用 curl。
已改为用容器自带的 python 探活。

### ⑦ 推理型模型白烧 token（已优化）

`deepseek-flash` 是推理型模型，每次调用都会先生成 `reasoning_content`。
实体/关系抽取是**结构化 JSON 任务**，不需要思考链。

DeepSeek 支持 `thinking: {"type": "disabled"}` 关闭推理，而 LightRAG 的
OpenAI binding 恰好有 `extra_body` 字段可以透传（`binding_options.py:736` →
`lightrag_server.py:1918 kwargs.update(...)` → OpenAI SDK 的 `extra_body`）。

写法是**按角色**设环境变量：

```bash
EXTRACT_OPENAI_LLM_EXTRA_BODY='{"thinking": {"type": "disabled"}}'
KEYWORD_OPENAI_LLM_EXTRA_BODY='{"thinking": {"type": "disabled"}}'
# 回答角色保留思考以保证质量:
# QUERY_OPENAI_LLM_EXTRA_BODY='{"thinking": {"type": "disabled"}}'
```

命名规则是 `{角色}_{BINDING}_{字段}`，角色可选
`EXTRACT` / `KEYWORD` / `QUERY` / `VLM`。

**实测收益**（同一个 prompt）：

| 配置 | 耗时 | completion tokens | reasoning tokens |
|---|---|---|---|
| 不传（默认） | 2.28 s | 297 | 264 |
| **`thinking=disabled`** | **1.01 s** | **25** | **无** |
| `enabled` + `reasoning_effort=low` | 1.55 s | 178 | 143 |

**整章灌库实测**：

| | 101 章（思考开） | 102 章（思考关） |
|---|---|---|
| chunk 数 | 22 | 28 |
| 处理耗时 | ~190 s | **~73 s** |
| 每 chunk | 8.6 s | **2.6 s（3.3×）** |
| 抽出实体 / 关系 | 200 / 302 | 209 / 221 |
| 实体名质量 | — | 正常（阿尔卡纳、华尔街股灾、Megrez δ魔药书室…） |
| 问答质量 | — | 正常（4/4 回归通过） |

> 可用 `scripts/probe_llm_extra.py` 在容器内随时复验这条链路是否仍然通。
> 注意 `extra_body` 只有 **OpenAI binding** 有（Bedrock 是 `extra_fields`，
> Ollama 是 `think` 开关），换服务商要相应改写。

---

## 目录结构

```
1999RAG/
├── LightRAG/                     # 上游源码（只读，保持可 git pull）
├── corpus/                       # 语料（独立 clone，不进 git）
├── .env / .env.example           # 配置（.env 含密钥，不进 git）
├── .gitattributes                # 换行符策略（Dockerfile 续行 / CRLF 坑）
├── .gitignore
├── docker-compose.yml            # postgres + lightrag 编排
├── README.md
├── pipeline/                     # 数据管线
│   ├── chapter_index.py          #   语料目录 → state/chapter_index.json
│   ├── build_inputs.py           #   语料 → data/inputs/ + manifest
│   ├── ingest.py                 #   灌库 / 看进度 / 回填 / 冒烟测试
│   └── lib/lightrag_client.py    #   REST 客户端（纯标准库）
├── state/                        # 状态清单（进 git）
│   ├── corpus.lock.json          #   语料 commit 锁定
│   ├── chapter_index.json        #   81 章的序号/分类/标题/字节数
│   └── index_manifest.json       #   每章 sha256 + doc_id + 索引状态
├── data/                         # 运行时数据（不进 git）
│   ├── inputs/                   #   ← INPUT_DIR（81 章平铺 + __parsed__）
│   ├── rag_storage/              #   ← WORKING_DIR
│   ├── prompts/entity_type/      #   实体类型定义
│   ├── pgdata/                   #   PostgreSQL 数据目录
│   └── backups/
├── deploy/
│   ├── initdb/01-vector.sql      #   CREATE EXTENSION vector
│   └── Dockerfile.lightrag       #   由 build-image.ps1 生成
└── scripts/
    ├── build-image.ps1           # 构建镜像（绕开 syntax 联网问题）
    ├── up.ps1 / down.ps1         # 启停
    ├── status.ps1 / logs.ps1     # 巡检 / 日志
    └── ...
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
> 该语料曾把 1977 个单元文件重构成 82 个章节文件（见下文「布局变更熔断」）。

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
| `EMBEDDING_MODEL` | `text-embedding-v4` | |
| `EMBEDDING_DIM` | `1024` | |
| `EMBEDDING_SEND_DIM` | `true` | 百炼要显式传维度 |
| `EMBEDDING_USE_BASE64` | `false` | 百炼不支持 base64 embedding |
| `EMBEDDING_BATCH_NUM` | `10` | **百炼单次上限就是 10，填 16 会报 400** |
| `LIGHTRAG_PARSER` | `md:native-P,*:legacy-R` | 见「决策 3」 |
| `CHUNK_P_SIZE` | `2000` | |
| `EXTRACT_`/`KEYWORD_OPENAI_LLM_EXTRA_BODY` | `{"thinking":{"type":"disabled"}}` | 推理模型按角色关思考，3.3× 提速 |

> ⚠️ **Embedding 一旦灌了数据就不能改**（换模型或维度 = 重建整个索引）。
> ⚠️ 存储后端同理，有数据后不能换成别的后端。

### 2. 构建镜像并启动

```powershell
.\scripts\build-image.ps1     # 首次构建 lightrag-1999:local（含前端，约 10 分钟）
.\scripts\up.ps1              # 启动 postgres + lightrag
```

Windows 上不要直接用 `docker compose build`，原因见「环境修复记录 ③」：
BuildKit 不走 Docker Desktop 的代理，且上游 `Dockerfile` 的 `# syntax=` 指令
会触发联网拉前端镜像。`build-image.ps1` 已绕开这两点，并顺手把 24 个 `.sh`
统一转成 LF（见 ④）。

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

先只灌主线 16 章是本项目的省钱验证路径（实测约 27 分钟）。
确认验收通过后再全量，见第 6 步。

### 5. 验收（四类问题）

```powershell
python scripts/smoke_test.py            # 一次跑完四题并给出 PASS/FAIL
python scripts/smoke_test.py --only 4   # 只跑第 4 题(说话人归属, 有硬性判据)
```

| 验收点 | 期望 |
|---|---|
| 引用落到正确章节 | `references` 的 `file_path` 应是 `101-在我们的时代里.md` 这类 |
| 说话人未丢 | 第 4 题必须答出「维尔汀」 |
| 跨章汇总 | 第 2 题应调用图检索，答案跨多个剧情单元 |
| 分块真的用了 P | `data/inputs/__parsed__/*.parsed/*.blocks.jsonl` 存在且 heading 层级正确 |

### 6. 全量灌库

```powershell
python pipeline/build_inputs.py --categories mainline,activity,character,anecdote
python pipeline/ingest.py --scan
python pipeline/ingest.py --watch
python pipeline/ingest.py --backfill
```

全量 81 章实测约 112 分钟。已 PROCESSED 的章节：源文件重新铺入后
扫描会判定为 `already processed` 并再次归档，**不会重复抽取**
（`lightrag_llm_cache` 里已有缓存，重灌近乎全命中）。

---

## 增量更新（游戏发新版本时）

```powershell
python pipeline/update_index.py --check      # 上游有没有更新
python pipeline/update_index.py --plan       # 看要动哪些章(只读)
python pipeline/update_index.py --apply      # 执行
```

**三条必须"先删后传"的理由**（均已在 LightRAG 源码核实）：同名上传返回 409、
内容 hash 会被判重、`process_options`/`chunk_options` 在入队时就冻结。
脚本已封装 delete → stage → scan → backfill → 更新 corpus.lock.json 全流程，
且删除时保持 `delete_llm_cache=False`，**未被改动的 chunk 重灌时直接命中缓存**。

### ⚠️ 布局变更熔断（这个语料真的发生过）

本语料的目录布局**结构性变过**：

| tag | 简中布局 | 文件数 |
|---|---|---|
| v1.0.0 / v1.0.1 | 无 `story_reader_linked/zh-CN` | 0 |
| **v1.1.0** | `activity/chapter_11101/1110101-xxx.md` + `.json` | **1977** |
| **v1.2.0**（当前） | `activity/11101-xxx.md` | **82** |

也就是说从 v1.1.0 到 v1.2.0，维护者把"每章拆成多个剧情单元文件"
改成了"整个活动一个文件"。**朴素的 diff 增量会变成"删 81 加 1977"的灾难。**

所以 `update_index.py`：
- 只认当前命名规范 `分类/数字-标题.md`
- 文件数变化超过 30%（且 >10）或新版本匹配数为 0 时**直接熔断**（退出码 2），
  提示改走全量重建，需 `--force-layout` 才强行增量

## 后续可做

- **上服务器**：启用 `deploy/nginx/` + 配 TLS；迁移只需 `pg_dump` + `data/inputs` + `state/`
- **接上 UI**：直接用 LightRAG 原生 `/workspace`（问答）与 `/webui`（管理），
  或按需自建前端
- **调参**：`CHUNK_TOP_K`（整体梗概类问题调大）、`TOP_K`、`MIN_RERANK_SCORE`
- **按角色继续省钱**：`.env` 里已给 `QUERY_OPENAI_LLM_EXTRA_BODY` 留了注释，
  想换更快的回答可以打开（会略降归纳质量）

---

## 版权

剧情文本版权归其权利人所有。本仓库**不含**语料原文 —— 语料独立 clone 且被
`.gitignore` 排除，仅用于本地个人检索。
