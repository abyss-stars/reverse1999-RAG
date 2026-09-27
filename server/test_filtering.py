"""`server/filtering.py` 的单元测试 —— 纯逻辑，不联网、不起服务。

跑法：
    python server/test_filtering.py
退出码 0 = 全过。
"""

from __future__ import annotations

import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from server.filtering import (  # noqa: E402
    SEC_CHUNKS,
    SEC_ENTITY,
    SEC_REFLIST,
    filter_references,
    prune_context,
    split_sections,
)

# Windows 控制台默认 GBK（本机实测 `sys.stdout.encoding == 'gbk'`，代码页 936），
# 打印中文会变成乱码 —— 这正是本脚本此前的输出全是乱码的原因。
#
# ⚠️ 这里**故意不抄**仓库其它脚本的 `hasattr(sys.stdout, "reconfigure")`：
# hasattr 不给静态类型检查器做收窄，Pylance/pyright 会在那一行报
# `reportAttributeAccessIssue`（`TextIO` 类型上没有 reconfigure）。
# `isinstance(..., io.TextIOWrapper)` 既能收窄（typeshed 里 TextIOWrapper 有 reconfigure），
# 运行时也更稳：stdout 被替换成非 TextIOWrapper（如 pytest 的捕获对象）时直接跳过，
# 不会抛 AttributeError。
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

# 用真实抓下来的样本当夹具（scripts/dump_context_format.py 的产物）
REAL_SAMPLE = pathlib.Path(__file__).resolve().parent.parent / "docs" / "ref" / "context-sample.txt"

SYNTHETIC = """\
Knowledge Graph Data (Entity):

```json
{"entity": "箱子", "type": "location", "description": "…"}
{"entity": "维尔汀", "type": "character", "description": "…"}
```

Knowledge Graph Data (Relationship):

```json
{"entity1": "维尔汀", "entity2": "箱子", "description": "…"}
```

Document Chunks (Each entry has a reference_id refer to the `Reference Document List`; the optional `content_headings` field gives the chunk's heading path):

```json
{"reference_id": "1", "content": "A1"}
{"reference_id": "2", "content": "B1"}
{"reference_id": "1", "content": "A2"}
{"reference_id": "3", "content": "C1"}
```

Reference Document List (Each entry starts with a [reference_id] that corresponds to entries in the Document Chunks):

```json
[1] 101-在我们的时代里.md
[2] 36101-人们向何处去.md
[3] 1907-第九条美德.md
```
"""

failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  {'[PASS]' if cond else '[FAIL]'} {name}{('  ' + extra) if extra else ''}")
    if not cond:
        failures.append(name)


