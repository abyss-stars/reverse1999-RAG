#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_inputs.py — 语料 → LightRAG INPUT_DIR

把 corpus/Reverse1999-Story-Compendium 的简体中文章节整理成 LightRAG 可索引的
Markdown，写入 data/inputs/ 并生成 state/index_manifest.json。

设计要点(已核实 LightRAG 源码):
  * INPUT_DIR 必须是【扁平】的
      document_routes.py:6222  "Delete only files in the current directory,
                                preserve files in subdirectories"
      delete_file_variants_by_file_path() 只遍历 input_dir 与 input_dir/__parsed__
      文档身份由【basename】决定(source_file == file_path.name)
    → 所以 81 章 .md 直接平铺在 data/inputs/ 下, 不建子目录。
      前缀已验证全局唯一, basename 不会冲突。

  * 一章一个文件 = LightRAG 的增量/删除/查重粒度

清洗步骤(可关):
  1. 去掉 <!-- reading-navigation:start --> … end 导航块
  2. 去掉 "## 目录" 章节(纯导航, 会产生无用 chunk)
  3. 去掉 <a id="episode-xxxxx"></a> 锚点
  4. 在 H1 后插入一行可见元数据(分类/序号/版本), 便于回答时感知语境
  5. 折叠 3+ 连续空行

输出:
  data/cleaned/                    全部 81 章的清洗结果（暂存区，不进 git）
  data/inputs/<原文件名>.md        实际喂给 LightRAG 的那部分（= INPUT_DIR）
  state/index_manifest.json        全部 81 章的 sha256 / 分类 / 序号 / staged 标记

为什么分两层:
  INPUT_DIR 必须是扁平的且只放"现在要灌的"文件。把清洗结果先落到
  data/cleaned/，再由 --categories 决定往 data/inputs/ 放哪些，
  以后加灌其余分类只是改参数，不必重跑清洗、也不会重复计费。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "Reverse1999-Story-Compendium"
ZH_DIR = CORPUS / "readable" / "story_reader_linked" / "zh-CN"
CLEANED = ROOT / "data" / "cleaned"
INPUTS = ROOT / "data" / "inputs"
STATE = ROOT / "state"
CHAPTER_INDEX = STATE / "chapter_index.json"
MANIFEST = STATE / "index_manifest.json"

ALL_CATEGORIES = ["mainline", "activity", "character", "anecdote"]

# ---------------------------------------------------------------- 清洗规则
NAV_BLOCK_RE = re.compile(
    r"<!--\s*reading-navigation:start\s*-->.*?<!--\s*reading-navigation:end\s*-->",
    re.DOTALL,
)
# "## 目录" 到下一个 --- 分隔线（目录表自身以 --- 结尾）
TOC_RE = re.compile(r"^##\s*目录\s*$.*?^---\s*$", re.DOTALL | re.MULTILINE)
ANCHOR_RE = re.compile(r"^\s*<a\s+id=\"[^\"]+\"></a>\s*$", re.MULTILINE)
BLANK_RE = re.compile(r"\n{4,}")


def clean_markdown(text: str) -> str:
    text = NAV_BLOCK_RE.sub("", text)
    text = TOC_RE.sub("", text)
    text = ANCHOR_RE.sub("", text)
    text = BLANK_RE.sub("\n\n\n", text)
    return text.strip() + "\n"


