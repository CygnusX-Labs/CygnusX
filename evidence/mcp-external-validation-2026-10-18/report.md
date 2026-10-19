# CygnusX MCP 外部验收报告

测试时间：初次外部验收为 2026-10-18 UTC 14:26–15:14；本轮描述/四传输/完整测试复核为 UTC 23:46–23:49。测试 Agent：Codex CLI（具备本机 STDIO/loopback 权限的外部验收流程）。HEAD 为 `7c028af698762710f5d0b0dc632a060226ac298a`；本轮工作树基线、MCP tracked diff 哈希及运行时版本见 `baseline.json`。工作树包含未提交的 MCP 描述同步修复及测试改动；本报告不把这些改动写成已部署生产。

结论：**部分验收**。协议传输、安全负测、111项工具描述与四面契约均有证据；本轮在隔离平台身份下，MCP→平台 REST→ClinVar正向链经STDIO、Streamable HTTP、SSE成功，另对16项既有provider经STDIO MCP尝试，15项业务成功、Expression Atlas bulk目录超时。STRING固定v12.5 REST适配器已加入工作树并取得直接provider样例，但尚未验证MCP→认证平台REST链。19个Agent已导出真实隔离DB上下文（快照早于STRING工具加入），另测一个受限server上下文及scope拒绝。测试DB停在`dwnlease03`；Resource业务资产读取、cache miss范围、逐Agent Provider实发集合、模型级Prompt注入和生产部署仍未完成。能力去重矩阵见`capability-dedup-matrix.tsv`，截图线索与当前源码证据明确分开。

## 环境与权限

MCP venv 使用 Python 3.13.12、FastMCP 3.4.4；HTTP/SSE 传输绑定`127.0.0.1`。本轮另启用loopback隔离平台进程、Postgres/Redis测试容器及普通测试用户；平台Key和MCP HTTP Token分离，凭据值不入证据。测试数据库停在`dwnlease03`，更高的未提交下载迁移失败，未改动该迁移。MCP→平台请求通过`X-Request-ID`关联；provider走固定HTTPS host。身份范围与限制见`isolated-platform-identity-2026-10-19.json`。

## STDIO

使用 MCP Python Client `ClientSession` 作为真实外部 MCP 客户端，启动仓库 venv 的 `main.py` 子进程。initialize 成功，协商协议 `2025-11-25`，ServerInfo `CygnusX 3.4.4`，耗时约 2625 ms。`notifications/initialized` 由 SDK initialize 流程发送。该历史基线 tools/list 返回109项、无cursor；STRING工具加入后的当前111项四面清单见下方及`current-*-tools.json`。prompts/list 返回5项；resources/list 返回2个静态Resource，另有2个Resource Template（合计4个资源入口）。原始协议客户端结果在`stdio-probe.ndjson`，server stderr在`stdio-probe.stderr`。stderr有启动banner/日志，stdout由MCP客户端解析为协议响应，未观察到日志污染。早期Inspector STDIO CLI参数解析不兼容，故STDIO证据采用SDK客户端；Inspector CLI对HTTP/SSE可用。

历史基线中的只读 `cygnusx_list_flows {}` 调用到达工具，但因缺少平台令牌失败；四项早期 resource read 也因未认证失败。隔离测试身份建立后的更新结果见下方“Prompts 与 Resources”及`resources-platform-chain-2026-10-19.ndjson`。

## Streamable HTTP 与 SSE

早期Streamable HTTP监听`127.0.0.1:8900/mcp`、SSE监听`127.0.0.1:8901/sse`，Inspector initialize与tools/list均成功（当时各109项）；当前两种传输tools/list各111项，见`current-streamable_http-tools.json`、`current-sse-tools.json`。早期HTTP prompts/list返回5项、resources/list返回2项。Streamable HTTP的`cygnusx_list_flows`到达工具，dummy平台地址连接失败并以业务`success=false`返回，证明当时MCP到工具边界可用但平台REST不可用。

