#!/usr/bin/env python3
"""SessionStart hook：新会话开始时，把最近的对话留痕注入上下文，
让 Claude 知道用户此前找它做过什么。

逐条 resume 续接的会话已有上下文，不重复注入。
"""
import sys
import os
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cctrail_common import log_dir, MAX_LINES  # noqa: E402


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    # resume 是逐条续接，已有上下文 —— 不重复注入
    if data.get("source") == "resume":
        return

    d = log_dir(data.get("cwd"), create=False)
    files = sorted(glob.glob(os.path.join(d, "*.md")))
    if not files:
        return

    lines = []
    for fp in files[-2:]:
        with open(fp, encoding="utf-8") as f:
            lines.extend(f.read().splitlines())

    recent = [ln for ln in lines if ln.strip()][-MAX_LINES:]
    if not recent:
        return

    context = (
        "以下是用户此前与你对话的留痕（最近的实质请求记录），"
        "用于让你了解之前做过什么。不必主动提起，按需参考即可：\n\n"
        + "\n".join(recent)
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }))


if __name__ == "__main__":
    main()
