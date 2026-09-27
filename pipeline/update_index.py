#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
update_index.py — 语料更新后的增量重索引

场景: 上游 compendium 发新版本（新增活动、修错字、补漏章），
      只把**真正变动过的章节**重新灌一遍，不动其余部分。

用法:
    python pipeline/update_index.py --check               # 上游有没有更新
    python pipeline/update_index.py --plan                # 要动哪些章(只读)
    python pipeline/update_index.py --plan --to v1.3.0    # 指定目标 tag/commit
    python pipeline/update_index.py --apply               # 执行增量更新

## 为什么必须"先删后传"

三条 LightRAG 约束叠加（均已在源码核实）:
  1. 同名文件上传返回 409(输入目录或 doc_status 已有同规范名文档)
  2. 内容 hash 相同会被判重
  3. 引擎 / process_options / chunk_options 在入队时就冻结进 doc_status,
     改配置对已有文档不生效 —— 要换内容只能 delete + 重传

删除语义是干净的: delete_document 触发 _purge_doc_chunks_and_kg,
失去全部来源的实体/关系直接从图谱删除, 仍有其它文档贡献的用剩余 chunk 重建。
且 delete_llm_cache=False 保住抽取缓存 —— 未改动的 chunk 重灌时直接命中。

## 为什么按 git blob 比对

清洗结果依赖章节序号/版本等元数据（来自当时的 README 解析），
"重新清洗再比内容"复现有风险。git blob SHA 是权威的：
同一个 blob 就是同一份源文件。

## 布局变更熔断（重要）

本语料的目录布局**结构性变过**:

    v1.1.0  activity/chapter_11101/1110101-xxx.md   (每章拆成多个剧情单元, 1977 个文件)
    v1.2.0  activity/11101-xxx.md                   (整个活动一个文件,   82 个文件)

