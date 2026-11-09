# Local role usage / 本地角色用量

## English

**Run `usage` explicitly to inspect local usage by role and client.** Normal startup and receiving keep their existing behavior. The command reads native Claude/Codex JSONL files and the project's existing `.aris/workbench/launch.json` binding. It runs locally, opens no client or Herdr process, and leaves logs, bindings and global configuration unchanged.

### Commands and time range

```bash
superaris usage /path/to/project --by-role
superaris usage /path/to/project --by-role --json
superaris usage /path/to/project --hours 48 --lang en
superaris usage /path/to/project --since 2026-01-01T00:00:00+00:00 --until 2026-01-02T00:00:00+00:00 --json
superaris usage /path/to/project --claude-root /path/to/claude/projects --codex-root /path/to/codex/sessions --by-role --json
```

The default range is the previous 24 hours, with `[since, until)` boundaries. ISO timestamps require a timezone, `--since` replaces the lookback start, and `until` must be at or before the current time. Default roots are `.claude/projects` and `.codex/sessions` below the user's home directory; explicit roots support custom locations and offline fixtures. The scanner reads JSONL files and skips symlink files.

Text follows the binding's `ui_language`, defaulting to Chinese; `--lang zh|en` overrides it. JSON uses stable English keys and status codes. See [CLI](../src/superaris/cli.py) for the lazy command entry, [usage reports](../src/superaris/usage.py) for attribution and output, and [native log parsing](../src/superaris/usage_logs.py) for supported schemas and deduplication.

### Attribution and coverage

**Role ownership comes from `roles[ROLE].native_session_id` together with its client type.** An exact current binding takes priority. Explicit descendant links are supported: Claude `parentSessionId` / `parent_session_id` and native `SESSION/subagents/agent-*.jsonl` paths; Codex `session_meta` fields `forked_from_id`, `parent_thread_id`, `parent_session_id`, and `source.subagent.thread_spawn.parent_thread_id`.

Conflicting bindings and project sessions without a proven owner enter `unattributed`. A matching cwd only identifies project-local unattributed records; it never selects main or another role. Unlinked historical ownership is unknown. A log with no session link or project cwd cannot be assigned to this project. Antigravity currently has no usage parser and reports unknown.

Coverage describes local observations; completeness of the full usage ledger remains unknown. Missing roots or sessions, malformed/truncated lines, unsupported usage schemas, missing fields and missing timestamps produce diagnostics. Unknown values are `null`, and genuine recorded zero remains `0`. `observed` lists only known contributions; a partially covered total remains unknown. Diagnostics contain reason codes, relative file positions and line numbers, grouped into at most 100 entries with an explicit suppressed count.

### Requests, tokens and shares

There are three client/accounting rules:

1. Claude deduplicates assistant `message.id` values across streaming snapshots and restored copies. Repeated snapshots retain the greatest observed value per field, with one request per message. Input, cache read and cache creation are separate counts; their weights are 1, 0.1 and 1.25, with output weighted 5. Conflicting owners of a duplicated message remain unattributed.
2. Codex reads structured `token_usage_record` responses as well as legacy `event_msg.payload.type=token_count`. Structured records use their original thread/response IDs; matching cumulative and per-response usage reconciles the paired legacy representation without counting it twice. An exact copied usage prefix is shared only along an explicit `forked_from_id` link, preserving independent equal-cost requests. For legacy-only records, `last_token_usage` and the cumulative identity provide deduplication. Otherwise only a verifiable difference between cumulative snapshots contributes tokens, while request count remains unknown. A missing baseline, counter regression, range-crossing delta or missing stable identity remains unknown. Raw input includes cached input; normalized input subtracts cached input. Independent cache writes are `null` when absent; Codex equivalent tokens use the supported input/cache-read/output categories.
3. Each client and role reports requests, raw/normalized input, cache read/write, output, equivalent tokens and coverage. `share` is the role's fraction of project observations within that client, including unattributed usage in the denominator. `all_clients_share` covers verifiable cross-client observations. Missing or zero denominators produce `null` shares. Weights express relative contribution, with billing coverage unspecified.

A request/usage snapshot belongs to its local log timestamp. Only snapshots before the upper boundary participate; exact per-token occurrence times cannot be reconstructed. Ambiguous cumulative differences are retained as unknown.

### Privacy and synthetic example

The command accesses session logs and launch bindings only. Credentials, authentication files and process environments are outside its inputs. Reports omit conversation bodies and expose whitelisted usage values and positional diagnostics. There are no extra runtime dependencies or background collection services.