无 Authorization、错误 Token、平台 API Key 代替 MCP Token 均返回 HTTP 401（响应见 `no-auth.headers`、`wrong-token.headers`、`api-key.headers`）。`host=0.0.0.0` 启动被 loopback 校验拒绝；少于 32 字符的 HTTP Token 启动被拒绝，stderr 证据分别为 `nonloopback.stderr`、`short-token.stderr`。在隔离 dummy endpoint 的 MCP 客户端测试中，分析提交工具收到 `user_confirmed=true` 后返回 `success=false`，没有请求平台确认或提交接口；测试通过。没有调用任何真实写工具。初次 SSE 测试 helper 错用 POST 得到 405；随后按 SSE 契约使用 GET 验证未认证为 401、独立测试 Token 为 200 `text/event-stream`，见 `sse-security-probe.json`。服务已停止。

## 工具描述与协议对象

修复前保存的 STDIO 清单包含 109 个工具，旧审计表有 109 条结构化 TSV 记录、13 列。首次描述整改按原审计理由逐项补充了 12 个模糊描述：`cygnusx_list_runs`、`cygnusx_get_run_status`、`cygnusx_get_run_logs`、`cygnusx_verify_artifact`、`cygnusx_confirm_run_plan`、`cygnusx_preview_analysis`、`atac_seq_status`、`cygnusx_gene_search`、`cygnusx_chem_search`、`cygnusx_genome_sequence`、`cygnusx_plant_get`、`cygnusx_expression_studies`；当时该项整改仅改description，工具名与schema未变。当前`description-changes.tsv`/`before-after-contract-diff.json`已重算为2026-10-18历史清单至当前累计工作树的差异，因此另含后来ClinVar typed-ID的description与schema改动，以及其他既有工作树schema变化；详见本报告ClinVar后续记录，不能把累计差异全归因于首次描述整改。修复前没有保存handler映射，因此handler绑定未能做独立历史前后比较，不能把这一项写成已验证。

描述同步修复已在当前工作树完成，核心实现位于 `mcp-server/tools/__init__.py`，首轮12条实际生效描述来自工具 docstring，并同步到 `mcp-server/tools.yaml`。空或空白运行时描述仍按精确工具名使用同名 YAML 描述；无映射时只告警并带源码位置，不阻断启动。随后加入两个 STRING 工具，当前重新真实采集 in-process、STDIO、Streamable HTTP、SSE 四组完整 tools/list，每组111项；`schema-diff.json` 对比四组的名称、`inputSchema`、description 均无差异，当前外部传输均返回非空描述。原始规范化清单为 `current-runtime-tools.json`、`current-stdio-tools.json`、`current-streamable_http-tools.json`、`current-sse-tools.json`，采集命令见 `capture_four_surfaces.py`。历史109项基线至当前工作树的累计契约差异见 `before-after-contract-diff.json`，包含新增两个STRING名称及后来ClinVar等schema变化，不能全部归因于首轮描述修复。

修正说明：旧审计表未经 TSV 转义地写入多行 docstring，按物理行统计得到 471 行，不能支撑旧报告所称的 46 项 `vague`。现已基于当前 runtime `tools/list`、`tools.yaml` 和源码 AST 重建表格；`rebuild_description_audit.py` 可复现，解析校验为111条记录、13列，其中99项为`valid`、12项为`vague`，无缺失、空或纯空白描述。`vague` 表示描述非空但用途仍需人工确认，不等同于缺失描述。首轮修复的12条模糊描述仍是原有12项；两条新增STRING描述也通过审计。描述回归测试覆盖 YAML fallback、空白 fallback、显式描述保留、精确名称映射、禁用工具组和全量 schema 不变。当前工作树外部MCP完整套件72/72、平台API/research preset/双表面定向回归71/71，Ruff检查及相关服务/preset strict mypy通过。研究桥接修复定向回归历史记录为13/13；Seqout使用确定性本地adapter fixture，不构成provider live验收。历史失败摘要保留在`isolated-test-results.txt`；旧协议清单保存在`stdio-tools-list.ndjson`、`http-tools-list.ndjson`和`sse-tools-list.json`，当前四面新清单见`current-*-tools.json`。

## Prompts 与 Resources

