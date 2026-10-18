# S3 Closure 增量实施报告

日期：2026-10-16。依据本轮 Runtime Optimization Plan 与配套 Prompt A；仅实施 S3，不启动 S4–S7。活动架构仍以 `ARCHITECTURE_DESIGN/CygnusX_download_architecture.md` 为准。

## 结论

本轮新增请求重验与调用方/协议安全策略投影，相关隔离用例通过。**G3 = PARTIAL_CODE / RUNTIME_BLOCKED**，不是 CODE_COMPLETE 或 PASS_WITH_EVIDENCE。网络硬预算、全链路历史投影等要求仍有未完成项。真实执行门禁、Agent 写门禁均保持关闭；人工下载尚未恢复。没有新下载器、任务引擎、审批系统或凭据库。

## 基线与保留矩阵

`evidence/download-s3-closure/` 保存 HEAD、完整 status、递归子模块状态与相关 tracked diff。新增/未跟踪文件不能由 tracked diff 完整覆盖，交接不得据此整文件恢复。工作区有大量先前与并行改动，本轮不 reset/clean/stash，不提交、推送、部署或安装依赖。

| 既有成果 | 本轮处理 |
|---|---|
| FileRegistry Task/source/SHA/size 与配额事务 | 保留，运行真实函数级回归 |
| Dataset reconcile 真实 Task 关联 | 保留，SQLite/临时真实文件回归 |
| 协议/方法约束与来源 manifest | 保留，不升级下载子模块或工具 |
| URL、FTP 展开、日志/Task 响应脱敏 | 保留并联合回归 |
| 人类确认/hash/TTL 与模型不可自批 | 不改存储、消费、哈希或身份来源 |
| 源码 transport / Agent 执行关闭 | 保留；策略投影不能授予权限 |

## 修改文件与红绿测试

1. `application/services/download_service.py::submit`：内部调用可修改已构造的 Pydantic 实例，原路径只检查协议，不能证明完整 URL 验证已执行。现在从模型数据重建副本，运行完整当前验证器，在目录、Task、队列及 transport gate 前拒绝不安全参数；返回固定 `DOWNLOAD_ARGUMENTS_INVALID`，不回显 Pydantic 原输入。确认 ID 原本为排除字段，Service 不承担确认消费；该重建不改已存确认参数或哈希。
2. `infrastructure/download/policy.py`：新增不可变 `TransportAdmission` 与 `describe_transport_admission(protocol, caller_kind)`。区分人工 JWT/module scope、Agent 可信委托/scope/人类确认、Worker 持久 Task owner/批准来源要求。协议逐项返回未认证或不支持，未知调用方增加身份缺失原因，全部 execute_allowed=false。此为只读策略分层，**尚未接入完整身份认证或运行证书消费**，不替代 REST 身份/既有 Gateway 授权，也不是 S5 Catalog 实现。参数只是标签，模型可填标签不代表可信身份。
3. `tests/unit/test_download_s3_closure.py`：先红测再修复，覆盖可变 DTO 的私网/签名 URL 拒绝及 10 协议×4调用方拒绝矩阵。

红测 `red-tests.txt`，42 failures；绿测 `green-tests.txt`，42 passed。重建副本不批量改历史 Task，不输出原始请求。

## 网络、FTP 与代理边界

| 后端 | 已有/新增代码约束 | 未证明的运行层边界 | 准入 |
|---|---|---|---|
| aria2 HTTP/HTTPS | URL syntax、协议、Service/Worker 重验 | DNS/CNAME、多结果、连接绑定、逐跳、代理实际出口 | BLOCKED |
| FTP | 同上及递归深度/条目/展开链接总量/超时 | 控制连接目标、PASV/EPSV IP和端口、主动模式/数据流 | BLOCKED |
| EBIDownload aws/ftp | 方法白名单、Task 前置重验 | Rust/wget 的实际连接、重试/转换后的总任务预算 | BLOCKED |
| OSS/TOS/OBS | provider/scheme/主机与查询限制 | 各 CLI 实际 endpoint、代理/重定向/流量及磁盘硬限 | BLOCKED |
| FTPS/Aspera/通用 S3/COS/云盘 | 不支持契约 | 无对应认证实现 | UNSUPPORTED/UI_ONLY |

