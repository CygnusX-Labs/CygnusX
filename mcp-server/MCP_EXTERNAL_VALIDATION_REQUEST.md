# CygnusX MCP 外部权限验收委托书

## 1. 目的和范围

请在具备本机进程管道、回环网络、平台 API、Redis（如确认链路需要）和相应数据库出口权限的测试 Agent 上，完成 CygnusX MCP 的真实外部验收。本委托覆盖：

1. STDIO、SSE 和 Streamable HTTP 的真实 MCP 握手。
2. 外部客户端 `tools/list` 实际收到的工具描述。
3. 只读 `tools/call` 经 MCP 到平台 REST 或 provider 的真实链路。
4. 19 个 Agent 的 MCP 绑定、白名单裁剪和最终模型工具集合。
5. 17 项科研数据库资源的可审计接通状态。

本次只读验收禁止写入生产数据、关闭认证、绑定公网地址、伪造确认参数或发起压力请求。

## 2. 当前基线

测试前以当前工作树和以下文件为准，不以旧报告中的工具数量或名称为准：

- `mcp-server/main.py`、`mcp-server/pipelines_main.py`
- `mcp-server/tools/__init__.py`、`mcp-server/tools.yaml`
- `mcp-server/resources/catalog.py`、`mcp-server/prompts/workflows.py`
- `mcp-server/core/config.py`、`mcp-server/core/runtime.py`
- `mcp-server/README.md`、`mcp-server/ARCHITECTURE.md`
- `ARCHITECTURE_DESIGN/CygnusX_mcp_architecture.md`
- `data/ai/*.yaml`、`data/ai/tools/research.yaml`
- `src/cygnusx/application/services/agent_service.py`
- `src/cygnusx/infrastructure/mcp/presets.py`、`biothings_preset.py`、`research_preset.py`

外部 Server 当前默认线索是 **109 个工具、18 个工具组、5 个 Prompt、4 个 Resource**，最终数字必须以真实 `tools/list`、`prompts/list`、`resources/list` 返回为准。FastMCP 版本必须实测记录：

```bash
cd /path/to/OmicHub/mcp-server
./.venv/bin/python --version
./.venv/bin/python -c 'import fastmcp; print(fastmcp.__version__, fastmcp.__file__)'
```

## 3. 权限、安全和证据要求

开始前记录下表；凭证只记录是否配置、长度或 hash 前缀，不记录原文。

| 条件 | 要求 | 证据 |
|---|---|---|
| Python/FastMCP | 使用 MCP venv，记录版本和路径 | `environment.txt` |
| STDIO | 允许子进程、stdin/stdout 和后台线程读取 | Inspector 连接结果 |
| HTTP | 允许绑定 `127.0.0.1`/`::1` | 监听结果 |
| 平台 API | 测试 URL 和专用 API Key | 脱敏配置记录 |
| HTTP MCP Token | 独立于 API Key，至少 32 字符 | 长度和 hash 前缀 |
| Redis | 确认链路需要时使用隔离 Redis | 连接结果 |
| provider 出口 | 可发送少量公开只读请求 | 响应摘要 |

安全要求：

- HTTP/SSE 只能监听 `127.0.0.1`、`localhost` 或 `::1`。
- 不得使用 `allow_non_loopback_http` 绕过限制。
- `CYGNUSX_HTTP_TOKEN` 与 `CYGNUSX_API_KEY` 必须不同。
- 输出中不得出现 API Key、Bearer Token、JWT、Cookie、完整用户路径或隐私样本信息。
- 只调用只读工具；禁止 `submit`、`cancel`、`sandbox_execute`、`sandbox_destroy`、云下载提交及确认门写工具。
- 每项 provider 最多一个小请求，必要时只重试一次。

建议证据目录：

```text
evidence/mcp-external-validation-YYYY-MM-DD/
  environment.txt
  stdio-initialize.log
  stdio-tools-list.ndjson
  stdio-readonly-call.json
  http-initialize.json
  http-tools-list.ndjson
  http-readonly-call.json
  prompts-list.json
  resources-list.json
  description-audit.tsv
  agent-tool-loading.tsv
  provider-status.tsv
  failures.ndjson
  checksums.txt
```

所有证据必须脱敏，并记录 UTC 时间、测试 Agent、代码 SHA、命令、传输、目标、结果、错误码、耗时和证据路径。

## 4. STDIO 验收

### 4.1 启动和 Inspector

```bash
cd /path/to/OmicHub/mcp-server
./.venv/bin/python main.py
```

用项目 venv 和正确工作目录执行真实 MCP 请求。Inspector 参数以本机帮助为准：