Prompts：`new_analysis`、`interpret_results`、`optimize_in_sandbox`、`download_and_analyze`、`troubleshoot_task`，均执行过 prompts/get。`download_and_analyze` 明确要求 GSE/GSM 先核对 ENA/SRA run，再使用已核对 run accession；符合委托要求。**待部署验收问题（未关闭）：** 初次采集的 `prompts-resources.ndjson` 包含 Python `subprocess.run(find, ...)` 示例，与 Agent 不获得 shell 的边界冲突；作为 `agent_shell_boundary_violation` 保留在 `failures.ndjson`。当前工作树中的 `mcp-server/prompts/workflows.py` 已移除该示例，改为通过 `cygnusx_list_files` / `cygnusx_read_file_content` 发现和读取有权限的文件；不可见时要求停止。该修复只在工作树，尚未部署，也未通过部署后 prompts/get 复核及模型遵从测试；该历史风险仍待部署验收，不代表已发现 shell 执行。

**Prompt 参数的语义级注入验收尚未测试：** `prompts-resources.ndjson` 中五个常规 prompts/get 使用普通参数，没有注入探测。另有4项本地及 STDIO、Streamable HTTP、SSE 测试向 `optimize_in_sandbox` 传入引号、换行、`{{...}}` 模板标记和指令式文本，但只检查 JSON 字符串转义及渲染边界；这属于参数序列化测试，不是恶意 Prompt 注入验收，也没有把结果交给模型观察其指令遵循或工具行为。故恶意参数是否改变模型行为、是否诱发未授权工具调用，以及部署后的模板/参数处理均尚未验证。相关记录见 `prompt-transport-safety-2026-10-19.ndjson` 和 `prompt-parameter-safety-test.txt`；不得据此宣称 Prompt 注入验收通过。

静态 Resource：`cygnusx://flows/catalog`、`cygnusx://user/storage`；Template：`cygnusx://tasks/{task_id}/outputs`、`cygnusx://reports/{report_id}`。早期四项 read 使用非生产占位 ID 或静态 URI，因未认证返回 JSON 错误。2026-10-19 隔离身份复验中，外部 STDIO MCP→平台 REST 对`cygnusx://flows/catalog`返回结构化 JSON（2项）；`cygnusx://user/storage`被平台以缺少所需权限范围拒绝。后者是实际授权拒绝，不是成功读取；两个 task/report 模板仍未以真实隔离业务资产验证。逐项结果见`resources-platform-chain-2026-10-19.ndjson`。

## 19 个 Agent

**隔离复验更新（2026-10-19，以下较早段落中的“无真实上下文”状态已过期）：** 已在隔离DB中对19个Agent执行真实上下文装配并导出脱敏快照，逐Agent工具数/schema字节数见`agent-loading-summary.tsv`，完整工具和裁剪信息见`agents-runtime-2026-10-19/`。范围72–98工具/Agent。汇总TSV现有12列，含Agent身份、context_ref、绑定/启用preset、BioThings/Research Data计数、schema字节数、未测token/allowlist标记及证据路径；schema字节数不是token估算。模型未调用，因此这些是最终AgentContext集合，不是19次实际Provider HTTP payload。重要限制：这些隔离快照生成于STRING两工具加入之前，不能证明新增工具已通过19个Agent的用户权限裁剪。额外platform-only上下文有16项工具、BioThings/Research Data均为0且事务已回滚；flows-only身份经MCP调用Research Data工具返回403、provider未触发。这只验证一个绑定与API scope，不覆盖所有capability/case策略。证据见`agent-general-restricted-context-2026-10-19.json`和`agent-general-restricted-mcp-invoke-2026-10-19.json`。

静态配置盘点见 `agent-tool-loading.tsv`。19 个已启用 Agent 的 YAML 均显式包含 `research` tool pack。`research.yaml` 显式列出两个 preset UUID，BioThings 白名单 10 项，Research Data 白名单 26 项。静态配置不能证明数据库中的 preset `is_enabled`、用户/能力/case 裁剪结果或最终模型 function 集合；这些列标记为未验证。未更改任何 Agent 绑定。

