"""内置源 memory_md —— Claude Code 原生记忆（MEMORY.md 索引）。

把 MEMORY.md 的索引行 `- [标题](file.md) — 钩子` 解析出来，命中话题就回带
卡片标题 + detail 文件路径（route by reference，只给指针不搬全文）。
MEMORY.md 路径由 CCTRAIL_MEMORY_MD 配置，不存在则静默 no-op。
"""
import os
import re

from cctrail_common import (  # noqa: E402
    MemorySource, Hit, clip, MEMORY_MD, MIN_TOPIC_LEN,
)

_ENTRY = re.compile(r"^\s*[-*]\s*\[(.+?)\]\((.+?\.md)\)\s*[—-]+\s*(.*)$")


def _terms(title, fname):
    terms = set(re.findall(r"[A-Za-z][\w]{3,}", title))
    terms |= set(re.split(r"[_\-.]", os.path.splitext(os.path.basename(fname))[0]))
    return {t.lower() for t in terms if len(t) >= MIN_TOPIC_LEN}


class MemoryMdSource(MemorySource):
    name = "memory_md"

    def _entries(self):
        out = []
        try:
            for ln in open(MEMORY_MD, encoding="utf-8"):
                m = _ENTRY.match(ln)
                if m:
                    out.append((m.group(1).strip(), m.group(2).strip(), m.group(3).strip()))
        except Exception:
            pass
        return out

    def topics(self):
        v = set()
        for title, fname, _ in self._entries():
            v |= _terms(title, fname)
        return v

    def lookup(self, topic, prompt):
        base = os.path.dirname(MEMORY_MD)
        hits = []
        for title, fname, hook in self._entries():
            if topic in _terms(title, fname):
                path = fname if os.path.isabs(fname) else os.path.join(base, fname)
                hits.append(Hit("memory_md", title, path, clip(hook, 120)))
        return hits[:2]


SOURCE = MemoryMdSource()