```bash
MCP_INSPECTOR_SECRET_STORE=memory \
  mcp-inspector --cli \
  --cwd /path/to/OmicHub/mcp-server \
  --method initialize \
  /path/to/OmicHub/mcp-server/.venv/bin/python main.py

MCP_INSPECTOR_SECRET_STORE=memory \
  mcp-inspector --cli \
  --cwd /path/to/OmicHub/mcp-server \
  --method tools/list \
  /path/to/OmicHub/mcp-server/.venv/bin/python main.py
```

必须分别保存 `initialize`、`notifications/initialized`、`tools/list`、`prompts/list` 和 `resources/list` 的原始结果。不得只保存退出码或启动日志。

### 4.2 STDIO 必须记录的内容

- `initialize`：JSON-RPC 成功/失败、协议版本、ServerInfo、能力声明和耗时。
- `tools/list`：分页 cursor、数量、每项 `name`、`description`、`inputSchema`。
- `prompts/list` 和 `resources/list`：数量、名称/URI、描述。
- 只读 `tools/call`：工具名、脱敏参数、`isError`、业务 `success`、摘要、数据类型和耗时。
- Server stderr：启动、自校验、FastMCP 版本、警告和异常。
- stdout 原始字节：确认是否混入非 JSON-RPC 日志。
- 命令、工作目录、解释器真实路径、环境变量名称和启动到超时的时间线。

若 `initialize` 超时，必须启动一个只有 `ping` 工具的最小 FastMCP 对照服务，说明是环境管道问题、Inspector/SDK 兼容问题还是 CygnusX 代码问题。不得只增加超时。

### 4.3 STDIO 只读调用建议

按测试账户数据情况选择至少一个平台、一个任务/文件和一个科研数据库工具：

```text
cygnusx_list_flows       {}
cygnusx_get_platform_status  {}
cygnusx_list_tasks        {"status":"success"}
cygnusx_gene_search       {"query":"TP53","species":"human","limit":1,"offset":0}
cygnusx_variant_search    {"query":"rs121913529","assembly":"hg38","limit":1,"offset":0}
```

没有数据时区分“业务无数据”“平台 REST 失败”“provider 网络失败”和“参数校验失败”。错误封装的 `success=false` 不得写成数据库业务成功。

## 5. HTTP、SSE 和 Streamable HTTP 验收

### 5.1 启动

从安全凭证存储注入独立 Token，不要写入命令历史或证据：

```bash
export CYGNUSX_HTTP_TOKEN='安全存储注入的至少32字符测试Token'
export CYGNUSX_API_KEY='安全存储注入的测试平台Key'
export CYGNUSX_HOST='127.0.0.1'
export CYGNUSX_PORT='8900'
./.venv/bin/python main.py --transport streamable-http --port 8900
```

记录实际生效的配置来源。不得绑定 `0.0.0.0`。

### 5.2 Streamable HTTP

FastMCP 端点通常为 `/mcp`，以服务日志为准：

```bash
MCP_INSPECTOR_SECRET_STORE=memory \
  mcp-inspector --cli --transport http \
  --server-url http://127.0.0.1:8900/mcp \
  --header "Authorization: Bearer ${CYGNUSX_HTTP_TOKEN}" \
  --method initialize

MCP_INSPECTOR_SECRET_STORE=memory \
  mcp-inspector --cli --transport http \
  --server-url http://127.0.0.1:8900/mcp \
  --header "Authorization: Bearer ${CYGNUSX_HTTP_TOKEN}" \
  --method tools/list
```

随后完成一个只读 `tools/call`。记录 HTTP 状态、Content-Type、JSON-RPC 错误、业务 `success` 和耗时。HTTP 2xx 只能证明 HTTP 层成功，不能代替业务成功。

### 5.3 SSE 和负向安全测试

仅在代码和启动日志仍明确支持 SSE 时测试 `/sse`；SSE 与 Streamable HTTP 分开判定。至少验证：

| 用例 | 预期 |
|---|---|
| 无 Authorization | 401/403 或等价认证失败 |
| 错误 HTTP Token | 认证失败 |
| 平台 API Key 代替 HTTP Token | 认证失败 |
| `host=0.0.0.0` | 启动拒绝 |
| Token 少于 32 字符 | 启动拒绝 |
| 写工具伪造 `user_confirmed=true` | 不执行写操作 |

负向用例不得触发真实写业务。

## 6. 工具描述审计

以外部客户端实际 `tools/list` 为全集，逐项收集：

