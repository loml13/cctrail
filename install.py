#!/usr/bin/env python3
"""cctrail 安装器：拷贝 hooks + skill 到 ~/.claude，并安全合并 settings.json。

幂等：重复运行不会重复注册。改写 settings.json 前自动备份。纯标准库。

用法：
  python3 install.py            # 安装到 ~/.claude（或 $CLAUDE_CONFIG_DIR）
  python3 install.py --dry-run  # 只打印将做什么，不落盘
"""
import os
import sys
import json
import shutil

REPO = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude"
)
HOOKS_DST = os.path.join(CLAUDE_DIR, "hooks")
SKILLS_DST = os.path.join(CLAUDE_DIR, "skills", "log-compress")
SETTINGS = os.path.join(CLAUDE_DIR, "settings.json")

HOOK_FILES = [
    "cctrail_common.py",
    "log_user_prompt.py",
    "log_assistant_response.py",
    "inject_recent_log.py",
]

# (事件, 对应脚本)
REGISTRATIONS = [
    ("UserPromptSubmit", "log_user_prompt.py"),
    ("Stop", "log_assistant_response.py"),
    ("SessionStart", "inject_recent_log.py"),
]

DRY = "--dry-run" in sys.argv


def copy_files():
    if not DRY:
        os.makedirs(HOOKS_DST, exist_ok=True)
        os.makedirs(SKILLS_DST, exist_ok=True)
    for name in HOOK_FILES:
        src = os.path.join(REPO, "hooks", name)
        dst = os.path.join(HOOKS_DST, name)
        print(f"  copy  {name} -> {dst}")
        if not DRY:
            shutil.copy2(src, dst)
    print(f"  copy  log-compress -> {SKILLS_DST}")
    if not DRY:
        shutil.copy2(
            os.path.join(REPO, "skills", "log-compress", "SKILL.md"),
            os.path.join(SKILLS_DST, "SKILL.md"),
        )


def already_registered(event_list, script):
    for entry in event_list:
        for h in entry.get("hooks", []):
            if script in (h.get("command") or ""):
                return True
    return False


def patch_settings():
    settings = {}
    if os.path.exists(SETTINGS):
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                settings = json.load(f)
        except Exception as e:
            print(f"  !! 无法解析 {SETTINGS}：{e}")
            print("     跳过 settings 合并，请按 README 手动配置 hooks。")
            return
        bak = f"{SETTINGS}.cctrail-bak"
        print(f"  backup settings.json -> {bak}")
        if not DRY:
            shutil.copy2(SETTINGS, bak)

    hooks = settings.setdefault("hooks", {})
    changed = False
    for event, script in REGISTRATIONS:
        lst = hooks.setdefault(event, [])
        if already_registered(lst, script):
            print(f"  skip  {event}（已注册 {script}）")
            continue
        cmd = f"python3 {os.path.join(HOOKS_DST, script)}"
        lst.append({"hooks": [{"type": "command", "command": cmd}]})
        print(f"  add   {event} -> {cmd}")
        changed = True

    if changed and not DRY:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.write("\n")


def main():
    print(f"cctrail 安装 → {CLAUDE_DIR}" + ("  [dry-run]" if DRY else ""))
    copy_files()
    patch_settings()
    print("完成。新会话即生效（当前会话不受影响）。")


if __name__ == "__main__":
    main()
