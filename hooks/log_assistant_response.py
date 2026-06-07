#!/usr/bin/env python3
"""Stop hook：把 Claude 本轮回答追加到对话留痕日志。

仅当 UserPromptSubmit 记录了对应的用户提问（.pending-response 存在）时才记录，
避免给被过滤掉的寒暄消息留下孤立的回答。

非阻塞 —— 只写文件后退出，不增加对话轮次。
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cctrail_common import log_dir, pending_path  # noqa: E402


def last_assistant_text(transcript_path):
    """从 transcript JSONL 里取最后一条 assistant 消息的文本。"""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "assistant":
            continue
        content = obj.get("message", {}).get("content", [])
        if isinstance(content, str):
            return content.strip()
        parts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        joined = " ".join(p for p in parts if p).strip()
        if joined:
            return joined
    return ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    d = log_dir(data.get("cwd"))
    pending = pending_path(d)
    if not os.path.exists(pending):
        return
    try:
        os.remove(pending)
    except Exception:
        pass

    answer = last_assistant_text(data.get("transcript_path", ""))
    if not answer:
        return

    preview = " ".join(answer.split())[:300]
    log_file = os.path.join(d, datetime.now().strftime("%Y-%m.md"))
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"  ↳ 答：{preview}\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