历史预检记录（隔离运行前，已被本节首段复验更新取代）：当时只有静态`runtime-snapshot-2026-10-19.json`，无法证明数据库preset开关、运行时裁剪或最终Provider工具集合。随后已在隔离DB真实装配19个Agent，并导出脱敏context工具清单及裁剪原因；快照/导出代码回归10/10，日志见`agent-tool-snapshot-tests-2026-10-19.txt`。当前仍未执行19个Agent的模型调用，故实际发给Provider的最终HTTP payload未逐Agent验证；token估算也没有测量。能力裁剪建议以Agent用途拆分research preset pack，但当前没有批量更改绑定。

## Provider 状态

**隔离MCP平台链更新（2026-10-19，取代下文“全部未经平台MCP验证”的历史口径）：** 当时16项已实现provider均经外部STDIO MCP→隔离认证平台REST尝试一次，15项业务成功，Expression Atlas bulk目录超时；ClinVar与InterPro另在桥接修复后成功复测。逐项工具、脱敏输入、状态和摘要见`provider-mcp-platform-2026-10-19.ndjson`及`provider-mcp-platform-followup-2026-10-19.ndjson`，对应平台request ID在相邻日志。之后STRING固定v12.5 REST适配器在工作树实现，并取得外部FastMCP进程内adapter直连provider样例；其MCP wire及认证平台链仍未测。cache状态未完全审计：除了Atlas目录，代码中未发现应用结果缓存；Atlas bulk首请求超时、single-cell目录在本隔离API进程首次请求成功。Resource业务读取、Atlas其它功能及来源版本覆盖仍不完整。

17项资源交付状态（工作树代码/单样例链路/部署证据分列；`passed_live`只表示该行指定调用样例通过，不表示全库或全部子能力通过）：

| 资源 | 当前实现/入口 | 外部MCP→隔离平台样例 | 部署状态 | 未闭合范围 |
|---|---|---|---|---|
| MyGene | 已实现：`cygnusx_gene_*` | `passed_live`，1个样例 | 未验证 | 物种/多匹配/投影的完整矩阵与缓存miss |
| MyVariant | 已实现：`cygnusx_variant_*` | `passed_live`，1个样例 | 未验证 | assembly矩阵、GET/POST语义端到端和缓存miss |
| MyChem | 已实现：`cygnusx_chem_*` | `passed_live`，1个样例 | 未验证 | 盐型/异构体/canonical身份边界 |
| Ensembl Plants | 已实现：`cygnusx_genome_*` | `passed_live`，1个lookup样例 | 未验证 | 植物Compara、region/sequence/VEP覆盖 |
| Gramene | 已实现：`cygnusx_plant_*` | `passed_live`，1个样例 | 未验证 | taxonomy映射及版本化路径覆盖 |
| Dfam | 已实现：`cygnusx_te_*` | `passed_live`，1个样例 | 未验证 | classification/clade/raw范围与HMM资产 |
| Expression Atlas | 已实现：`cygnusx_expression_*` | `failed_live`，bulk目录超时 | 未验证 | bulk/sc目录与manifest分别验收；定量未验收 |
| Single Cell Expression Atlas | 已实现：`cygnusx_expression_*` | `passed_live`，目录样例 | 未验证 | manifest、定量与完整cache miss语义 |
| STRING | 已实现工作树固定v12.5 REST适配器：`cygnusx_string_resolve`、`cygnusx_string_network`，同属research-data preset/API | `implemented_unverified`；直接provider样例成功，未通过认证平台REST | 未验证 | MCP→平台正向链、缓存、Agent授权及部署；工具只覆盖有界身份映射和分类型网络查询 |
| Europe PMC | 复用`europe_pmc_search`；新增详情/注释入口 | `passed_live`，文章样例 | 未验证 | 全文授权、注释与来源锚点 |
| ClinVar | 已实现：`cygnusx_clinvar_*` | `passed_live`，search/get样例；修复后VCV复测 | 未验证 | RCV/SCV/Variation全链路样本及分类/提交证据覆盖 |
| Open Targets | 已实现：`cygnusx_target_*` | `passed_live`；TP53响应核验`errors=0`、`partial=false` | 未验证 | GraphQL子查询字段/证据类型覆盖 |
| UniProt | 已实现：`cygnusx_protein_*` | `passed_live`，1个样例 | 未验证 | isoform、FASTA版本/hash、IDmapping轮询 |
| RCSB PDB | 已实现：`cygnusx_structure_*` | `passed_live`，1个样例 | 未验证 | entity/chain、映射及实验结构分类 |
| AlphaFold DB | 已实现：`cygnusx_structure_prediction` | `passed_live`，1个样例 | 未验证 | isoform/版本/文件权限与PAE资产 |
| Reactome | 已实现：`cygnusx_pathway_*` | `passed_live`，pathway样例 | 未验证 | Analysis与Content、release/物种投射分别验证 |
| InterPro | 已实现：`cygnusx_domain_*` | `passed_live`，修正accession后复测 | 未验证 | family/domain/site与序列扫描分界 |

