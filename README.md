# cctrail

中文 · [English](README.en.md)

> 给 Claude Code 一条跨会话的「我让它做过什么」流水线记录 —— 纯 hook，零依赖，不烧 token。

每开一个新会话，Claude Code 都是失忆的：它不知道你昨天让它改了什么、上一个会话停在哪。
cctrail 用三个轻量 hook 在后台记下你**每一轮的提问与回答摘要**，
并在**新会话开始时自动把最近的留痕注入上下文** —— 于是它一上来就知道你最近在忙什么。


## 为什么不是又一个 memory 工具

Claude Code 周边的「session memory」项目大致两类，cctrail 都不是：

| 类别 | 代表 | 做法 | 短板 |
|---|---|---|---|
| 离线查看 / 同步 | log viewer、log→git、log→Notion | 把官方 transcript 导出 / 展示 | **不回注**到新会话上下文 |
| 重型记忆系统 | 知识 wiki、5 层架构、Letta 集成 | 结构化长期记忆 + 检索 | 起 server、装依赖、上手重 |

cctrail 走第三条路：**只做"流水 + 回注 + 压缩"这一件事，且做到最轻**。

- 纯 Python 标准库，**零第三方依赖**，不起任何常驻进程
- 全程跑在 hook 里，**不消耗额外对话轮次、不额外烧 token**
- 只记忆精炼问答，而非整段 transcript
- 压缩是 skill 驱动的**语义浓缩**（保留脉络）

## 组成

| 部件 | 触发时机 | 作用 |
|---|---|---|
| `hooks/log_user_prompt.py` | UserPromptSubmit | 过滤寒暄 → 按月追加用户提问；到周期注入压缩提醒；命中已知话题时调 router 召回 |
| `hooks/log_assistant_response.py` | Stop | 配对记录这一轮的回答摘要（靠 `.pending-response` 防孤儿） |
| `hooks/inject_recent_log.py` | SessionStart | 新会话注入「近两个月脉络 + 近 N 天原文」（resume 续接的会话跳过） |
| `hooks/router.py` + `hooks/sources/` | UserPromptSubmit | 话题召回：提到已知项目/实体时，从各记忆源拉指针注入（命中才注入，idle 零开销） |
| `hooks/cctrail_common.py` | — | 共享的目录解析 / 配置 / 提示词清洗 / 记忆源接口 |
| `skills/log-compress` | 周期到达时由 hook 提醒 | 把 5 天前的逐条记录语义浓缩成 `## 历史摘要` |

## 数据流

```
你提问 ──UserPromptSubmit──▶ log_user_prompt.py
                              ├─ 寒暄？丢弃
                              ├─ 实质问题？写入 YYYY-MM.md，落 .pending-response 标记
                              └─ 这句话提到已知话题？──▶ router.py
                                    └─ 从各记忆源拉「指针」注入（命中才有，否则零开销）

Claude 回答 ──Stop──▶ log_assistant_response.py
                       └─ 有 .pending-response？取回答摘要追加到同一行下

新会话开始 ──SessionStart──▶ inject_recent_log.py
                              ├─ 长期记忆：近两个月的「历史摘要」(压缩脉络)
                              └─ 近 5 天：逐条原文 (滤掉监视器噪声) → 注入上下文

到压缩周期 ──▶ hook 提醒 Claude 运行 log-compress skill
              └─ 5 天前记录浓缩为「历史摘要」，近 5 天原样保留
```

留痕长这样（见 `examples/conversation-log-sample/`）：

```markdown
## 2026-06-05

- 09:14 问：帮我给 user service 的查询加上缓存
  ↳ 答：用 LRU 包了 getUser，TTL 5min，加了失效钩子；命中率约 80%。
```

## 安装

需要 Python 3.8+ 和 Claude Code。

```bash
git clone https://github.com/loml13/cctrail.git
cd cctrail
python3 install.py            # 装到 ~/.claude，自动合并 settings.json（先备份）
# python3 install.py --dry-run  # 想先看它会改什么
```

安装器会：把 hook 脚本（含 `router.py` 与 `sources/` 内置源）拷到 `~/.claude/hooks/`、把
log-compress skill 拷到 `~/.claude/skills/`、向 `~/.claude/settings.json` 注册三个 hook
（**幂等**，重复运行不重复注册；改写前备份为 `settings.json.cctrail-bak`）。

**新会话即生效，当前会话不受影响。**

### 手动安装

不想让脚本碰你的 settings.json，就把 `hooks/` 拷到 `~/.claude/hooks/`、
`skills/log-compress` 拷到 `~/.claude/skills/`，然后在 `~/.claude/settings.json` 的
`hooks` 里加：

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

