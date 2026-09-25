#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
chapter_index.py — 解析语料目录，生成 state/chapter_index.json

语料真实结构（已核实 commit f6e18439）:
    readable/story_reader_linked/zh-CN/
        README.md          ← 权威目录（含阅读顺序）
        mainline/   16 章
        activity/   23 章
        character/  20 章
        anecdote/   22 章

README 条目格式:
    - [101 · 在我们的时代里](mainline/101-%E5%9C%A8....md) — 16 个剧情单元，23 条小径

输出: state/chapter_index.json
    每章包含 order(阅读顺序) / chapter_no(数字前缀) / title / category /
    source_rel / filename / episodes / trails / version
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- 路径常量
ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "Reverse1999-Story-Compendium"
ZH_DIR = CORPUS / "readable" / "story_reader_linked" / "zh-CN"
INDEX_MD = ZH_DIR / "README.md"
CHAPTER_META = CORPUS / "exports" / "chapter_metadata.json"
OUT = ROOT / "state" / "chapter_index.json"

# 分类显示名（用于元数据注释与文档）
CATEGORY_LABEL = {
    "mainline": "主线",
    "activity": "活动",
    "character": "角色剧情",
    "anecdote": "轶事",
}

# README 里 - [101 · 标题](path.md) — 16 个剧情单元，23 条小径
ENTRY_RE = re.compile(
    r"^-\s*\[(\d+)\s*·\s*(?P<title>.+?)\]\((?P<path>.+?\.md)\)"
    r"(?:\s*—\s*(?P<episodes>\d+)\s*个剧情单元)?"
    r"(?:，\s*(?P<trails>\d+)\s*条小径)?"
)
SECTION_RE = re.compile(r"^##\s+(?P<name>.+?)（(?P<count>\d+)\s*章）")

# 中文分类名 → 目录名
NAME_TO_CATEGORY = {
    "主线": "mainline",
    "活动剧情": "activity",
    "角色剧情": "character",
    "轶事": "anecdote",
}


def git(*args: str) -> str:
    """在语料仓库里执行 git, 失败返回空串。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(CORPUS), *args],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def load_versions() -> dict[str, dict]:
    """从 exports/chapter_metadata.json 取 version / ordinal 等补充信息。

    该文件有 247 条(含 mirror), 这里按中文名建索引, 仅作 best-effort 补充。
    """
    if not CHAPTER_META.exists():
        return {}
    try:
        data = json.loads(CHAPTER_META.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [warn] 读取 chapter_metadata.json 失败: {e}")
        return {}

    out: dict[str, dict] = {}
    for ch in data.get("chapters", []):
        name = (ch.get("name_zh_CN_archive") or "").strip()
        if not name:
            continue
        # 同一名字可能有多条(mirror), 优先保留 in_story_catalog=true 的
        prev = out.get(name)
        if prev is None or (ch.get("in_story_catalog") and not prev.get("in_story_catalog")):
            out[name] = {
                "version": ch.get("version") or None,
                "ordinal": ch.get("ordinal") or None,
                "category_raw": ch.get("category") or None,
                "in_story_catalog": bool(ch.get("in_story_catalog")),
            }
    return out


def parse_readme() -> list[dict]:
    """按 README 的章节顺序解析出全部条目。"""
    lines = INDEX_MD.read_text(encoding="utf-8").splitlines()
    cat: str | None = None
    rows: list[dict] = []
    order = 0

    for raw in lines:
        line = raw.rstrip()

        m_sec = SECTION_RE.match(line)
        if m_sec:
            name = m_sec.group("name").strip()
            cat = NAME_TO_CATEGORY.get(name)
            if cat is None:
                print(f"  [warn] 未知分类标题: {name!r} (归入 misc)")
                cat = "misc"
            continue

        m = ENTRY_RE.match(line)
        if not m or cat is None:
            continue

        order += 1
        rel = unquote(m.group("path"))
        rows.append({
            "order": order,
            "chapter_no": m.group(1),
            "title": m.group("title").strip(),
            "category": cat,
            "category_label": CATEGORY_LABEL.get(cat, cat),
            "source_rel": rel.replace("/", "\\"),
            "filename": Path(rel).name,
            "episodes": int(m.group("episodes")) if m.group("episodes") else None,
            "trails": int(m.group("trails")) if m.group("trails") else None,
        })

    return rows


def main() -> int:
    if not INDEX_MD.exists():
        print(f"[ERROR] 找不到语料目录文件: {INDEX_MD}")
        print("        请先确认语料已 clone 到 corpus/Reverse1999-Story-Compendium")
        return 1

    print(f"读取目录: {INDEX_MD.relative_to(ROOT)}")
    chapters = parse_readme()
    print(f"  解析到 {len(chapters)} 章")

    versions = load_versions()
    hit = 0

    # 校验源文件存在 + 补充 version
    missing: list[str] = []
    for ch in chapters:
        src = ZH_DIR / ch["source_rel"]
        ch["exists"] = src.exists()
        ch["bytes"] = src.stat().st_size if src.exists() else 0
        if not src.exists():
            missing.append(ch["source_rel"])

        v = versions.get(ch["title"])
        ch["version"] = v["version"] if v else None
        ch["ordinal"] = v["ordinal"] if v else None
        if v:
            hit += 1

    if missing:
        print(f"  [warn] {len(missing)} 个源文件不存在:")
        for m in missing[:10]:
            print(f"         {m}")

    print(f"  补充 version 信息: {hit}/{len(chapters)} 章命中")

    # 分类统计
    counts: dict[str, int] = {}
    for ch in chapters:
        counts[ch["category"]] = counts.get(ch["category"], 0) + 1

    payload = {
        "format": "1999rag-chapter-index-v1",
        "generated_from": {
            "repo": "https://github.com/VioletWilde/Reverse1999-Story-Compendium",
            "commit": git("rev-parse", "HEAD"),
            "describe": git("describe", "--tags", "--always"),
            "index_file": "readable/story_reader_linked/zh-CN/README.md",
            "lang": "zh-CN",
        },
        "counts": counts,
        "total": len(chapters),
        "total_bytes": sum(c["bytes"] for c in chapters),
        "chapters": chapters,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出: {OUT.relative_to(ROOT)}")
    print(f"  分类统计: {counts}")
    print(f"  语料总体积: {payload['total_bytes'] / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