朴素的 diff 增量会因此变成"删 81 加 1977"的灾难。
所以这里只认当前命名规范（`分类/数字-标题.md`），并对文件数剧变直接熔断，
要求人工确认后走全量重建。
"""
from __future__ import annotations

import argparse
import json
import io
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "Reverse1999-Story-Compendium"
LOCK = ROOT / "state" / "corpus.lock.json"
MANIFEST = ROOT / "state" / "index_manifest.json"
ZH_SUBPATH = "readable/story_reader_linked/zh-CN"

# 当前语料的章节命名规范: 分类/数字-标题.md
CHAPTER_RE = re.compile(r"^(mainline|activity|character|anecdote)[/\\](\d+)-(?:.+)\.md$")

sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "pipeline" / "lib"))
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-C", str(CORPUS), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败:\n{r.stderr.strip()}")
    return r.stdout.strip()


def list_chapters(ref: str) -> dict[str, str]:
    """返回 {相对路径(反斜杠): blob SHA}，只保留符合当前命名规范的章节。

    ⚠️ `-z` 不能去掉：git 默认 `core.quotePath=true`，会把**非 ASCII 路径**输出成
    `"activity/11101-\\351\\233\\267..."`（加双引号 + 八进制转义），于是下面那句
    `path.startswith(prefix)` 全线落空 —— 实测对锁定版本 f6e18439 返回 **0 条**（应为 81 条），
    后果是 `compute_plan` 判出 `deleted: 81`、`layout_guard` 误报「上游改了目录布局，请全量重建」。
    与 `build_inputs.git_blob_map()` 是同一处坑（AGENTS §6 问题 1，2026-09-27 一并修）。
    """
    raw = git("ls-tree", "-r", "-z", ref, "--", ZH_SUBPATH)
    out: dict[str, str] = {}
    prefix = ZH_SUBPATH + "/"
    # `-z` 的分隔符是 NUL，每条记录形如 `<mode> SP <type> SP <object>\t<path>`
    for rec in raw.split("\0"):
        if not rec:
            continue
        meta, _sep, path = rec.partition("\t")
        fields = meta.split()
        if len(fields) < 3 or not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        if CHAPTER_RE.match(rel):
            out[rel.replace("/", "\\")] = fields[2]
    return out


def chapter_no(rel: str) -> str:
    return Path(rel).name.split("-")[0]


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def compute_plan(old_map: dict[str, str], new_map: dict[str, str]) -> dict[str, list[str]]:
    """按路径+blob 分类变更。"""
    added = sorted(r for r in new_map if r not in old_map)
    deleted = sorted(r for r in old_map if r not in new_map)
    modified = sorted(
        r for r in new_map
        if r in old_map and old_map[r] and new_map[r] != old_map[r]
    )
    return {"added": added, "modified": modified, "deleted": deleted}


def layout_guard(old_map: dict[str, str], new_map: dict[str, str]) -> str | None:
    """检测布局/命名规范变更，返回熔断原因(字符串)或 None。"""
    n_old, n_new = len(old_map), len(new_map)
    if n_new == 0 and n_old > 0:
        return (f"目标版本里没有任何文件符合当前章节命名规范 "
                f"({CHAPTER_RE.pattern})，共 0 个。\n"
                f"      上游很可能改了目录布局 —— 本次锁定版本有 {n_old} 章。")
    if n_old == 0:
        return None
    delta = abs(n_new - n_old)
    if delta > max(10, int(0.30 * n_old)):
        return (f"章节文件数剧变: {n_old} → {n_new} (差 {delta})，超过 30% 阈值。\n"
                f"      这通常意味着上游重构了目录布局，增量更新会造成大量误删。\n"
                f"      v1.1.0→v1.2.0 就发生过一次 (1977 个单元文件 → 82 个章节文件)。")
    return None


def print_plan(plan: dict, old: str, new: str) -> int:
    total = sum(len(v) for v in plan.values())
    print(f"\n语料变更 {old[:8]} → {new[:8]}    共 {total} 个章节变动")
    if total == 0:
        print("  章节内容没有变化。")
        return 0
    for kind, label in (("added", "新增"), ("modified", "修改"), ("deleted", "删除")):
        items = plan[kind]
        if not items:
            continue
        print(f"\n  [{label}] {len(items)} 个")
        for it in items[:40]:
            print(f"    {chapter_no(it):>7}  {Path(it).name}")
        if len(items) > 40:
            print(f"    ... 还有 {len(items) - 40} 个")
    return total


def r_client():
    from lightrag_client import LightRAGClient  # noqa
    env = {}
    ep = ROOT / ".env"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return LightRAGClient(
        base_url=f"http://localhost:{env.get('PORT', '9621')}",
        api_key=env.get("LIGHTRAG_API_KEY", ""),
        timeout=300,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="语料更新后的增量重索引",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="fetch 上游并报告有无更新")
    g.add_argument("--plan", action="store_true", help="只打印要动哪些章(只读)")
    g.add_argument("--apply", action="store_true", help="执行增量更新")
    ap.add_argument("--to", default="", help="目标 tag/commit(默认 origin 默认分支最新)")
    ap.add_argument("--no-fetch", action="store_true", help="跳过 git fetch(离线)")
    ap.add_argument("--force-layout", action="store_true",
                    help="无视布局熔断强行增量(危险, 通常你该走全量重建)")
    args = ap.parse_args()

    if not CORPUS.exists():
        print(f"[x] 找不到语料仓库: {CORPUS}")
        return 1

    lock = load_json(LOCK)
    if not lock:
        print("[x] 缺少 state/corpus.lock.json，先跑 pipeline/chapter_index.py")
        return 1
    man = load_json(MANIFEST) or {"docs": {}}
    docs = man.get("docs", {})

    old = lock["commit"]
    print(f"当前锁定语料版本: {old[:8]}  ({lock.get('describe', '')})")

    if not args.no_fetch:
        print("-> git fetch --tags ...")
        git("fetch", "--tags", "--prune", "origin")

    if args.to:
        new = git("rev-parse", args.to)
    else:
        new = ""
        for ref in ("origin/HEAD", "origin/main", "origin/master"):
            r = git("rev-parse", ref, check=False)
            if r:
                new = r
                break
        if not new:
            print("[x] 无法确定上游默认分支，请用 --to 指定")
            return 1

    print(f"目标版本:         {new[:8]}")
    if new == old:
        print("\n=> 无更新。")
        return 0

    # 旧的: 以清单里记录为准(它反映的是"实际索引了什么")
    old_map = {
        rec["source_rel"]: (rec.get("source_blob") or "")
        for rec in docs.values() if rec.get("source_rel")
    }
    new_map = list_chapters(new)
    print(f"章节数: 清单 {len(old_map)}  →  目标版本 {len(new_map)}")

    reason = layout_guard(old_map, new_map)
    if reason and not args.force_layout:
        print(f"\n[熔断] {reason}")
        print("\n  建议改走全量重建:")
        print("    python pipeline/update_index.py --apply --to "
              f"{new[:12]} --force-layout   # 若你确认要增量")
        print("    (全量: 清空索引 → 重跑 chapter_index/build_inputs/scan/backfill)")
        return 2

    plan = compute_plan(old_map, new_map)
    total = print_plan(plan, old, new)

    if args.check or args.plan:
        if total:
            print(f"\n执行: python pipeline/update_index.py --apply --to {new[:12]}")
        return 0

    # ------------------------------------------------------------- apply
    if total == 0:
        print("\n章节无变化, 只更新锁定版本号。")
        lock.update({"commit": new, "commit_short": new[:8],
                     "checked_at": datetime.now(timezone.utc).isoformat()})
        LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    print(f"\n=== 开始增量更新 ({total} 个章节) ===")

    print(f"-> 切换语料工作区到 {new[:8]}")
    git("checkout", "--detach", new)

    print("-> 重建章节索引")
    subprocess.run([sys.executable, str(ROOT / "pipeline" / "chapter_index.py")], check=True)
    print("-> 重新清洗(不铺入)并刷新清单")
    subprocess.run([sys.executable, str(ROOT / "pipeline" / "build_inputs.py"),
                    "--categories", "all", "--no-stage"], check=True)

    cli = r_client()

    # 删: 修改过的 + 删除掉的
    del_ids, del_names = [], []
    for rel in plan["modified"] + plan["deleted"]:
        rec = docs.get(Path(rel).name)
        if rec and rec.get("lightrag_doc_id"):
            del_ids.append(rec["lightrag_doc_id"])
            del_names.append(Path(rel).name)

    if del_ids:
        print(f"-> 删除 {len(del_ids)} 个已索引文档(保留抽取缓存)")
        for i in range(0, len(del_ids), 20):
            try:
                cli.delete_document(del_ids[i:i + 20], delete_file=False,
                                    delete_llm_cache=False)
            except Exception as e:
                print(f"   [warn] 删除失败: {e}")
        cli.wait_for_idle(timeout=1800)
    else:
        print("-> 无需删除(变动章节此前未索引)")

    # 加: 铺入 新增 + 修改, 然后扫描
    add_mod = plan["added"] + plan["modified"]
    if add_mod:
        nos = ",".join(sorted(chapter_no(x) for x in add_mod))
        print(f"-> 铺入 {len(add_mod)} 个章节: {nos}")
        subprocess.run([sys.executable, str(ROOT / "pipeline" / "build_inputs.py"),
                        "--categories", "all", "--chapters", nos], check=True)
        print("-> 触发扫描")
        r = cli.scan()
        print(f"   {r.get('status')}  track={r.get('track_id')}")
        print("-> 等待管线跑完(可能较久) ...")
        cli.wait_for_idle(
            timeout=14400,
            on_tick=lambda st, t: print(f"   [{int(t):>6}s] "
                                        f"{str(st.get('latest_message',''))[:100]}"))
    else:
        print("-> 只有删除, 无新增/修改")

    print("-> 回填清单")
    subprocess.run([sys.executable, str(ROOT / "pipeline" / "ingest.py"), "--backfill"],
                   check=True)

    lock.update({
        "commit": new,
        "commit_short": new[:8],
        "describe": git("describe", "--tags", "--always", check=False),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[ok] 增量更新完成, 语料已锁定到 {new[:8]}")
    print(f"     提交状态清单: git add state/ && git commit -m "
          f"'index: update corpus to {new[:8]}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