逐项attempted、缓存状态、transport/platform/provider验证标记及具体证据路径以`provider-verification-matrix.tsv`为准；资源名称、工具和HTTP摘要见`provider-status.tsv`。17项均已有代码实现，其中16项的指定样例经MCP→平台REST尝试，15项业务成功、Atlas bulk超时；STRING另有provider直连样例，但未验证平台链。`deployed`一列全为“未验证”，因为本轮只使用隔离工作树与隔离服务，没有生产发布证据。

现有能力去重结论（与截图线索分开）：隔离DB的19个Agent快照均绑定`cygnusx-platform`、`cygnusx-biothings`、`cygnusx-research-data`、`seqout`和`cygnusx-tools`五类server，未出现名称为`ensmbl`或`go-server`的绑定；这不证明生产库没有旧绑定。`ensmbl`和`go-server`的外部server ID/transport只能由生产管理面盘点，当前不得改名、删除或批量解绑。植物查询复用`cygnusx-research-data`服务，不新建同义server。Europe PMC保留平台原`europe_pmc_search`，详情/注释走新增的受限工具；不另建第二个通用搜索入口。完整矩阵见`capability-dedup-matrix.tsv`。

Open Targets内容核验补充：隔离MCP链返回HTTP 200，GraphQL `errors`为0、`partial=false`，TP53目标搜索命中71条中的首条`ENSG00000141510`，见`provider-opentargets-content-2026-10-19.json`。该项只验证固定搜索模板的一条正向响应，不替代其它GraphQL字段或关联证据子能力测试。

早期provider直连记录（与上方隔离MCP平台链结果分层）：STRING适配器实现前，另外16项资源曾做有限的**provider直连HTTPS adapter探测**，14项返回成功envelope，Ensembl Plants和Expression Atlas bulk超时。首批五项原始记录见`provider-direct-smoke-2026-10-19.ndjson`，后续见`provider-direct-followup-2026-10-19.ndjson`。这些请求没有经过FastMCP或平台REST鉴权，部分大响应受3000字节预算裁剪，也未核验上游缓存；只能证明adapter直连样例，不能替代当前表格中的MCP→平台链路结果。

直连复测发现并修复两项 provider 路由问题：Reactome 版本端点需 `Accept: text/plain`，Europe PMC 文章详情应使用 `/article/{source}/{id}` 并请求 `resultType=core`；内置 preset 和外部 FastMCP adapter 已同步修复，内部路由/Accept测试与外部双表面合同测试通过，修复后两项直连返回成功 envelope。Dfam、Atlas、Single Cell Atlas、InterPro 与 Open Targets 均使用固定 host；Open Targets 使用 v4 GraphQL 端点，partial GraphQL errors 会显式返回 `partial=true` 与 warning。Atlas bulk/sc 目录采用独立10 MiB响应上限、25秒总预算和每进程/事件循环6小时目录缓存，来源与上游列表变化仍需观测。原官方`https://mcp.string-db.org/`探测完成真实Streamable HTTP initialize、tools/list（17项）及`string_resolve_proteins`/`string_help(version_and_citation)`调用；TP53/taxon 9606映射成功，帮助工具报告数据版本v12.0。官方API版本页列v12.5，托管MCP页面说明服务仍在开发且自动提供最新版本；因此官方MCP没有被注册。后续已实现固定版本的STRING REST窄适配器：内部 `research_data_service.py` 与外部FastMCP bridge均新增`cygnusx_string_resolve`/`cygnusx_string_network`，REST host固定为`https://version-12-5.string-db.org/api/tsv`，显式species/taxon、先映射再查网络、分开functional/physical/regulatory、禁用自动扩展节点、结果有界并限速。真实直连样例解析TP53人类ID，physical首个伙伴为SIRT1，regulatory为TP53→MDM2；还验证TSV返回格式。方向/partner投影单测及HTTP200 HTML/超大响应拒绝测试通过。证据`string-rest-direct-probe-2026-10-19.json`仅代表进程内FastMCP→外部provider直连；未通过MCP wire或认证平台REST，cache与部署未验证。17项资源状态见`provider-status.tsv`，验证层级见`provider-verification-matrix.tsv`。

