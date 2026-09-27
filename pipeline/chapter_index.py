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
    source_rel / filename / episodes / trails / version / version_source

version 的解析顺序（见 resolve_version）:
    1. metadata          —— corpus/exports/chapter_metadata.json 的字段，最权威
                           但按标题 join，81 章只覆盖 25 章
    2. 主线对照表        —— MAINLINE_VERSION，补 metadata 缺失的主线/特别篇
                           （灰机 wiki 逐章实测 5 章）
    3. 主线附属          —— 同表，但依据只是"附属关系 + 阅读顺序"（313 船喻，1 章）。
                           wiki 与 metadata 都查不到它，故单独记 mainline_attached，
                           **不要**混进上面那 5 章的 wiki 档
    4. 编号规则          —— 活动/角色/轶事的章节号前两位即版本
                           活动 15/15 已验证；角色/轶事无权威字段可校验，置信度较低
    version_source 字段记录每章来自哪一档，便于按可信度筛选/复核（AGENTS §3）。
"""
from __future__ import annotations

import json
import io
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- 路径常量
ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "Reverse1999-Story-Compendium"
ZH_DIR = CORPUS / "readable" / "story_reader_linked" / "zh-CN"
INDEX_MD = ZH_DIR / "README.md"
CHAPTER_META = CORPUS / "exports" / "chapter_metadata.json"
OUT = ROOT / "state" / "chapter_index.json"

# 分类显示名（用于元数据注释与文档）
# 注意: build_inputs.py 会拼成 f"{label}剧情", 所以这里不要自带「剧情」后缀,
# 否则角色分类会渲染成「角色剧情剧情」。
CATEGORY_LABEL = {
    "mainline": "主线",
    "activity": "活动",
    "character": "角色",
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


# ---------------------------------------------------------------- 版本解析
# 主线章节号 101-114 是「顺序编号」(第1章…第14章)，与游戏版本号之间
# **没有算术关系**。反例: 105 是 1.4，而按前两位派生会得到 1.0。
# 所以主线必须用显式对照表；编号规则只适用于活动/角色/轶事。
#
# 来源: 灰机 wiki (res1999.huijiwiki.com) 各主线章节页的固定句式
#       「<标题>是 X.Y版本 的主线剧情活动。」
#       交叉验证 1: wikiru (reverse1999.wikiru.jp)「Ver.3.7 = 13th他者の哀しみ」
#       交叉验证 2: exports/chapter_metadata.json 已有字段全部吻合
#                   (107=1.9, 108=2.2, 110=2.8 三处独立互证)
# 最后核实: 2026-09-26
MAINLINE_VERSION = {
    "101": "1.0",   # 101-104 一次性在 1.0 上线（序章 + 第1-3章）
    "102": "1.0",
    "103": "1.0",
    "104": "1.0",
    "105": "1.4",
    "310": "1.4",   # 特别篇《星》，ordinal=5SP，紧接第5章，版本与 105 同
    "106": "1.7",
    "107": "1.9",
    "108": "2.2",
    "109": "2.6",
    "110": "2.8",
    "111": "3.0",   # 3.0 系列开篇
    "112": "3.3",
    "113": "3.7",
    "114": "4.0",
    # 313 特别篇《船喻》：语料阅读顺序在 114《应门者》(4.0) 之后（order=16）。
    # 2026-09-27 经用户确认它是「与 星 同类的主线附属章节」，据此记 4.0。
    # ⚠️ 依据与上表其它行**不同档**：灰机 wiki 无条目页(404)、无「X.Y版本」句式、
    #    chapter_metadata.json 247 条里查无 313 —— 唯一依据是「附属关系 + 阅读顺序」。
    #    复核证据（2026-09-27）：wiki 数据页 `小径/船喻`（200）内嵌全章节阅读顺序表，
    #    序列结尾为 `… 聚合浪潮 → 重燃！流金之海 → 应门者 → 船喻`；该页**不含版本字样**。
    #    所以来源标成 mainline_attached，而不是 wiki（见 AGENTS §3 的可信度分档）。
    "313": "4.0",
    # 注: 31X 是"特别篇"编号（310=星 的 ordinal 为 5SP，跟随第5章）。
    #     313 的 31 与主线第 13 章同形，但语料已明确它排在 114 之后，
    #     故不能套用"跟随第 X 章"的读法反推版本。
}

# 在 MAINLINE_VERSION 里、但依据是「附属关系 / 阅读顺序」而非 wiki 版本句式的章号。
# 单独列出来是为了让 version_source 如实反映可信度（AGENTS §3 按档筛选），
# 而不是把"推断值"混进 wiki 实测那一档。
MAINLINE_ATTACHED = {"313"}

# 活动 / 角色 / 轶事的章节号前两位编码版本：20101 -> 2.0，1901 -> 1.9，
# 305101 -> 3.0。已验证：活动章节 15/15 与权威字段全部吻合。
NUMBER_RULE_CATEGORIES = {"activity", "character", "anecdote"}


def derive_version(chapter_no: str, category: str) -> str | None:
    """按章节号前两位派生版本号（仅活动/角色/轶事）。"""
    if category not in NUMBER_RULE_CATEGORIES:
        return None
    if not chapter_no or len(chapter_no) < 3 or not chapter_no[:2].isdigit():
        return None
    return f"{chapter_no[0]}.{chapter_no[1]}"


def resolve_version(ch: dict, meta: dict | None) -> tuple[str | None, str | None]:
    """按可信度依次解析版本，并返回来源以便追溯。

    1. metadata          —— 游戏自身导出字段，最权威
    2. wiki              —— 灰机 wiki 逐章实测，补 metadata 缺失的主线/特别篇
    3. mainline_attached —— 主线附属章节：只由"附属关系 + 阅读顺序"定版，
                            来源仍是 MAINLINE_VERSION 表，但依据弱于 wiki 实测（见 AGENTS §3）
    4. number_rule       —— 仅活动/角色/轶事
    """
    if meta and meta.get("version"):
        return meta["version"], "metadata"
    if ch["chapter_no"] in MAINLINE_VERSION:
        source = "mainline_attached" if ch["chapter_no"] in MAINLINE_ATTACHED else "wiki"
        return MAINLINE_VERSION[ch["chapter_no"]], source
    derived = derive_version(ch["chapter_no"], ch["category"])
    if derived:
        return derived, "number_rule"
    return None, None


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

    # 校验源文件存在 + 解析 version
    missing: list[str] = []
    by_source: dict[str, int] = {}
    conflicts: list[str] = []
    for ch in chapters:
        src = ZH_DIR / ch["source_rel"]
        ch["exists"] = src.exists()
        ch["bytes"] = src.stat().st_size if src.exists() else 0
        if not src.exists():
            missing.append(ch["source_rel"])

        v = versions.get(ch["title"])
        ch["ordinal"] = v["ordinal"] if v else None

        ch["version"], ch["version_source"] = resolve_version(ch, v)
        key = ch["version_source"] or "unresolved"
        by_source[key] = by_source.get(key, 0) + 1

        # 交叉校验：主线对照表必须与 metadata 字段一致，冲突要暴露而不是静默取一个
        table = MAINLINE_VERSION.get(ch["chapter_no"])
        if table and v and v.get("version") and v["version"] != table:
            conflicts.append(f"{ch['chapter_no']} {ch['title']}: "
                             f"metadata={v['version']} vs 对照表={table}")

    if missing:
        print(f"  [warn] {len(missing)} 个源文件不存在:")
        for m in missing[:10]:
            print(f"         {m}")

    if conflicts:
        print(f"  [warn] {len(conflicts)} 处版本冲突（metadata vs 主线对照表）:")
        for c in conflicts:
            print(f"         {c}")

    resolved = len(chapters) - by_source.get("unresolved", 0)
    print(f"  版本解析: {resolved}/{len(chapters)} 章已确定")
    for src_name, label in (("metadata", "metadata 字段"),
                            ("wiki", "主线对照表(灰机 wiki 实测)"),
                            ("mainline_attached", "主线附属(依附属关系推断)"),
                            ("number_rule", "章节号编号规则"),
                            ("unresolved", "未确定")):
        if by_source.get(src_name):
            print(f"    {label:<26} {by_source[src_name]:>3} 章")
    for c in chapters:
        if not c["version"]:
            print(f"    [未确定] {c['chapter_no']:>6} {c['title']} ({c['category']})")

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
