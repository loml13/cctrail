#!/usr/bin/env python3
"""cctrail 公共逻辑：留痕目录解析、配置、提示词清洗。

被三个 hook 共享。纯标准库，零第三方依赖。

可用环境变量覆盖：
  CCTRAIL_HOME          留痕根目录（默认 ~/.claude/cctrail）
  CCTRAIL_PER_PROJECT   设为 1 时按项目 cwd 隔离留痕（默认全局一份）
  CCTRAIL_COMPRESS_DAYS 压缩触发周期，单位天（默认 1）
  CCTRAIL_RECENT_DAYS   SessionStart「近 N 天」原文窗口（默认 5；
                        需与 log-compress 的「原样保留窗口」对齐，注入才无盲区）
  CCTRAIL_FILES_BACK    「长期记忆」回看几个月度文件（默认 2 ≈ 近两个月）
  CCTRAIL_LONG_MAX      长期段（历史摘要）注入行数上限（默认 80）
  CCTRAIL_RECENT_MAX    近 N 天段注入行数上限（默认 120）
  CCTRAIL_LINE_MAXLEN   单行超长截断字符数（默认 240，防贴大块撑爆注入）
"""
import os
import re


def _home():
    return os.environ.get("CCTRAIL_HOME") or os.path.join(
        os.path.expanduser("~"), ".claude", "cctrail"
    )


def log_dir(cwd=None, create=True):
    """返回当前留痕目录。

    默认全局一份；设 CCTRAIL_PER_PROJECT=1 时按 cwd 隔离。
    create=False 时仅计算路径、不落盘（供只读的 SessionStart 用）。
    """
    base = _home()
    if os.environ.get("CCTRAIL_PER_PROJECT") and cwd:
        slug = cwd.strip("/").replace("/", "-") or "root"
        path = os.path.join(base, "projects", slug, "conversation-log")
    else:
        path = os.path.join(base, "conversation-log")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def pending_path(d):
    return os.path.join(d, ".pending-response")


def last_compressed_path(d):
    return os.path.join(d, ".last-compressed")


# ---- 配置（环境变量可覆盖）----
COMPRESS_INTERVAL_DAYS = int(os.environ.get("CCTRAIL_COMPRESS_DAYS", "1"))

# SessionStart 注入：长期记忆（历史摘要）+ 近 N 天原文，分两段
RECENT_DAYS = int(os.environ.get("CCTRAIL_RECENT_DAYS", "5"))
FILES_BACK = int(os.environ.get("CCTRAIL_FILES_BACK", "2"))
LONG_MAX_LINES = int(os.environ.get("CCTRAIL_LONG_MAX", "80"))
RECENT_MAX_LINES = int(os.environ.get("CCTRAIL_RECENT_MAX", "120"))
LINE_MAXLEN = int(os.environ.get("CCTRAIL_LINE_MAXLEN", "240"))

# 寒暄 / 测试类短消息：仅当整体匹配且长度 <= 12 时过滤，避免误伤真实提问。
TRIVIAL = re.compile(
    r"^(哈喽|你好|您好|早|早上好|中午好|下午好|晚上好|hi|hello|hey|在吗|"
    r"测试|test|ok|好的?|嗯+|收到|谢谢|thx|不客气|"
    r"[0-9\s\W]+|又?卡了|好慢|有点慢|怎么.{0,6}久)$",
    re.IGNORECASE,
)

# 注入型外壳标签：来自第三方桥接 / 交互卡片 / 系统提醒，记录前剥掉，
# 只留用户真正写下的话。按需增删（例如接入了自己的 IM 桥接）。
INJECTED_BLOCKS = (
    r"<bridge_context>.*?</bridge_context>",
    r"<quoted_message.*?</quoted_message>",
    r"<interactive_card>.*?</interactive_card>",
    r"<forwarded_messages>.*?</forwarded_messages>",
    r"<system-reminder>.*?</system-reminder>",
)


def clean_prompt(raw):
    """剥掉注入外壳、压平空白，得到用户的纯净提问。"""
    for pat in INJECTED_BLOCKS:
        raw = re.sub(pat, "", raw, flags=re.S)
    return " ".join(raw.split())