## 失败分类与待办

**当前状态更正（2026-10-19）：** 下文有关“Agent/provider均未发起”的内容是本轮隔离身份建立前的历史事实。当前Agent快照和provider尝试已完成，具体以本节前两条复验更新和独立证据文件为准；历史`attempted=false`记录仍保留其原始含义。当前完整外部MCP套件72/72，平台research preset/双表面定向回归66/66。R3的身份/API正向链与R5的19个上下文快照已部分完成；该快照早于STRING工具加入。剩余真实Resource资产、STRING平台正向链、全provider缓存miss、逐Agent实发Provider payload、模型级Prompt注入及生产部署。

已复现：一次实际 STDIO `cygnusx_list_flows` 请求到达 MCP 工具后因平台 token 缺失返回认证错误（`attempted=true`, `platform_auth_missing`）；HTTP 只读调用的 `platform_api_unavailable`（dummy endpoint）；认证负测 401；非 loopback 和短 Token 启动拒绝。Agent/provider 未发起条目使用 `attempted=false`、`transport=not_started` 和 `error_type=not_attempted_identity_unavailable`；这些不是 MCP 请求，也不表示实际请求遭认证拒绝。其后对16项已实现provider进行直连adapter抽样，14项返回成功envelope，Ensembl Plants与Expression Atlas bulk超时；另对STRING官方独立MCP完成协议/只读调用，但未接入CygnusX，具体传输边界见上一节及独立NDJSON，不改变Agent/MCP平台链的未验收状态。Prompt shell 示例仅在当前工作树修复，部署和运行时仍待验证；STDIO、Streamable HTTP、SSE 参数渲染边界连同本地测试共 4 项通过；模型运行时语义级 prompt injection 与工具行为仍未测试。没有发生 `stdout_pollution` 或握手失败。

历史测试汇总（部分子项完成时）：当时MCP全套为64/64、研究数据/API/双表面回归56/56、聊天运行时/golden/tool manifest 45/45、Provider边界23/23。随后完整MCP套件曾为67/67；STRING加入后当前工作树完整套件72/72。平台research preset/双表面定向回归66/66，Ruff与相关service/preset strict mypy通过。四组当前111项schema一致；修复前handler映射未留存，属于历史证据缺口。Prompt特殊字符测试覆盖in-process及三种外部传输共4项，只验证渲染边界；模型运行时语义级prompt injection与工具行为仍未测试。当前隔离业务、provider、Agent证据分别见本报告上方章节，不能再以早期“无测试身份/无上下文”描述当前状态。证据文件SHA-256见`checksums.txt`。

2026-10-19 响应预算补充：BioThings 与 research-data service 的 JSON、文本/FASTA 响应改为流式读取，超过字节上限时停止读取并关闭响应，避免先将完整上游响应缓冲进内存。相关 BioThings/research preset、Research Data API 和双表面契约回归为64/64通过，Ruff 与 mypy 通过；日志见`provider-streaming-budget-tests-2026-10-19.txt`，修改后源文件哈希见`provider-streaming-budget-source-hashes-2026-10-19.txt`。该验证是带 MockTransport 的响应预算测试，不代表 provider live 或平台业务调用。

2026-10-19 MyVariant assembly/HTTP method 补充：普通 DSL 搜索使用 GET；带显式 `scopes` 的 identifier resolve 使用 form POST `/query`。对同一 rs699 的直接 adapter GET/POST 探测均返回 `chr1:g.230710048A>G`，并含所选 `dbsnp.hg38` 字段；`assembly=hg38` 对 query 结果有效。对照发现 `hg38=true` 在该 rsID query 中未切换坐标，该参数仅按官方 FAQ 示例用于区间查询。服务不做 liftover。测试日志与脱敏结果见`myvariant-get-post-probe-2026-10-19.json`、`provider-direct-followup-2026-10-19.ndjson`；此探测不经过 FastMCP、认证平台 REST 或缓存 miss 证明。