def main() -> int:
    print("=== split_sections ===")
    secs = split_sections(SYNTHETIC)
    check("识别出 4 个段", len([k for k in secs if not k.startswith("__")]) == 4, f"{sorted(secs)}")
    check("实体段存在", SEC_ENTITY in secs)
    check("chunk 段存在", SEC_CHUNKS in secs)
    check("引用段存在", SEC_REFLIST in secs)

    print("\n=== prune_context：只留 id=1 ===")
    out, st = prune_context(SYNTHETIC, {"1"})
    check("chunks 从 4 降到 2", (st.chunks_before, st.chunks_after) == (4, 2), f"{st.chunks_before}→{st.chunks_after}")
    check("refs 从 3 降到 1", (st.refs_before, st.refs_after) == (3, 1), f"{st.refs_before}→{st.refs_after}")
    check("KG 被整段丢弃", st.kg_dropped is True)
    check("正文里不再有实体段", "Knowledge Graph Data (Entity)" not in out)
    check("正文里不再有 id=2 的 chunk", '"reference_id": "2"' not in out)
    check("正文里仍有两个 id=1 的 chunk", out.count('"reference_id": "1"') == 2)
    check("引用列表只剩 [1]", out.count("[1] 101-在我们的时代里.md") == 1 and "[2] " not in out)
    check("dropped_ref_ids 正确", st.dropped_ref_ids == ["2", "3"], f"{st.dropped_ref_ids}")

    print("\n=== prune_context：drop_kg=False 时保留 KG ===")
    out2, st2 = prune_context(SYNTHETIC, {"1", "2"}, drop_kg=False)
    check("保留实体段", "Knowledge Graph Data (Entity)" in out2)
    check("保留关系段", "Knowledge Graph Data (Relationship)" in out2)
    check("kg_dropped=False", st2.kg_dropped is False)

    print("\n=== prune_context：空 keep_ids → 全部 chunk 被丢 ===")
    out3, st3 = prune_context(SYNTHETIC, set())
    check("chunks_after=0", st3.chunks_after == 0)
    check("refs_after=0", st3.refs_after == 0)
    # chunk 段与引用段各有一对围栏 → 共 4 个；结构必须仍然闭合
    check("两段的围栏都还在（结构没被截坏）", out3.count("```") == 4, f"```={out3.count('```')}")
    check("chunk 段标题仍在", SEC_CHUNKS in out3)
    check("引用段标题仍在", SEC_REFLIST in out3)

    print("\n=== prune_context：引用表非空时，未声明的 id 一律丢弃 ===")
    weird = SYNTHETIC.replace('{"reference_id": "3", "content": "C1"}', '{"reference_id": "99", "content": "X"}')
    out5, st5 = prune_context(weird, {"1", "99"})
    check("99 未在引用表声明 → 不进 keep", st5.chunks_after == 2, f"chunks_after={st5.chunks_after}")
    check("99 的 chunk 确实不在输出里", '"reference_id": "99"' not in out5)

    print("\n=== prune_context：引用表缺失时退化为只按 keep_ids ===")
    # 注意：不能用 "Reference Document List" 切 —— 那个短语也出现在
    # Document Chunks 的说明行里，会把 chunk 段一起切掉。用引用段标题的独有前缀。
    no_reflist = SYNTHETIC.split("Reference Document List (Each entry starts with")[0]
    check("夹具确实切掉了引用表", "Reference Document List (Each entry starts" not in no_reflist)
    check("夹具仍保留 chunk 段", SEC_CHUNKS in no_reflist)
    _out6, st6 = prune_context(no_reflist, {"1", "3"})
    check("仍能按 keep_ids 保留", st6.chunks_after == 3, f"chunks_after={st6.chunks_after}")

    print("\n=== prune_context：识别不出 chunk 段时原样返回（宁可不过滤） ===")
    out7, st7 = prune_context("完全不是上下文的文本", {"1"})
    check("原样返回", out7 == "完全不是上下文的文本")
    check("stats 全零", st7.chunks_before == 0 and st7.refs_after == 0)

    print("\n=== filter_references ===")
    refs = [
        {"reference_id": "1", "file_path": "101-在我们的时代里.md"},
        {"reference_id": "2", "file_path": "36101-人们向何处去.md"},
        {"reference_id": "3", "file_path": "sub/1907-第九条美德.md"},
    ]
    kept, mapping = filter_references(refs, {"101-在我们的时代里.md", "1907-第九条美德.md"})
    check("按文件名过滤（含带目录的路径）", [r["reference_id"] for r in kept] == ["1", "3"])
    check("返回 id→file 映射", mapping["2"] == "36101-人们向何处去.md")
    kept_all, _ = filter_references(refs, set())
    check("空集合 = 不过滤", len(kept_all) == 3)

    if REAL_SAMPLE.exists():
        print("\n=== 真实样本（83230 字符）上的表现 ===")
        text = REAL_SAMPLE.read_text(encoding="utf-8")
        # 只留 101 章那一条（真实样本里 id=2 是 101）
        out6, st6 = prune_context(text, {"2"})
        check("真实样本可解析", st6.refs_before == 21, f"refs_before={st6.refs_before}")
        check("裁剪后只剩 1 条引用", st6.refs_after == 1, f"refs_after={st6.refs_after}")
        check("体积显著下降", len(out6) < len(text) * 0.2, f"{len(text)} → {len(out6)} 字符")
        check("保留的是 101 章的 chunk", "101 · 在我们的时代里" in out6)
    else:
        print("\n[!] 跳过真实样本：先跑 scripts/dump_context_format.py 生成")

    print()
    if failures:
        print(f"[FAIL] {len(failures)} 项未通过：{failures}")
        return 1
    print("[PASS] 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
