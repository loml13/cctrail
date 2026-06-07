#!/usr/bin/env python3
"""cctrail 话题召回路由器。

被 UserPromptSubmit hook 调用：用户这句话出现已知话题（项目/实体）时，从各记忆源
拉「指针」注入上下文 —— 路由不搬运，内容仍留在各源里。命中才注入，idle 零开销。

内置源：trail（cctrail 留痕）、memory_md（Claude Code 原生 MEMORY.md）。
自定义源：在 CCTRAIL_SOURCES_DIR 放 *.py（见 cctrail_common 顶部接口说明），自动加载。
shared_memory 等依赖私有后端的源不内置，见 examples/sources/ 照抄。
"""
import os
import re
import sys
import glob
import json
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cctrail_common import (  # noqa: E402
    MemorySource, Hit, log_dir, SOURCES_DIR, MIN_TOPIC_LEN, MAX_TOPICS, RECALL_ENABLED,
)


def _builtins():
    from sources import trail, memory_md
    return [trail.SOURCE, memory_md.SOURCE]


def _dropins():
    out = []
    if not os.path.isdir(SOURCES_DIR):
        return out
    for fp in sorted(glob.glob(os.path.join(SOURCES_DIR, "*.py"))):
        try:
            spec = importlib.util.spec_from_file_location(
                "cctrail_src_" + os.path.basename(fp)[:-3], fp)
            mod = importlib.util.module_from_spec(spec)
            mod.MemorySource, mod.Hit = MemorySource, Hit   # 备用：也可 from cctrail_common import
            spec.loader.exec_module(mod)
            src = getattr(mod, "SOURCE", None)
            if src is None:
                for v in vars(mod).values():
                    if isinstance(v, type) and issubclass(v, MemorySource) and v is not MemorySource:
                        src = v()
                        break
            if src is not None:
                out.append(src)
        except Exception:
            continue   # 坏的自定义源不拖垮主流程
    return out


def _sources():
    try:
        b = _builtins()
    except Exception:
        b = []
    return b + _dropins()


def _marker(session_id):
    sid = re.sub(r"[^\w.-]", "_", session_id or "nosess")[:64]
    return os.path.join(log_dir(create=False), f".routed-{sid}")


def _already(session_id):
    try:
        return set(open(_marker(session_id), encoding="utf-8").read().split())
    except Exception:
        return set()


def _remember(session_id, topics):
    try:
        with open(_marker(session_id), "a", encoding="utf-8") as f:
            for t in topics:
                f.write(t + "\n")
    except Exception:
        pass


def route(prompt, session_id=None):
    """命中已知话题则返回注入文本，否则 None。"""
    if not RECALL_ENABLED or not prompt:
        return None
    low = prompt.lower()
    sources = _sources()

    vocab = set()
    for s in sources:
        try:
            vocab |= {t for t in s.topics() if t and len(t) >= MIN_TOPIC_LEN}
        except Exception:
            continue

    done = _already(session_id)
    matched = [t for t in sorted(vocab, key=len, reverse=True)
               if t in low and t not in done][:MAX_TOPICS]
    if not matched:
        return None

    blocks, fresh = [], []
    for topic in matched:
        hits = []
        for s in sources:
            try:
                hits.extend(s.lookup(topic, prompt) or [])
            except Exception:
                continue
        if not hits:
            continue
        fresh.append(topic)
        lines = [f"・「{topic}」"]
        for h in hits:
            tail = f" — {h.snippet}" if h.snippet else ""
            lines.append(f"    [{h.source}] {h.label} → {h.pointer}{tail}")
        blocks.append("\n".join(lines))

    if not blocks:
        return None
    _remember(session_id, fresh)
    return (
        "[cctrail · 相关记忆] 你提到了下面的话题，附各记忆源的指针供按需取用"
        "（不必主动提起；要全文/实时就去 pointer 取）：\n" + "\n".join(blocks)
    )


if __name__ == "__main__":
    data = {}
    try:
        data = json.load(sys.stdin)
    except Exception:
        pass
    print(route(data.get("prompt", ""), data.get("session_id")) or "(无命中)")
