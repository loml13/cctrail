# cctrail

English · [中文](README.md)

> A cross-session trail of "what you asked Claude Code to do" — pure hooks, zero dependencies, no extra tokens.

Every new session, Claude Code has amnesia: it doesn't know what you had it change yesterday, or where the last session left off.
cctrail uses three lightweight hooks to record **a summary of each prompt and reply** in the background,
and **auto-injects the recent trail into context when a new session starts** — so it knows what you've been working on the moment it boots.

## Why not yet another memory tool

The "session memory" projects around Claude Code fall into roughly two camps. cctrail is neither:

| Camp | Examples | Approach | Weakness |
|---|---|---|---|
| Offline view / sync | log viewer, log→git, log→Notion | export / display the official transcript | **doesn't re-inject** into new-session context |
| Heavy memory system | knowledge wiki, 5-layer architectures, Letta integration | structured long-term memory + retrieval | needs a server, dependencies, heavy setup |

cctrail takes a third path: **do only "trail + re-inject + compress", and do it as lightly as possible**.

- Pure Python standard library, **zero third-party deps**, no resident process
- Runs entirely inside hooks, **no extra conversation turns, no extra tokens**
- Remembers distilled Q&A only, not the full transcript
- Compression is skill-driven **semantic condensation** (keeps the thread)

## Components

| Part | Trigger | Role |
|---|---|---|
| `hooks/log_user_prompt.py` | UserPromptSubmit | filter chit-chat → append the prompt by month; inject a compaction reminder when due; call router on topic hits |
| `hooks/log_assistant_response.py` | Stop | record this turn's reply summary, paired (uses `.pending-response` to avoid orphans) |
| `hooks/inject_recent_log.py` | SessionStart | inject "last ~2 months thread + last N days verbatim" (skipped for resumed sessions) |
| `hooks/router.py` + `hooks/sources/` | UserPromptSubmit | topic recall: when you mention a known project/entity, pull pointers from each memory source (injected only on a hit, zero idle cost) |
| `hooks/cctrail_common.py` | — | shared dir resolution / config / prompt cleanup / memory-source interface |
| `skills/log-compress` | reminded by hook when due | condense entries older than 5 days into `## 历史摘要` (history summary) |

## Data flow

```
You prompt ──UserPromptSubmit──▶ log_user_prompt.py
                                  ├─ chit-chat? drop
                                  ├─ real question? write to YYYY-MM.md, set .pending-response
                                  └─ mentions a known topic? ──▶ router.py
                                        └─ inject "pointers" from each source (only on a hit; else zero cost)

Claude replies ──Stop──▶ log_assistant_response.py
                          └─ .pending-response present? append the reply summary under the same line

New session ──SessionStart──▶ inject_recent_log.py
                              ├─ long-term: last ~2 months "history summary" (compressed thread)
                              └─ last 5 days: verbatim entries (monitor noise filtered) → injected

Compaction due ──▶ hook reminds Claude to run the log-compress skill
                   └─ entries older than 5 days condensed into "history summary", last 5 days kept verbatim
```

The trail looks like this (see `examples/conversation-log-sample/`):

```markdown
## 2026-06-05

- 09:14 问：Add caching to the user service query
  ↳ 答：Wrapped getUser in an LRU, TTL 5min, added an invalidation hook; ~80% hit rate.
```

## Install

Requires Python 3.8+ and Claude Code.

```bash
git clone https://github.com/loml13/cctrail.git
cd cctrail
python3 install.py            # installs into ~/.claude, merges settings.json (backs it up first)
# python3 install.py --dry-run  # preview what it will change
```

