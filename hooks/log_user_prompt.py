#!/usr/bin/env python3
"""UserPromptSubmit hook：

1. 把用户的实质提问追加到对话留痕日志（寒暄 / 测试类短消息过滤）。
2. 维护 .pending-response 标记，供 Stop hook 判断是否记录本轮回答。
3. 检查留痕日志是否到达压缩周期，到期则注入压缩提醒。

纯脚本运行，不消耗额外 Claude 轮次。
"""
import sys
import os
import json
import glob
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cctrail_common import (  # noqa: E402
    log_dir,
    pending_path,
    last_compressed_path,
    clean_prompt,
    TRIVIAL,
    COMPRESS_INTERVAL_DAYS,
)


def log_prompt(d, text):
    """记录一条实质提问；返回 True 表示已记录。"""
    if not text or (len(text) <= 12 and TRIVIAL.match(text)):
        return False
    now = datetime.now()
    log_file = os.path.join(d, now.strftime("%Y-%m.md"))
    day_heading = now.strftime("## %Y-%m-%d")
    existing = ""
    if os.path.exists(log_file):
        with open(log_file, encoding="utf-8") as f:
            existing = f.read()
    with open(log_file, "a", encoding="utf-8") as f:
        if day_heading not in existing:
            f.write(f"\n{day_heading}\n\n")
        f.write(f"- {now:%H:%M} 问：{text[:200]}\n")
    return True


def compress_due(d):
    """到达压缩周期返回 True。首次运行只建标记、不提醒。"""
    if not glob.glob(os.path.join(d, "*.md")):
        return False
    marker = last_compressed_path(d)
    if not os.path.exists(marker):
        try:
            with open(marker, "w") as f:
                f.write(datetime.now().isoformat(timespec="seconds"))
        except Exception:
            pass
        return False
    try:
        with open(marker) as f:
            last = datetime.fromisoformat(f.read().strip())
    except Exception:
        return False
    return datetime.now() - last > timedelta(days=COMPRESS_INTERVAL_DAYS)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    d = log_dir(data.get("cwd"))
    text = clean_prompt(data.get("prompt", "") or "")

    logged = log_prompt(d, text)
    pending = pending_path(d)
    if logged:
        open(pending, "w").close()
    elif os.path.exists(pending):
        os.remove(pending)

    if compress_due(d):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    f"[系统] conversation-log 距上次压缩已超过 "
                    f"{COMPRESS_INTERVAL_DAYS} 天。请在回应用户之后，运行 "
                    f"log-compress skill 压缩留痕日志（不必向用户特别说明）。"
                ),
            }
        }))


if __name__ == "__main__":
    main()
