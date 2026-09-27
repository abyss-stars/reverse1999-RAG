"""薄服务层的配置：从仓库根的 .env 取 LightRAG 与 LLM 的连接信息。

刻意**不引第三方 dotenv**：这个仓库的 .env 是简单 KEY=VALUE，手写解析够用，
也避免给服务层加依赖。
"""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def _load_env(path: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


_FILE_ENV = _load_env(ENV_PATH)


def get(key: str, default: str = "") -> str:
    """优先环境变量，其次 .env 文件（容器里 .env 会被 compose 注入成环境变量）。"""
    return os.environ.get(key) or _FILE_ENV.get(key) or default


# —— LightRAG 后端 ——
LIGHTRAG_BASE = get("LIGHTRAG_BASE", f"http://localhost:{get('PORT', '9621')}")
LIGHTRAG_API_KEY = get("LIGHTRAG_API_KEY", "")

# —— 生成用的 LLM（与 LightRAG 的 QUERY 角色同一家，但我们自己发请求）——
LLM_BINDING_HOST = get("LLM_BINDING_HOST", "https://api.deepseek.com/v1").rstrip("/")
LLM_API_KEY = get("LLM_BINDING_API_KEY", "")
LLM_MODEL = get("QUERY_LLM_MODEL") or get("LLM_MODEL", "deepseek-flash")
LLM_TIMEOUT = float(get("LLM_TIMEOUT", "180"))

# —— 薄服务层自己 ——
# 端口**不在这里配**：监听端口由 `uvicorn --port` 决定（见 .vscode/tasks.json ②、
# server/README.md）。曾有一个 SANDBOX_PORT 常量，全仓无人读取、改了也不生效，已删。
# 允许把 LightRAG 的 KG 段保留下来（默认在启用过滤时丢弃，理由见 filtering.py）
KEEP_KG_DEFAULT = get("SANDBOX_KEEP_KG", "false").lower() in ("1", "true", "yes")

# 前端构建产物（生产形态由本服务一并托管，见 server/README.md）
WEB_DIST = ROOT / "web" / "dist"
CHAPTER_INDEX = ROOT / "state" / "chapter_index.json"
INDEX_MANIFEST = ROOT / "state" / "index_manifest.json"
PRESET_MODULE_DIR = ROOT / "pipeline" / "lib"