2026-10-19 ClinVar VCV 补充：使用 NCBI E-utilities `efetch.fcgi?db=clinvar&rettype=vcv&id=VCV000014206` 获取一次公开 XML（HTTP 200，10,524 bytes，根节点 `ClinVarResult-Set`），并通过实际 `execute_research(cygnusx_clinvar_get)` 服务入口生成 1,516-byte envelope，解析出子节点 `VariationArchive` 的 accession/version/Variation ID、分类、review status 与 ClinVarSubmissionID。由于响应预算，分类/review 子集显式标记 `projection.truncated=true`；外层 envelope 未超限且核心记录身份仍存在。结果记录见`clinvar-vcv-contract-probe-2026-10-19.json`。这仅验证一个VCV样例的上游契约及本地service；没有通过MCP、平台REST、Agent或缓存链，也未覆盖RCV/SCV/Variation/Allele输入。

2026-10-19 ClinVar VCV adapter 实现复核：内置路径现使用流式 2 MiB 上限 EFetch XML 请求，拒绝 DTD/ENTITY，并验证返回 VariationArchive accession/显式版本与请求一致；按记录投影 VCV 版本/Variation ID、三个分类域、review status 和 submission evidence。投影先按输出预算裁剪并标明受限 sections，避免通用 envelope 预算器丢弃全部结果。外部 XML 直连 fallback 同样拒绝 DTD/ENTITY。平台定向回归63/63、外部 MCP 全套64/64、Ruff 与 mypy 通过，输出及源文件哈希见`clinvar-vcv-tests-2026-10-19.txt`与`clinvar-vcv-source-hashes-2026-10-19.txt`。这不代表 RCV/SCV/Allele 类型覆盖或平台业务链通过。

上述 MyVariant adapter 和响应预算改动合并后的研究/BioThings/API/双表面组合回归为65/65通过，命令见`myvariant-get-post-tests-2026-10-19.txt`。这是定向本地回归，不替代 MCP 全量套件重跑。

2026-10-19 ClinVar typed-ID 后续：`cygnusx_clinvar_get`保留旧`vcv_accession`调用，新增`identifier`+`identifier_type`，支持VCV、RCV、SCV、Variation ID；Allele ID明确拒绝且不转换成Variation ID。RCV通过`rettype=clinvarset`读取，SCV通过JSON ESearch `[clv_acc]`解析Variation UID后读取VCV并校验SCV accession/version，Variation ID使用`is_variationid=true&from_esearch=true`并校验返回VariationID。一次公开service-adapter直连样例中，四种支持类型均返回匹配记录，详见`clinvar-typed-identifiers-2026-10-19.json`。当时回归与历史schema差异见`clinvar-typed-id-mcp-suite-2026-10-19.txt`和`before-after-contract-diff.json`。该段记录的是adapter实现阶段；之后ClinVar VCV样例已纳入三种MCP传输的隔离平台正向链，见`platform-chain-positive-2026-10-19.json`。19个Agent上下文快照现已完成，但逐Agent Provider实发与全部类型/子能力仍待验证。

2026-10-19 STRING共享限速补充：临时隔离Redis上4个独立Python进程调用当前生产 `_string_rate_limit`，各获取2次名额；8次Redis占位的7个相邻间隔均为1001 ms。停掉Redis后 `execute_research(cygnusx_string_resolve)` 返回 success=false 及 ConnectionError，未发起provider HTTP。临时容器已移除，未接触平台Redis。证据见 `string-redis-multiprocess-2026-10-19.json` 和 `string-redis-multiprocess-probe-2026-10-19.py`。复跑脚本需先创建同名临时Redis，并按实际回环端口调整URL。这证明共享名额间隔和Redis故障拒绝，不证明名额到HTTP发包之间的调度间隔；STRING认证平台链及Agent授权仍未验收。