This synthetic excerpt contains one Claude request and its corresponding equivalent-token calculation:

```json
{
  "roles": {
    "main": {"clients": {"claude": {"requests": 1, "raw_input_tokens": 100, "input_tokens": 100, "cache_read_tokens": 20, "cache_write_tokens": 8, "output_tokens": 6, "equivalent_tokens": 142, "share": 1.0, "status": "observed"}}}
  },
  "weights": {"input": 1, "cache_read": 0.1, "cache_write": 1.25, "output": 5}
}
```

Synthetic tests in [usage tests](../tests/test_usage.py) cover attribution, descendants, deduplication, missing/damaged data, genuine zero, range boundaries, bilingual CLI and read-only execution. The established upstream test evidence and this command's focused evidence are recorded separately. Navigation starts at [documentation index](index.md).

## 中文

**显式运行 `usage`，按角色和客户端查看本地用量。** 默认启动和接收流程保持现有行为；命令只读原生Claude/Codex JSONL及项目现有 `.aris/workbench/launch.json` 绑定，全部本地执行，日志、绑定和全局配置保持原样。

### 入口与时间范围

使用上面的通用命令示例；默认回看24小时，边界为 `[since, until)`。时间须带时区，`--since` 覆盖起点，结束时间不晚于当前时间；默认日志根目录在用户主目录的 `.claude/projects`、`.codex/sessions`，显式目录支持自定义位置和离线夹具，扫描JSONL并跳过符号链接文件。

文本沿用绑定中的界面语言，默认中文，`--lang zh|en` 可覆盖；JSON使用固定英文键和状态码。实现入口为 [CLI惰性分支](../src/superaris/cli.py)、[归属与报告](../src/superaris/usage.py) 和 [原生日志解析](../src/superaris/usage_logs.py)。

### 归属与覆盖

**会话编号与客户端类型决定角色归属，当前精确绑定优先。** 支持英文节列出的Claude显式父会话/原生子代理目录及Codex父线程字段；绑定冲突或项目内无法证明角色的记录进入 `unattributed`。同cwd仅用于圈定项目未归属记录，未链接历史和缺少项目线索的日志保持归属未知；Antigravity暂无解析器。

覆盖范围是本地观测，完整账本覆盖仍未知。缺目录/会话、坏尾行、未知schema、缺字段或时间产生诊断；未知为null，真实零为0。`observed`只列可核实部分，整体覆盖不足时汇总保持未知；诊断仅含原因和文件位置，最多100类，额外数量单列。

### 请求、词元与占比

有以下三类口径：

1. Claude按消息ID及恢复副本去重，流式快照逐字段保留已观测最大值，每消息一次请求；输入、缓存读、缓存写和输出权重分别为1、0.1、1.25、5，重复消息有归属竞争时列未归属。
2. Codex支持结构化 `token_usage_record` 和旧 `token_count`；按原线程/响应ID识别结构化请求，以匹配的累计及单次用量协调双记录，只计一次。仅沿明确 `forked_from_id` 排除与父日志完全匹配的继承用量前缀，独立等量请求仍保留。旧格式有last时用last并按累计身份去重；仅有total时用可核实差量，请求数未知。原始input包含cached，归一化input先扣除cached；未提供的独立缓存写为null，等效值按已提供三类计算。缺基线、回退、跨起点或缺身份时保留未知。
3. 每角色/客户端展示请求、原始及归一输入、缓存读写、输出、等效值和覆盖状态；`share`为同客户端项目内占比，`all_clients_share`为可核实的跨客户端占比。分母未知或为零时为null，词元权重只表达相对贡献。

消息/快照归入本地记录时间所在范围，只采用结束边界前的数据；逐词元真实时间无法还原，无法拆分的累计差量保持未知。

### 隐私、示例与验证

**输入仅为会话日志及启动绑定，输出省略对话正文。** 命令不访问认证文件、凭据或进程环境，不发网络请求、启动客户端/Herdr、改写日志/绑定，也没有新增运行依赖和后台采集。英文节给出的JSON摘录为合成数据，Claude示例等效值为 `100+20×0.1+8×1.25+6×5=142`。

合成夹具见 [用量测试](../tests/test_usage.py)，覆盖精确归属、子会话、去重、缺失/损坏、真实零、时间边界和双语只读CLI。原始上游验证与本次受影响入口证据分别记录；模块导航见 [文档入口](index.md)。