`verify_resolved_addresses`/`verify_redirect` 仍只校验观察，不控制 CLI socket。当前 BinaryExecutor 未提供经认证的 egress 或代理隔离；不能把清理 HTTP_PROXY/预解析单独当网络隔离。不能开放任何后端，不能以纯函数测试冒充 DNS rebinding/FTP 数据通道阻断证据。

后续可信隔离必须约束整个进程树及 DNS、IPv4/IPv6、透明出口和显式代理；拒绝直连绕过，重定向每跳复核。FTP 要有受限被动端口和数据地址策略、禁主动外连，否则继续拒绝。部署这些策略需要独立获授权环境，不在本轮安装代理或改防火墙。

## 实时预算调查与设计边界

现有链路为前置验证 → 外部进程 → 等待退出 → 有界登记/配额结算。没有可信执行层的总接收字节计量与硬停止。源码 EBIDownload `--max-size` 在 `crates/ebidownload-cli/src/main.rs` 明确为 Prefetch only，平台仅接 aws/ftp，不能移用为当前方法硬预算；Rust 中 reqwest timeout 也不是任务总预算。aria2 和三云 CLI 的真实版本/help 未取得，不能虚构支持选项。

网络计量须统计所有文件、重试、断点和重定向实际接收字节；落盘计量须包括临时文件、SRA 转换和解压，不等同网络预算。可信网络层需要流式硬限；文件系统需 Task 范围硬配额且覆盖子进程所有写入路径。轮询目录大小、文件预估和登记扫描均不能证明绝对硬限。

数据库配额预留/结算/释放与 S4 的并发事务一致性耦合，本轮不新增平行 ledger。没有实际网络/文件系统 enforcement，因此未知长度、撒谎 Content-Length、chunked、多文件预算、磁盘满、Worker crash 的运行结果均 NOT_TESTED，协议保持 BLOCKED。

## 凭据、ToolTrace 与历史

原 URL/日志/API/Task 展示/确认/MCP 错误边界回归保留。现有 `core/security.py::encrypt_value` 无有效密钥时原样返回，不能作为本轮下载安全凭据存储保证；继续拒绝当前识别的签名 URL，不新增 vault。普通非敏感 query 不被统一删除，原执行数据与审批哈希不改。

Gateway 在 invocation 记录前做 capability schema 校验；但这不是所有 Chat/Node/ToolBridge/history 入口的全链路证明。对话事件、Node 回调、历史恢复、未知网站私有签名格式仍需完整审查，G3-07/I06 仅局部通过。未修改这些广泛共享历史路径，未清理真实用户数据。

历史治理方案：先在授权 owner 范围只读检测并记录脱敏统计/受限证据；响应端用安全投影；既有 canonical 参数、确认哈希和 Task 不改写；必要的执行凭据迁移需独立密钥可用性、访问控制和审批，不允许调用明文回退函数后声称已加密。没有运行该迁移。

## 验收矩阵

| 用例 | 证据/状态 |
|---|---|
| G3-01–04 / I01–03 | 语法/观察/拒绝矩阵 PASS_ISOLATED；真实连接、redirect、DNS变化、FTP数据通道 RUNTIME_BLOCKED |
| G3-05–06 / I04–05 | 登记/展开限制隔离回归通过；真实传输/磁盘硬停止 NOT_TESTED |
| G3-07 / I06 | Task/API/日志/确认/MCP 错误局部 PASS_ISOLATED；全历史/Node投影未完成 |
| G3-08 / I07 | caller×protocol 只读分层 PASS_ISOLATED；完整可信身份/认证消费未接线，双方继续关闭 |
| G3-09 | 可变 DTO 再验证、既有 queued Worker 拒绝回归 PASS_ISOLATED；真实队列重放未验 |
| G3-10 / I08 | 原 Worker→FileRegistry→Dataset 真实函数级回归 PASS_ISOLATED；PG/Worker RUNTIME_BLOCKED |

联合回归 194 passed，1 存量 Pydantic warning。非重复累计数，只对应 `regression.txt` 中本次集合。两修改源文件 Ruff 与 strict mypy（follow-imports=silent）通过；不代表全仓通过。保留此前全仓 Ruff/mypy 失败及既有 quarantine 记录；本次未将 quarantine 重标绿。测试无真实 DB/Redis/网络/CLI。