def inject_meta(text: str, ch: dict) -> str:
    """在 H1 之后插入一行可见元数据。

    这行会随首个 chunk 一起进索引，让 LLM 知道自己在读哪一类、哪一章的剧情。
    ordinal 字段是游戏自带的 "1ST"/"4TH" 写法，与阅读顺序重复且显示别扭，故不采用。
    """
    parts = [f"{ch['category_label']}剧情", f"章节 {ch['chapter_no']}"]
    parts.append(f"阅读顺序 {ch['order']}")
    if ch.get("version"):
        parts.append(f"游戏版本 {ch['version']}")
    if ch.get("episodes") is not None:
        parts.append(f"{ch['episodes']} 个剧情单元")
    if ch.get("trails"):
        parts.append(f"{ch['trails']} 条小径")
    line = "> " + " · ".join(parts)

    lines = text.split("\n")
    # 找第一行 H1
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            # 已有同款元数据行则跳过
            if i + 2 < len(lines) and lines[i + 2].startswith("> "):
                return text
            lines.insert(i + 2, line)          # H1 后空一行再插入
            return "\n".join(lines)
    return f"{line}\n\n{text}"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def git_blob_map(commit: str) -> dict[str, str]:
    """一次 git ls-tree 拿到 {相对路径: blob SHA}，路径用反斜杠与 chapter_index 对齐。

    增量比较用 git 自己的 blob SHA，而不是"重新清洗一遍再比内容" ——
    清洗结果依赖章节序号/版本等元数据（来自当时的 README 解析），复现有风险；
    blob SHA 是权威且精确的：同一个 blob 就是同一份源文件。
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(CORPUS), "ls-tree", "-r", commit, "--",
             "readable/story_reader_linked/zh-CN"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
    except Exception:
        return {}
    if r.returncode != 0:
        return {}

    prefix = "readable/story_reader_linked/zh-CN/"
    m: dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        meta, path = parts
        fields = meta.split()
        if len(fields) < 3 or not path.startswith(prefix):
            continue
        m[path[len(prefix):].replace("/", "\\")] = fields[2]
    return m


def main() -> int:
    ap = argparse.ArgumentParser(
        description="语料 → 清洗 → 暂存 → 按分类铺进 INPUT_DIR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="例:\n"
               "  python pipeline/build_inputs.py --categories mainline\n"
               "  python pipeline/build_inputs.py --categories mainline,activity\n"
               "  python pipeline/build_inputs.py --categories all",
    )
    ap.add_argument("--categories", default="mainline",
                    help=f"要铺进 INPUT_DIR 的分类, 逗号分隔; all = {'/'.join(ALL_CATEGORIES)}"
                         f"  (默认: mainline)")
    ap.add_argument("--chapters", default="",
                    help="只铺这些章号, 逗号分隔 (如 101 或 101,102); 留空=不限。"
                         "用于单章冒烟测试, 避免一次烧掉全部抽取费用")
    ap.add_argument("--skip-indexed", action="store_true",
                    help="跳过清单里已是 PROCESSED 的章节(续灌时用, 避免白扫一遍)")
    ap.add_argument("--no-clean", action="store_true", help="不清洗, 原样复制")
    ap.add_argument("--no-meta", action="store_true", help="不注入元数据行")
    ap.add_argument("--no-stage", action="store_true",
                    help="只更新 data/cleaned/ 与清单, 不动 INPUT_DIR")
    args = ap.parse_args()

    if not CHAPTER_INDEX.exists():
        print(f"[ERROR] 找不到 {CHAPTER_INDEX.relative_to(ROOT)}")
        print("        请先运行: python pipeline/chapter_index.py")
        return 1

    # 解析分类
    if args.categories.strip().lower() == "all":
        wanted = set(ALL_CATEGORIES)
    else:
        wanted = {c.strip() for c in args.categories.split(",") if c.strip()}
    unknown = wanted - set(ALL_CATEGORIES)
    if unknown:
        print(f"[ERROR] 未知分类: {sorted(unknown)}")
        print(f"        可用: {ALL_CATEGORIES} 或 all")
        return 1

    # 可选的章号白名单（单章冒烟测试用，避免一次烧掉全部抽取费用）
    only_chapters = {c.strip() for c in args.chapters.split(",") if c.strip()}
    if only_chapters:
        print(f"仅铺这些章号: {sorted(only_chapters)}")

    idx = json.loads(CHAPTER_INDEX.read_text(encoding="utf-8"))
    chapters = idx["chapters"]
    corpus_commit = idx["generated_from"]["commit"]
    print(f"章节索引: {len(chapters)} 章 (语料 {corpus_commit[:8]})")
    print(f"本次铺入 INPUT_DIR 的分类: {sorted(wanted)}")

    # 源文件的 git blob SHA —— 增量更新靠它精确判断"哪些章真的变了"
    blobs = git_blob_map(corpus_commit)
    if blobs:
        print(f"  取到 {len(blobs)} 个源文件 blob SHA")
    else:
        print("  [warn] 取不到 blob SHA，增量更新会退化为按内容比对")

    CLEANED.mkdir(parents=True, exist_ok=True)
    INPUTS.mkdir(parents=True, exist_ok=True)

    # ---- 1) 清洗全部章节 → data/cleaned/ ----
    docs: dict[str, dict] = {}
    total_in = total_out = 0
    for ch in chapters:
        src = ZH_DIR / ch["source_rel"]
        if not src.exists():
            print(f"  [skip] 源文件缺失: {ch['source_rel']}")
            continue

        raw = src.read_text(encoding="utf-8")
        out_text = raw if args.no_clean else clean_markdown(raw)
        if not args.no_meta:
            out_text = inject_meta(out_text, ch)

        dst = CLEANED / ch["filename"]
        dst.write_text(out_text, encoding="utf-8")

        total_in += src.stat().st_size
        total_out += dst.stat().st_size

        docs[ch["filename"]] = {
            "chapter_no": ch["chapter_no"],
            "title": ch["title"],
            "category": ch["category"],
            "order": ch["order"],
            "version": ch.get("version"),
            "episodes": ch.get("episodes"),
            "trails": ch.get("trails"),
            "sha256": sha256_file(dst),
            "bytes": dst.stat().st_size,
            "source_rel": ch["source_rel"],
            "source_blob": blobs.get(ch["source_rel"]),
            "staged": False,
            # 以下字段由 ingest.py --backfill 回填
            "lightrag_doc_id": None,
            "status": "NOT_INDEXED",
            "chunks_count": None,
            "indexed_at": None,
        }

    # ---- 2) 合并旧清单里已索引章节的回填字段(按 sha256 相同才继承) ----
    if MANIFEST.exists():
        try:
            prev = json.loads(MANIFEST.read_text(encoding="utf-8"))
            inherited = 0
            for name, rec in docs.items():
                p = prev.get("docs", {}).get(name)
                if p and p.get("sha256") == rec["sha256"]:
                    for k in ("lightrag_doc_id", "status", "chunks_count", "indexed_at"):
                        rec[k] = p.get(k)
                    inherited += 1
            if inherited:
                print(f"  继承旧清单里 {inherited} 章的索引状态(内容未变)")
        except Exception as e:
            print(f"  [warn] 合并旧 manifest 失败: {e}")

    # ---- 3) 按分类铺进 INPUT_DIR ----
    staged = 0
    if not args.no_stage:
        old = [p for p in INPUTS.glob("*.md") if p.is_file()]
        for p in old:
            p.unlink()
        if old:
            print(f"  已清空 INPUT_DIR 顶层 {len(old)} 个旧 .md（__parsed__ 保留）")

        for name, rec in docs.items():
            if rec["category"] not in wanted:
                continue
            if only_chapters and rec["chapter_no"] not in only_chapters:
                continue
            # 续灌: 已索引的章节不必重新铺入(铺了也会被扫描判定为 already processed
            # 再归档一次, 只是噪音)
            if args.skip_indexed and rec.get("status") == "PROCESSED":
                continue
            shutil.copy2(CLEANED / name, INPUTS / name)
            rec["staged"] = True
            staged += 1

    # ---- 4) 写清单 ----
    manifest = {
        "format": "1999rag-index-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lang": "zh-CN",
        "corpus": idx["generated_from"],
        "config_fingerprint": {
            # 与 .env 对齐; 改动这些必须重建索引
            "parser": "md:native-P,*:legacy-R",
            "chunk_p_size": 2000,
            "embedding_model": "text-embedding-v4",
            "embedding_dim": 1024,
            "clean": not args.no_clean,
            "meta_line": not args.no_meta,
        },
        "staged_categories": sorted(wanted),
        "counts": {
            "docs": len(docs),
            "staged": staged,
            "by_category": {
                c: sum(1 for r in docs.values() if r["category"] == c)
                for c in ALL_CATEGORIES if any(r["category"] == c for r in docs.values())
            },
        },
        "docs": docs,
    }

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n清洗: {len(docs)} 章 → {CLEANED.relative_to(ROOT)}\\")
    print(f"  原始 {total_in / 1024 / 1024:.2f} MB → 清洗后 {total_out / 1024 / 1024:.2f} MB")
    if not args.no_stage:
        print(f"铺入: {staged} 章 → {INPUTS.relative_to(ROOT)}\\")
    print(f"清单: {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
