#!/usr/bin/env python3
"""SessionStart hook：新会话开始时，把最近的对话留痕注入上下文，
让 Claude 知道用户此前找它做过什么。

分两段注入：
  · 长期记忆 —— 近两个月的压缩脉络（历史摘要），用于了解「可能仍在长期推进」的事。
  · 近 N 天   —— 最近 N 天的逐条原文（默认 5），用于了解「刚起步 / 进行中」的任务。
    N = RECENT_DAYS，应与 log-compress 的「原样保留窗口」对齐，注入才无盲区。

逐条 resume 续接的会话已有上下文，不重复注入。
"""
import sys
import os
import re
import glob
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cctrail_common import (  # noqa: E402
    log_dir, RECENT_DAYS, FILES_BACK, LONG_MAX_LINES, RECENT_MAX_LINES, LINE_MAXLEN,
)

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# 监视器 / 工具回执类噪声条目：不进记忆
NOISE_RE = re.compile(r"task-notification|Monitor event|tool-use-id|output-file")


def _trunc(ln):
    return ln if len(ln) <= LINE_MAXLEN else ln[:LINE_MAXLEN].rstrip() + " …"


def _parse(lines):
    """切块。返回 (summary_lines, [(date_str, [lines]), ...])。

    summary_lines 收 `## 历史摘要` 块全文（含 `### 日期` 子条目）；
    day_blocks 收每个 `## YYYY-MM-DD` 顶层日块的逐条原文。
    """
    summary, days = [], []
    mode, date, buf = None, None, []
    for ln in lines:
        if ln.startswith("## ") and not ln.startswith("###"):
            if mode == "day":
                days.append((date, buf))
            head = ln[3:].strip()
            m = DATE_RE.search(head)
            if head.startswith("历史摘要"):
                mode = "summary"
                summary.append(ln)
            elif m:
                mode, date, buf = "day", m.group(0), [ln]
            else:
                mode = None
            continue
        if mode == "summary":
            summary.append(ln)
        elif mode == "day":
            buf.append(ln)
    if mode == "day":
        days.append((date, buf))
    return summary, days


def _denoise(buf):
    """按「一问及其后续答行」为单位，丢掉 task-notification / monitor 噪声条目。"""
    out, skip = [], False
    for ln in buf:
        if ln.lstrip().startswith("- "):
            skip = bool(NOISE_RE.search(ln))
        if not skip:
            out.append(ln)
    return out


def build(summary, days, today):
    cut = today - timedelta(days=RECENT_DAYS - 1)

    # 长期段：历史摘要 —— 已压缩的多周脉络（= 可能长期在做的事），保留最近的部分。
    # 早于「近 N 天」、但尚未压进摘要的原文日不在此重复展开，
    # 待压缩窗口（log-compress「近 N 天原样保留」，与 RECENT_DAYS 对齐）把它们并入摘要。
    long_lines = [l for l in summary if l.strip()][-LONG_MAX_LINES:]

    # 近 N 天段：逐条原文，滤掉 task-notification / monitor 噪声条目
    recent_lines = []
    for ds, buf in days:
        try:
            dd = datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            continue
        if dd < cut:
            continue
        recent_lines.extend(_trunc(l) for l in _denoise(buf) if l.strip())
    recent_lines = recent_lines[-RECENT_MAX_LINES:]
    # 尾切可能从半条开始 —— 丢掉开头不完整的答 / 续行
    while recent_lines and not (
        recent_lines[0].lstrip().startswith("- ") or recent_lines[0].startswith("## ")
    ):
        recent_lines.pop(0)

    return long_lines, recent_lines


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
    for fp in files[-FILES_BACK:]:
        with open(fp, encoding="utf-8") as f:
            lines.extend(f.read().splitlines())

    summary, days = _parse(lines)
    long_lines, recent_lines = build(summary, days, datetime.now().date())

    parts = []
    if long_lines:
        parts.append("【长期记忆 · 近两个月脉络】\n" + "\n".join(long_lines))
    if recent_lines:
        parts.append(f"【近 {RECENT_DAYS} 天 · 最近在做的任务】\n" + "\n".join(recent_lines))
    if not parts:
        return

    context = (
        f"以下是用户此前与你对话的留痕，帮助你了解之前做过什么。分两段："
        f"前者是较长期、可能仍在推进的事；后者是最近 {RECENT_DAYS} 天刚起步 / 进行中的任务。"
        f"不必主动提起，按需参考即可：\n\n"
        + "\n\n".join(parts)
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }))


if __name__ == "__main__":
    main()
