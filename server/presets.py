"""预设定义 —— 从 `pipeline/lib/query_planner.py` **导入**，不复制。

这样"预设的唯一真源"仍然是 pipeline 那个模块：网页、`preset_matrix.py`、
薄服务层看到的是同一份参数，不会出现"前端写死一套、后端改了另一套"。
"""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def _module():
    path = config.PRESET_MODULE_DIR / "query_planner.py"
    if str(config.PRESET_MODULE_DIR) not in sys.path:
        sys.path.insert(0, str(config.PRESET_MODULE_DIR))
    name = "1999rag_query_planner"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载预设模块：{path}")
    mod = importlib.util.module_from_spec(spec)
    # 必须先注册进 sys.modules 再 exec：query_planner 里用了 @dataclass，
    # 而 dataclasses 解析注解时要靠 sys.modules[cls.__module__] 取命名空间，
    # 缺了这一步会报 `'NoneType' object has no attribute '__dict__'`。
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def for_ui() -> list[dict]:
    """前端契约（与 `python pipeline/lib/query_planner.py --json` 同源同形）。"""
    return _module().for_ui()


def get_preset(name: str) -> dict | None:
    try:
        return _module().get_preset(name)
    except Exception:
        return None


def params_of(name: str) -> dict:
    """取某档的检索参数。

    ⚠️ 必须走 `for_ui()`，不要直接读 `PRESETS[name]`：
    `PRESETS` 里的参数是**平铺**在条目顶层的（`mode` / `top_k` / …），
    **没有** `params` 子字典；而 `for_ui()` 才把它们规整成 `params`。
    之前这里写成 `get_preset(name)["params"]`，取到空字典 →
    预设参数被静默丢掉、退回 naive 默认值。
    pinpoint 恰好等于那组默认值，所以只有 chain/lookup/sweep 才暴露出来。

    `enable_rerank` 只有 sweep 显式给了 false，其余缺失即视为 True。
    """
    for item in for_ui():
        if item.get("name") == name:
            params = dict(item.get("params") or {})
            params.setdefault("enable_rerank", True)
            return params
    return {}