## 配置

全部通过环境变量，无需改代码：

| 变量 | 默认 | 说明 |
|---|---|---|
| `CCTRAIL_HOME` | `~/.claude/cctrail` | 留痕根目录 |
| `CCTRAIL_PER_PROJECT` | 关 | 设为 `1` 时按项目 `cwd` 分别记录；默认全局一份流水 |
| `CCTRAIL_COMPRESS_DAYS` | `1` | 多少天提醒压缩一次 |
| `CCTRAIL_RECENT_DAYS` | `5` | 注入「近 N 天」原文窗口；须与 log-compress 原样保留窗口一致 |
| `CCTRAIL_FILES_BACK` | `2` | 「长期记忆」回看几个月度文件（≈ 近两个月）|
| `CCTRAIL_LONG_MAX` | `80` | 长期段（历史摘要）注入行数上限 |
| `CCTRAIL_RECENT_MAX` | `120` | 近 N 天段注入行数上限 |
| `CCTRAIL_LINE_MAXLEN` | `240` | 单行超长截断字符数 |
| `CCTRAIL_RECALL` | `1` | 设为 `0` 关闭话题召回 |
| `CCTRAIL_MEMORY_MD` | `~/.claude/MEMORY.md` | `memory_md` 源读取的索引文件；不存在则该源 no-op |
| `CCTRAIL_SOURCES_DIR` | `~/.claude/cctrail/sources` | 自定义记忆源目录，放 `*.py` 即自动加载 |

寒暄过滤规则、需要剥离的注入标签（如自建 IM 桥接的外壳标签）在
`hooks/cctrail_common.py` 顶部，按需增删。

## 话题召回 · 当记忆的中间层

留痕是「按时间」的活动线。但换个会话提到某个老项目时，你要的往往是「这个项目是什么」——
**按话题**召回，而不是按最近。cctrail 在 UserPromptSubmit 里做这件事：

- 你这句话出现**已知话题**（项目 / 工具 / 实体名）时，才从各记忆源拉**指针**注入；没提到就什么都不加，**idle 零开销**。
- **路由不搬运**：注入的是「去哪取全文」的 pointer + 极短预览，内容仍留在各源里，不重复维护、不撑爆上下文。
- 每会话每话题只注一次。

内置两个源：

| 源 | 读什么 | 命中给什么 |
|---|---|---|
| `trail` | cctrail 自己的留痕 | 命中话题的问答行（封顶）+ 日志文件路径 |
| `memory_md` | Claude Code 原生 `MEMORY.md` 索引 | 卡片标题 + detail 文件路径 |

### 加自己的记忆源

放一个 `*.py` 到 `CCTRAIL_SOURCES_DIR`（默认 `~/.claude/cctrail/sources/`）即被自动加载，实现两个方法：

```python
from cctrail_common import MemorySource, Hit

class ObsidianSource(MemorySource):
    name = "obsidian"
    def topics(self):                 # 本源认识的话题词（可省略）
        return ()
    def lookup(self, topic, prompt):  # 必实现：查不到返回 []
        import glob, os
        return [Hit("obsidian", os.path.basename(p), p)        # source, label, pointer
                for p in glob.glob(os.path.expanduser("~/vault/**/*.md"), recursive=True)
                if topic.lower() in p.lower()][:3]

SOURCE = ObsidianSource()
```

`examples/sources/shared_memory.py` 是一个完整范例（接 mem0/qdrant 的 JSON 备份做关键词匹配），照抄改路径即可。坏掉的自定义源会被静默跳过，不影响其它源。

## 隐私

留痕是你和 Claude 的**真实对话记录**，可能含敏感信息。

- 默认存在本地 `~/.claude/cctrail/`，**不上传任何地方**。
- 本仓库 `.gitignore` 已排除运行时数据，**留痕不会被误提交**。
- log-compress 在压缩时会顺手删除混入的 token / 密码 / key，但**别依赖它兜底** ——
  真正的密钥请走环境变量，不要贴进对话。

## 卸载

删掉 `~/.claude/hooks/` 下的 cctrail 脚本（`cctrail_common.py` / `log_user_prompt.py` /
`log_assistant_response.py` / `inject_recent_log.py` / `router.py` 与 `sources/`）和
`~/.claude/skills/log-compress/`，并从 `~/.claude/settings.json` 移除对应 hook
（或直接还原 `settings.json.cctrail-bak`）。留痕数据在 `~/.claude/cctrail/`，想留作归档可保留。

## License

MIT