The installer copies the hook scripts (including `router.py` and the `sources/` built-ins) into `~/.claude/hooks/`,
copies the log-compress skill into `~/.claude/skills/`, and registers three hooks in `~/.claude/settings.json`
(**idempotent** — re-running won't double-register; the file is backed up to `settings.json.cctrail-bak` before any edit).

**Takes effect on new sessions; the current session is unaffected.**

### Manual install

If you'd rather the script not touch your settings.json, copy `hooks/` into `~/.claude/hooks/` and
`skills/log-compress` into `~/.claude/skills/`, then add to `hooks` in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/log_user_prompt.py" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/log_assistant_response.py" }] }
    ],
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/inject_recent_log.py" }] }
    ]
  }
}
```

## Configuration

All via environment variables — no code changes needed:

| Variable | Default | Meaning |
|---|---|---|
| `CCTRAIL_HOME` | `~/.claude/cctrail` | trail root directory |
| `CCTRAIL_PER_PROJECT` | off | set to `1` to record per project `cwd`; default is one global trail |
| `CCTRAIL_COMPRESS_DAYS` | `1` | how many days between compaction reminders |
| `CCTRAIL_RECENT_DAYS` | `5` | "last N days" verbatim window for injection; must match log-compress's keep-verbatim window |
| `CCTRAIL_FILES_BACK` | `2` | how many monthly files "long-term memory" looks back (≈ last 2 months) |
| `CCTRAIL_LONG_MAX` | `80` | max lines injected for the long-term (history-summary) section |
| `CCTRAIL_RECENT_MAX` | `120` | max lines injected for the last-N-days section |
| `CCTRAIL_LINE_MAXLEN` | `240` | per-line truncation length |
| `CCTRAIL_RECALL` | `1` | set to `0` to disable topic recall |
| `CCTRAIL_MEMORY_MD` | `~/.claude/MEMORY.md` | index file the `memory_md` source reads; no-op if absent |
| `CCTRAIL_SOURCES_DIR` | `~/.claude/cctrail/sources` | custom memory-source dir; drop `*.py` here to auto-load |

Chit-chat filter rules and the wrapper tags to strip (e.g. an in-house IM bridge's shell tags) live at the top of
`hooks/cctrail_common.py` — edit as needed.

## Topic recall · cctrail as a memory middle layer

The trail is an activity timeline ordered **by time**. But when you mention an old project in a fresh session,
what you usually want is "what is this project" — recall **by topic**, not by recency. cctrail does this in UserPromptSubmit:

- When your message contains a **known topic** (project / tool / entity name), it pulls **pointers** from each memory source and injects them; if nothing is mentioned, nothing is added — **zero idle cost**.
- **Route, don't copy**: it injects a pointer ("where to get the full text") plus a tiny preview; the content stays in its source — no duplication, no context bloat.
- Each topic is injected at most once per session.

Two built-in sources:

| Source | Reads | On a hit returns |
|---|---|---|
| `trail` | cctrail's own trail | the Q&A lines matching the topic (capped) + the log file path |
| `memory_md` | Claude Code's native `MEMORY.md` index | the card title + the detail file path |

### Add your own memory source

Drop a `*.py` into `CCTRAIL_SOURCES_DIR` (default `~/.claude/cctrail/sources/`) and it's auto-loaded. Implement two methods:

```python
from cctrail_common import MemorySource, Hit

class ObsidianSource(MemorySource):
    name = "obsidian"
    def topics(self):                 # topic words this source recognizes (optional)
        return ()
    def lookup(self, topic, prompt):  # required: return [] when nothing matches
        import glob, os
        return [Hit("obsidian", os.path.basename(p), p)        # source, label, pointer
                for p in glob.glob(os.path.expanduser("~/vault/**/*.md"), recursive=True)
                if topic.lower() in p.lower()][:3]

SOURCE = ObsidianSource()
```

`examples/sources/shared_memory.py` is a full example (keyword-matching over a mem0/qdrant JSON backup) — copy it and change the path. A broken custom source is skipped silently and never affects the others.

## Privacy

The trail is a **real record of your conversations** with Claude and may contain sensitive info.

- Stored locally in `~/.claude/cctrail/` by default; **never uploaded anywhere**.
- This repo's `.gitignore` excludes runtime data, so **the trail won't be committed by accident**.
- log-compress will strip stray tokens / passwords / keys during compaction, but **don't rely on it as a safety net** —
  keep real secrets in environment variables, out of the conversation.

## Uninstall

Delete the cctrail scripts under `~/.claude/hooks/` (`cctrail_common.py` / `log_user_prompt.py` /
`log_assistant_response.py` / `inject_recent_log.py` / `router.py` and `sources/`) and `~/.claude/skills/log-compress/`,
then remove the corresponding hooks from `~/.claude/settings.json` (or just restore `settings.json.cctrail-bak`).
Trail data lives in `~/.claude/cctrail/` — keep it as an archive if you like.

## License

MIT
