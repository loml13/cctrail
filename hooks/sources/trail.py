"""内置源 trail —— cctrail 自己的留痕。

话题词 = 留痕里出现的 repo/路径名（高精度）+ 高频 ASCII 词（项目/工具名会反复出现，
去停用词与随机 ID）。lookup 按关键词回带命中的问答行（封顶，路由不搬运）。
"""
import os
import re
import glob
from collections import Counter

from cctrail_common import (  # noqa: E402
    MemorySource, Hit, log_dir, clip, idish, STOP, FREQ_MIN, MIN_TOPIC_LEN,
)

# ASCII-only：\w 会匹配中文，把 repo 名和后面的中文粘住。兼容 / 与 SSH 冒号。
_REPO = re.compile(
    r"github\.com[/:][A-Za-z0-9._-]+/([A-Za-z][A-Za-z0-9._-]{2,})"
    r"|/(?:Documents|repos|projects|src|code)/([A-Za-z][A-Za-z0-9._-]{2,})")

TRAIL_HITS = 6   # 最多回带几行


class TrailSource(MemorySource):
    name = "trail"

    def _files(self):
        return sorted(glob.glob(os.path.join(log_dir(create=False), "*.md")))

    def topics(self):
        names, counter = set(), Counter()
        for fp in self._files():
            try:
                txt = open(fp, encoding="utf-8").read()
            except Exception:
                continue
            for m in _REPO.finditer(txt):
                name = (m.group(1) or m.group(2) or "").rstrip(".,;:)/")
                if name.endswith(".git"):
                    name = name[:-4]
                if len(name) >= MIN_TOPIC_LEN:
                    names.add(name.lower())
            counter.update(re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,29}", txt.lower()))
        names |= {w for w, c in counter.items()
                  if c >= FREQ_MIN and w not in STOP and not idish(w)}
        return names

    def lookup(self, topic, prompt):
        files = self._files()
        lines = []
        for fp in files:
            try:
                for ln in open(fp, encoding="utf-8"):
                    if topic.lower() in ln.lower() and ln.lstrip().startswith(("-", "##")):
                        lines.append(ln.strip())
            except Exception:
                continue
        if not lines:
            return []
        recent = lines[-TRAIL_HITS:]
        snippet = " / ".join(clip(l, 90) for l in recent)
        return [Hit("trail", f"留痕命中 {len(lines)} 处（带最近 {len(recent)} 条）",
                    files[-1], clip(snippet))]


SOURCE = TrailSource()
