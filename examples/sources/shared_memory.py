"""示例自定义源 —— 跨 agent 共享记忆库（mem0 + qdrant 的 JSON 备份）。

这是「自行添加记忆源」的范例：放到 CCTRAIL_SOURCES_DIR（默认 ~/.claude/cctrail/sources/）
即被 cctrail 自动加载。它依赖私有后端（一个每日 JSON 全量备份的目录），所以**不内置**，
照抄改路径即可接你自己的记忆库。

为什么读备份而不是直接查 MCP：hook 是裸 python 子进程，调不了 MCP，也不该在 hook 里
拉起 embedding/向量库。读最新 JSON 备份做关键词匹配，纯标准库、毫秒级；要实时结果，
让 agent 自己再调 search_memory。备份缺失则静默 no-op。

配置：环境变量 SHARED_MEMORY_BACKUPS 指向 `memory-*.json` 的 glob（默认见下）。
"""
import os
import glob
import json

from cctrail_common import MemorySource, Hit, clip, MIN_TOPIC_LEN

BACKUPS = os.path.expanduser(os.environ.get(
    "SHARED_MEMORY_BACKUPS", "~/.shared-memory/backups/memory-*.json"))
MAX_HITS = 3


class SharedMemorySource(MemorySource):
    name = "shared_memory"

    def _records(self):
        files = sorted(glob.glob(BACKUPS))
        if not files:
            return []
        try:
            data = json.load(open(files[-1], encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def topics(self):
        v = set()
        for r in self._records():
            t = (r.get("metadata") or {}).get("topic")
            if t and len(str(t)) >= MIN_TOPIC_LEN:
                v.add(str(t).lower())
        return v

    def lookup(self, topic, prompt):
        hits = []
        for r in self._records():
            mem = str(r.get("memory", ""))
            tp = str((r.get("metadata") or {}).get("topic", ""))
            if topic in mem.lower() or topic == tp.lower():
                who = r.get("agent_id", "?")
                hits.append(Hit("shared_memory", f"共享库·{who}",
                                f"search_memory('{topic}')", clip(mem, 140)))
        return hits[:MAX_HITS]


SOURCE = SharedMemorySource()
