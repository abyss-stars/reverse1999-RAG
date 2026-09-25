#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""临时检查工具: 打印 .blocks.jsonl 的层级结构（在容器内运行）"""
import json
import sys

p = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 8

print("--- meta 行 ---")
with open(p, encoding="utf-8") as f:
    first = json.loads(f.readline())
print(json.dumps(first, ensure_ascii=False, indent=2)[:800])

print(f"\n--- 前 {n} 个 content block ---")
count = 0
levels = {}
with open(p, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("type") != "content":
            continue
        lv = d.get("level")
        levels[lv] = levels.get(lv, 0) + 1
        if count < n:
            print(f"level={lv}  heading={d.get('heading')!r}")
            print(f"         parent_headings={d.get('parent_headings')!r}")
            body = d.get("content") or ""
            print(f"         content[{len(body)}字]: {body[:70]!r}")
        count += 1

print(f"\n--- 统计 ---")
print(f"content block 总数: {count}")
print(f"level 分布: {levels}")