1. `tools.yaml` 的同名描述。
2. Python 函数位置、docstring、decorator 显式描述。
3. Server 运行时工具对象描述。
4. 外部客户端描述。

分类规则：

- `missing`：无条目或描述缺失。
- `empty`：空字符串。
- `whitespace`：只有空白。
- `vague`：有文字但无法说明用途、关键输入、返回内容或重要限制。
- `valid`：与函数行为一致，能帮助模型安全选择。
- `transport_missing`：进程内有描述，但外部客户端没有取得。

输出 `description-audit.tsv`：

```text
tool_name  group  module  function_location  yaml_description  yaml_state
runtime_description  client_description  docstring  explicit_description
classification  reason  evidence
```

重点核对当前实际全集中的以下历史缺失工具，不得假定它们仍是唯一缺失项：

```text
cygnusx_list_tasks, cygnusx_get_task, cygnusx_get_task_progress,
cygnusx_get_task_logs, cygnusx_cancel_task, cygnusx_get_task_dag,
list_workspace_files, search_workspace_files, cygnusx_list_files,
cygnusx_get_file_tree, cygnusx_list_directories,
cygnusx_get_task_outputs, cygnusx_read_file_content
```

验证描述同步规则：有效运行时描述保持原值；空/空白描述只能使用同名 YAML 非空描述补齐；YAML 缺失时依据函数行为编写准确描述；禁止跨工具映射；注册缺失只告警且不改变原启动策略。工具名称、input schema、默认参数、返回结构和权限必须与基线一致。

## 7. Prompts 和 Resources

### 7.1 Prompts

`prompts/list` 以实际返回为准，当前预期包括：

```text
new_analysis
interpret_results
optimize_in_sandbox
download_and_analyze
troubleshoot_task
```

每个 Prompt 至少执行一次 `prompts/get`，记录参数 schema 和生成文本。重点检查参数插入、模板注入、确认门提示，以及 `download_and_analyze` 对 GSE/GSM 是否先核对 ENA/SRA run 后再使用合法 SRA accession。

### 7.2 Resources

当前预期的 4 个只读 URI：

```text
cygnusx://flows/catalog
cygnusx://user/storage
cygnusx://tasks/{task_id}/outputs
cygnusx://reports/{report_id}
```

分别执行一次 `resources/read`。没有合法 task/report 时记录业务前置条件或平台错误，不伪造生产 ID；区分 JSON、HTML、错误对象和 HTTP 状态。

## 8. Agent 实际加载范围

当前预期检查 19 个 Agent：

```text
agent-router, agent-general, agentteams-manager, agent-rnaseq,
agent-atacseq, agent-scrna, agent-scrna-upstream,
agent-scrna-integration, agent-scrna-advanced, agent-code,
agent-explorer, agent-viz, agent-data, agent-qc, agent-delivery,
agent-cloud-ops, shania, agent-mcp-builder, agent-skill-builder
```

不能只看 `mcp_ids`，必须取证：

```text
Agent YAML
  → tool_packs
  → research.mcp_ids / mcp_tools 白名单
  → mcp_servers 是否存在且 is_enabled
  → capability / case mode / 用户权限裁剪
  → AgentService.assemble_context
  → 最终发给模型的 function/tool 名称、描述和 schema
```

输出 `agent-tool-loading.tsv`：

```text
agent  research_bound  biothings_bound  research_whitelist_count
biothings_whitelist_count  server_enabled  excluded_by_capability
final_model_tool_count  final_research_count  final_biothings_count
dynamic_skill_count  evidence  notes
```

必须回答 19 个 Agent 是否都绑定两个 Preset、36 个科研数据库工具是否都进入最终上下文、哪些被裁剪、最终数量是否过载，以及按领域拆分 Tool Pack 的具体建议。不得批量修改绑定。

## 9. 17 项数据库资源

逐项做一个最小公开只读请求，记录 MCP 工具、参数、HTTP 状态、Content-Type、MCP 错误、业务 `success`、空结果、HTML、GraphQL `errors` 和证据路径。资源全集：

```text
MyGene, MyVariant, MyChem, Ensembl Plants, Gramene, Dfam,
Expression Atlas, Single Cell Expression Atlas, STRING, Europe PMC,
ClinVar, Open Targets, UniProt, InterPro, RCSB PDB,
AlphaFold DB, Reactome
```

输出 `provider-status.tsv`：

```text
resource  implemented  mcp_tool  transport  tested_at_utc
http_status  content_type  mcp_result  business_success
empty_result  html_response  graphql_errors  failure_kind evidence notes
```

状态只能是：