重跑命令（已安装环境，无依赖安装）：

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True MPLCONFIGDIR=/tmp/cygnusx-matplotlib \
.venv/bin/pytest tests/unit/test_download_s3_closure.py \
 tests/unit/test_download_registration_contract.py tests/unit/test_download_transport_contract.py \
 tests/unit/test_download_service.py tests/unit/test_lifecycle_download_security.py \
 tests/unit/test_download_log_security.py tests/unit/test_download_worker_protocol_gate.py \
 tests/unit/test_download_provenance.py -q -m 'not quarantine'
.venv/bin/mypy src/cygnusx/infrastructure/download/policy.py \
 src/cygnusx/application/services/download_service.py --follow-imports=silent
```

## 受控环境复测要求与停止结论

当前沙箱不得强行启动 Worker。需运维先提供非生产项目/用户、PG/Redis/Broker、不可变 Worker 镜像、工具版本、只读程序挂载、独占可写数据盘、受控 HTTP/FTP 服务和显式字节/时长额度。先导出源码清单：

```bash
.venv/bin/python scripts/inspect_download_runtime.py --output /tmp/download-s3-source-review.json
```

该命令输出必须不存在，只读，不代表运行验收。随后由获授权运维在实际 Worker 采集严格观察 Schema，再以脚本 `--worker-observation` 比对。实际传输测试尚无完整已实现的可信 enforcement/harness，**不能提供一个声称可认证网络/硬预算的 pytest 命令**。需先补齐策略和受控环境，分别记录私网跳转、DNS改变、PASV变化、无长度/撒谎长度、累积溢出、磁盘满和进程异常的真实停止与文件证据，才能判断 G3。

回滚仅回退本轮 Service 重建验证 hunk、只读策略投影及新测试；保留原 require gate、S1/S2、用户 Task/文件/参数/哈希、此前安全函数。禁止整文件恢复 tracked patch 或 reset。S4 依赖准入 **不通过**；本轮按 Prompt A 阶段边界停止，不部署、不开放执行。

## 后续增量：历史消息 DTO 投影

定位到会话消息端点 `/sessions/{session_id}/messages` 使用 ChatMessageDTO；原 metadata_json 对下载工具信封不脱敏。新增 `domain/download_security.py::redact_download_tool_history` 和 `ChatMessageDTO.protect_download_history`，按已知下载工具名/capability（platform_submit_download、cygnusx_submit_download、downloads.prepare/submit）识别嵌套信封，只对其显示副本过滤 URL、常见密钥及 work_dir/target_directory/binary/result_path。其他工具的字段保持原契约。不修改消息数据库内容、执行请求、确认参数或哈希。

先红测：`history-red.txt` 中真实 DTO 序列化暴露合成 canary；修改后 `history-green.txt` 63 passed（包含原安全/策略用例，不能与历史数字累加）。`chat-history-regression.txt` 覆盖消息 metadata、附件、compaction 保留和新投影，7 passed。两源文件 strict mypy 与聚焦 Ruff 通过。

范围限制：这是消息 DTO 的结构化下载工具元数据投影，不覆盖自由文本、未识别工具别名、Node 原始诊断或模型实时回灌；不等于持久写入端已经安全，也没有迁移历史数据。G3 仍 PARTIAL_CODE / RUNTIME_BLOCKED。回滚仅移除本轮 field_validator、投影 helper 与专用测试，保留之前的下载 URL/日志安全函数。

## 后续增量：实时 SSE 与新信封持久化

`ChatEventService.before_send` 对 SSE metadata 生成副本后再校验事件顺序，不更改执行对象；已识别下载工具参数和结果使用同一脱敏函数。`chat/utils.py::_finalize_invocation_envelope` 在新展示信封投影后计算 payload_hash，Legacy 与 LangGraph 两 Runtime 的持久信封均调用此函数。此处 hash 为聊天展示完整性摘要，不是审批参数哈希；原 args/result/确认对象不改写。旧数据库信封和旧 hash 未迁移。

新增红测 `live-write-red.txt`，SSE 原回显合成 canary、finalizer 尚不存在；修改后 `live-write-green.txt`：49 passed / 2 failed。两失败位于 LangGraph Runtime 第316行的 provider DB 读取，测试 `_Service` 缺 `_db`，在本轮新 finalizer 逻辑执行之前；保留失败记录，未修改这些 fixture 或标 quarantine。另 `envelope-sandbox-regression.txt`：18 passed / 7 skipped，含消息信封哈希、Notebook导出；真实沙箱测试均未执行，不算 E2E 通过。

新增/涉及的事件服务、utils、两 Runtime 与专项测试 Ruff 通过。聚焦 mypy 对 utils/event service 检查在 utils 的其他函数 int(Any|None) 报1项错（当前第225行），不能宣称全绿。此前聚焦 mypy 通过是此前文件集合的时点证据。

尚未覆盖：没有工具标识的 tool_output 字符串、自由文本、未知工具别名/嵌套自定义载荷、全部模型回灌及 Node callback。不能把本轮 SSE/信封保护当作所有信息流已认证。G3 保持 PARTIAL_CODE / RUNTIME_BLOCKED，S4 不准入。回滚只撤回 finalizer 及两调用点、SSE副本投影和新增测试，不改历史数据或确认哈希。

## 后续增量：仅含调用 ID 的 SSE 输出

SSE 服务维护单个流实例内的已识别下载 call ID 集合。已识别下载的后续事件即便只带 tool_call_id，也对 metadata 和 content 做副本脱敏；不同流不共享集合。新增 canary 红测 `call-id-red.txt`；`call-id-green.txt` 52 passed，覆盖事件顺序、Runtime金样本、终态/审批和投影边界。消息不是下载调用或无法建立关联时不套用该规则，因此仍不覆盖无关联自由文本或未知工具别名。

此前两项 LangGraph 测试失败的原因是本机动态路由配置影响了原本只测试静态模型绑定的替身。本轮在该测试文件局部 fixture 固定静态绑定，保留真实 Runtime 终态/金样本断言；没有修改生产路由开关、生产 DB 行为或传输门禁。修正后原失败的两用例均运行通过。该52项为本次集合，替代此前49 passed/2 failed的当前结论；原失败日志仍保留。

修改文件为 download_security.py、ChatEventService、下载历史专项测试及 test_langgraph_chat_runtime.py；聚焦 Ruff 通过，两源文件 strict mypy通过（call-id-mypy.txt）。此前 utils其他函数的mypy错误不因此消失，仍不宣称全仓通过。S3网络硬预算和运行环境阻断未改变，G3仍未通过。

## 后续增量：执行门禁消费逐协议策略

`require_download_runtime` 现将来源映射到已有后端的协议集合，消费 `describe_transport_admission` 的拒绝结果。原本只读投影不再完全脱离执行门禁。单独改变全局 release switch 不能把未认证协议变为可执行，未知来源同样拒绝。当前没有可信认证消费实现，所以全部既有来源仍拒绝执行；此变更不等于人工/Agent 身份接线已经全部完成。

新增测试先把 switch 仅在进程内 monkeypatch 为 True，复现原门禁未拒绝（admission-red.txt）；修复后联合集合 `final-regression.txt` 249 passed，覆盖 S1 登记/Dataset、Service/协议、安全/日志、history/SSE、聊天金样本和终态。不是各阶段数字累加，也不含真实传输或 PG/Redis。五个相关源文件聚焦 strict mypy 结果见 final-mypy.txt；policy与测试 Ruff通过。此前 utils其他函数的静态问题及真实沙箱跳过仍保留。

人工页面已有明确的未验收提示，并保留各入口；未恢复下载。没有新增环境开关或认证 API，没有把协议认证交给模型参数。回滚仅撤回本次 require 函数体和3个测试，不能翻转生产 release gate。真实 egress/硬预算、身份认证消费及全部信息链路仍是未完成要求，G3与S4准入结论不变。

## 最终依赖复核与恢复入口

再次只读检查 `runtime-access-recheck.json`：Docker socket存在但连接返回PermissionError(errno 1)，宿主aria2c不存在；仅记录代理变量名是否存在，不输出值。此前连续推进期间同一隔离运行条件始终缺失，真实出站和实时硬预算依赖未改变。

当前成果不是S3全部代码完成：实际流量/落盘enforcement与可信认证消费尚未建立；全模型/Node信息边界亦未全验。不再追加布尔配置、模拟吞吐或更多同型矩阵来代替这些缺口。下一步需在明确授权的非生产环境确定可实施的可信出口与文件系统硬配额边界，再实现和验证真实后端约束；当前协议全部保持BLOCKED。没有独立环境/运行授权前，不执行CLI、启动Worker、改防火墙、安装代理、迁移DB或开放人工/Agent执行。

已请求用户提供非生产运行入口、受控HTTP/FTP目标、字节/时长额度及使用范围。待这些外部条件具备后恢复Prompt A；不自动进入Prompt B–E。任务整体未完成，保留PARTIAL_CODE/RUNTIME_BLOCKED结论。
