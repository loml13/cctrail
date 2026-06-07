# cctrail

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
| `hooks/log_user_prompt.py` | UserPromptSubmit | 过滤寒暄 → 按月追加用户提问；到周期注入压缩提醒 |
| `hooks/log_assistant_response.py` | Stop | 配对记录这一轮的回答摘要（靠 `.pending-response` 防孤儿） |
| `hooks/inject_recent_log.py` | SessionStart | 新会话把最近 N 行留痕注入上下文（resume 续接的会话跳过） |
| `hooks/cctrail_common.py` | — | 三者共享的目录解析 / 配置 / 提示词清洗 |
| `skills/log-compress` | 周期到达时由 hook 提醒 | 把 7 天前的逐条记录语义浓缩成 `## 历史摘要` |

## 数据流

```
你提问 ──UserPromptSubmit──▶ log_user_prompt.py
                              ├─ 寒暄？丢弃
                              └─ 实质问题？写入 YYYY-MM.md，落 .pending-response 标记

Claude 回答 ──Stop──▶ log_assistant_response.py
                       └─ 有 .pending-response？取回答摘要追加到同一行下

新会话开始 ──SessionStart──▶ inject_recent_log.py
                              └─ 读最近 2 个月度文件的末尾 N 行 → 注入上下文

到压缩周期 ──▶ hook 提醒 Claude 运行 log-compress skill
              └─ 7 天前记录浓缩为「历史摘要」，近 7 天原样保留
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

安装器会：把 4 个 hook 脚本拷到 `~/.claude/hooks/`、把 log-compress skill 拷到
`~/.claude/skills/`、向 `~/.claude/settings.json` 注册三个 hook（**幂等**，重复运行不重复注册；
改写前备份为 `settings.json.cctrail-bak`）。

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
| `CCTRAIL_MAX_LINES` | `40` | SessionStart 注入的最大行数 |
| `CCTRAIL_COMPRESS_DAYS` | `1` | 多少天提醒压缩一次 |

寒暄过滤规则、需要剥离的注入标签（如自建 IM 桥接的外壳标签）在
`hooks/cctrail_common.py` 顶部，按需增删。

## 隐私

留痕是你和 Claude 的**真实对话记录**，可能含敏感信息。

- 默认存在本地 `~/.claude/cctrail/`，**不上传任何地方**。
- 本仓库 `.gitignore` 已排除运行时数据，**留痕不会被误提交**。
- log-compress 在压缩时会顺手删除混入的 token / 密码 / key，但**别依赖它兜底** ——
  真正的密钥请走环境变量，不要贴进对话。

## 卸载

删掉 `~/.claude/hooks/` 下的四个脚本与 `~/.claude/skills/log-compress/`，
并从 `~/.claude/settings.json` 移除对应 hook（或直接还原 `settings.json.cctrail-bak`）。
留痕数据在 `~/.claude/cctrail/`，想留作归档可保留。

## License

MIT