- `implemented_unverified`：代码存在但无真实 MCP 调用证据。
- `live_success`：真实 initialize/list/call 完成且 HTTP、协议、业务均成功。
- `live_failure`：真实 MCP 到达资源但明确失败，有根因证据。
- `untested`：尚未请求。
- `not_implemented`：没有注册能力，例如当前 STRING。

特别区分：数据库直连不等于 MCP 成功；HTTP 2xx 不等于业务成功；HTML 错误、GraphQL errors、空结果、鉴权失败、参数错误分别记录；不得下载 FASTQ、矩阵、结构大文件或运行分析。

推荐最小查询（必须先以实际 schema 校验）：

```text
MyGene: TP53 + human, limit=1
MyVariant: rs121913529 + hg38, limit=1
MyChem: 一个公开化合物标识符, limit=1
Ensembl Plants: 明确物种和稳定 ID
Gramene: 短字面查询, limit=1
Dfam: 家族 accession 或短名称
Expression Atlas / Single Cell Expression Atlas: 目录 limit=1
Europe PMC: TP53, limit=1
ClinVar: 公开检索词, limit=1
Open Targets: ENSG00000141510 或公开疾病 ID
UniProt: P04637, 限制字段
InterPro: IPR000719 或 P04637
RCSB PDB: P04637, limit=1
AlphaFold DB: P04637, 仅模型元数据
Reactome: 公开 stable ID
STRING: 标记 not_implemented，不自行造工具
```

## 10. 失败分类

所有失败写入 `failures.ndjson`，每行至少包含：

```json
{"time_utc":"...","phase":"stdio|http|description|agent|provider","transport":"...","operation":"initialize|tools/list|tools/call|resources/read","target":"脱敏名称","error_type":"timeout|auth|bind_denied|schema|html|graphql|business|network|unknown","status_code":null,"message":"脱敏错误","evidence":"相对路径","reproducible":true}
```

至少区分 `startup_slow`、`stdout_pollution`、`stdio_pipe_or_thread`、`protocol_mismatch`、`missing_dependency`、`auth_failed`、`loopback_bind_denied`、`platform_api_unavailable`、`provider_http_error`、`provider_html_error`、`provider_graphql_error` 和 `provider_empty`。

## 11. 判定标准

只有同时满足以下条件，才能写“外部 MCP 验收通过”：

- 至少一个真实外部传输完成 `initialize → tools/list → 只读 tools/call`。
- 外部 `tools/list` 每项描述非空，缺失项有逐项原因。
- 工具名、输入 schema、默认参数、返回结构和权限与基线一致。
- Prompts/Resources 有列表及代表性读取证据，或有明确业务前置条件和错误证据。
- 19 个 Agent 有实际最终工具集合证据，不是只读 YAML。
- 17 项资源全部有明确状态，未测试和未实现不能写成功。
- 认证、回环和确认门负向测试通过。
- 证据已脱敏，带 UTC 时间、版本和校验和。

以下只能判定为“部分验收”或“未完成”：只有启动日志、只有 YAML、自校验或进程内 SDK；只有数据库直连；只有 HTTP 2xx；没有最终 Agent 工具清单；或资源缺少调用时间和证据路径。

## 12. 最终报告格式

请按以下顺序返回 Markdown 报告：

1. 测试环境、权限、版本和代码 SHA。
2. 结论摘要：通过、部分通过或未完成。
3. STDIO 的 initialize/list/call、stdout/stderr 和根因。
4. HTTP/SSE 的监听、Token、认证、initialize/list/call 和负向测试。
5. 描述修复前后对照表及 `description-audit.tsv` 摘要。
6. Prompts/Resources 列表和读取结果。
7. 19 个 Agent 的绑定、白名单、最终数量和建议。
8. 17 项资源状态表。
9. 失败分类、重现条件、待办和证据清单。

必须明确区分：

```text
代码已实现
进程内 SDK 可用
外部 MCP 传输可用
平台 REST 可用
provider 真实业务成功
```

这五种状态不能合并成“已接通”。

## 13. 禁止事项

- 不自动部署生产、删除服务或修改生产数据库。
- 不批量解绑 Agent，不修改 `mcp_ids` 作为测试捷径。
- 不修改工具名、schema、默认参数、返回结构或权限来让测试通过。
- 不把延长超时单独当作修复。
- 不绑定 `0.0.0.0`、移除认证或复用平台 API Key 作为 HTTP Token。
- 不伪造人类确认凭证，不用 `user_confirmed=true` 绕过确认门。
- 不压测 provider，不下载大文件。
- 不把 mock、启动自检、数据库直连或进程内检查作为外部传输证据。
