"""从语料生成前端用的「今日台词」列表。

语料是第三方版权内容，所以：
  - 这个脚本可以进仓库；
  - **产物 `web/public/data/quotes.json` 不进仓库**（已 gitignore），随机器重新生成。

取的是每话的「副标题」行 —— 它是游戏内的一行短文案，短、独立、适合当引语。
用法：
    python scripts/gen_web_quotes.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "Reverse1999-Story-Compendium" / "readable" / "story_reader_linked" / "zh-CN"
OUT = ROOT / "web" / "public" / "data" / "quotes.json"

SUBTITLE_RE = re.compile(r"^> \*\*副标题：\*\*\s*(.+?)\s*$", re.M)
MIN_LEN, MAX_LEN = 8, 42


def main() -> int:
    if not CORPUS.exists():
        print(f"[x] 找不到语料目录：{CORPUS}", file=sys.stderr)
        print("    先跑 pipeline/update_index.py 或 README 的语料 clone 步骤。", file=sys.stderr)
        return 1

    quotes: list[dict[str, str]] = []
    seen: set[str] = set()
    for f in sorted(CORPUS.rglob("*.md")):
        if f.name == "README.md":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        # 章标题：文件名形如 `13101-行至摩卢旁卡.md`
        stem = f.stem
        title = stem.split("-", 1)[1] if "-" in stem else stem
        for m in SUBTITLE_RE.finditer(text):
            line = m.group(1).strip()
            if not (MIN_LEN <= len(line) <= MAX_LEN) or line in seen:
                continue
            seen.add(line)
            quotes.append({"text": line, "source": f"{title} · 副标题"})

    if not quotes:
        print("[x] 一条都没抽到 —— 语料格式可能变了。", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(quotes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] {len(quotes)} 条台词 → {OUT.relative_to(ROOT)}")
    print("     （该文件按设计不进仓库，换机器需重新生成）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
