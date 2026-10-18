# 统一下载与 Agent 接入：已完成工作与交接说明

记录日期：2026-10-16。本文是阶段成果快照，汇总本次下载架构调整已落地的代码、验证证据与后续接续位置。活动架构权威仍为 [CygnusX_download_architecture.md](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)，本文不替代该文档。

## 1. 当前交付状态

已完成 S0 基线与失败复现、S1 文件登记与 Dataset 对账修复、S2 协议契约及运行来源清单，并完成 S3 的一部分安全修复。**整体架构调整尚未完成，未部署，未开放 Agent 或人工真实下载执行。**

| 阶段 | 已交付 | 验收范围 |
|---|---|---|
| S0 | 工作树基线、变更前真实失败用例、证据索引 | G0 隔离通过 |
| S1 | Worker → FileRegistry → Dataset 登记链及失败保护 | G1 隔离通过，真实 Worker/PG 并发未验 |
| S2 | 统一方法/协议约束、配置重验、来源清单、前端契约修正 | 局部隔离验证通过；运行来源及人工兼容性未完成 |
| S3 | URL 语法、FTP 展开数量、日志/响应/确认/工具错误脱敏 | 局部通过，G3 未通过 |
| S4–S7 | 尚未按阶段完成可靠性、完整目录、多 Agent 接入及运行认证 | 不得据当前成果宣称完成 |

源码关闭门禁 `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False` 和 Agent 写门禁保持关闭。当前人工下载页面也受关闭门禁影响，“保留人工安全下载体验”仍是待解决要求，不能作为已交付能力。

## 2. 已完成的核心改动

### 2.1 下载产物接入原 FileRegistry

原 Worker 登记缺少 `task_id`、实际 checksum，并使用默认上传来源，导致 Dataset 按 Task 查询时无法找到下载文件。现改为调用既有 `FileRegistry.register`，显式绑定真实 Task、下载来源、SHA 和文件大小，无新增登记表或数据库迁移。

- 下载前保存有界输出基线，检查用户、工作目录及本地受管存储；拒绝其他任务共享目录和历史未绑定文件，防止自动覆盖或冒领。
- 登记前拒绝路径逃逸、软/硬链接、特殊文件、不稳定内容与未完成产物，排除控制文件；登记扫描有条目、文件数与字节上限。
- 文件记录、目录链和 `used_storage` 在同一事务/savepoint 内更新；同用户、Task、来源、SHA、大小等条件一致时幂等复用，不重复扣配额。
- 非零退出可保留稳定部分文件，任务仍失败；成功退出但无完整产物或登记失败，不得变为成功。
- 原 Task 参数保存 `FILES_REGISTERED`、`PARTIAL` 或 `RECONCILIATION_REQUIRED` 投影。`scientific_ready=false`；下载登记不自动提升 Dataset 科研就绪状态。

真实生产登记函数已经在临时文件与 SQLite 上贯通到原 Dataset reconcile。测试未手工补造 FileRecord 的 Task 关联。

### 2.2 平台协议与方法收敛

`domain/download_contract.py` 统一平台来源、方法与协议集合，DTO、Service 和排队 Worker 重验，防止旧任务或内部调用绕过策略。

| 来源 | 当前契约 | 边界 |
|---|---|---|
| SRA/ENA | 单 accession，方法 `aws` / `ftp` | 格式接受不代表源端一定存在数据或 Worker 已认证 |
| GEO | 明确返回需元数据解析 | GSE/GSM/GPL 不直接送下载 CLI |
| 直链 | HTTP / HTTPS / 匿名 FTP | 配置只能收紧；FTPS 不支持；实际传输关闭 |
| 云存储 | OSS / TOS / OBS 及已有提供商别名 | 不扩展为通用 S3/COS；实际传输关闭 |
| 云盘 | 保留未接入展示 | 无可执行适配 |

Aspera 不再静默接受或映射。未接线的高级筛选明确拒绝；前端移除失真速度宣传、多 accession 暗示和无效控件。内置/外部 MCP 方法声明及 MAS 旧旁路对齐，但不代表完整多 Agent 运行验收完成。

二进制路径按显式下载 YAML → 对应 Settings/env → 存储路径默认值解析；拒绝不可信路径形态。共享功能开关检查保留既有 YAML OR Settings 语义。

### 2.3 运行来源清单与漂移检查

新增只读来源清单模块和 `scripts/inspect_download_runtime.py`，记录主/子仓、锁文件、配置、Worker 代码及构建声明摘要；可合并严格 Schema 的运维观察，检查版本、路径、方法和挂载漂移。

默认仅生成 `SOURCE_ONLY`，不执行程序、不访问容器或数据库、不导出完整环境或凭据。即便观察一致，仍保持 `runtime_status=BLOCKED`、`release_ready=false`，不能由模型自报通过。平台子模块、独立旁仓、宿主二进制与 Worker 实际运行版本按不同证据管理，不互相替代。

### 2.4 S3 已落地的安全增量

- 限制公网主机语法、链接长度及查询字段数量，拒绝常见签名/凭据查询及云对象查询；没有新增凭据保险库。
- FTP 目录递归具有限深、条目和超时边界；展开结果按 `min(max_ftp_files, max_links_per_task)` 限制，避免目录展开放大链接总量。
- 为原 BinaryExecutor 添加可选调用方日志过滤器：下载 stdout/stderr 缓存及日志回调先脱敏，原结构化进度解析保留。Worker 入库/发布入口再次过滤；其他调用默认不启用过滤。
- 下载 Task 的名称、错误、日志和参数在响应副本中脱敏，不改写原执行参数、历史记录或确认哈希。
- 下载 API 校验错误去除原始 input/ctx/msg；下载工具确认在存储前校验参数，拒绝不安全输入。
- 内置 MCP 下载工具不再返回可能含签名 URL 的完整 Pydantic 异常，改为固定 `DOWNLOAD_ARGUMENTS_INVALID` 与提示。

这些措施不证明所有 ToolTrace、对话历史或网站私有令牌格式均已覆盖，也不等于真实 DNS/重定向/FTP 数据通道已被约束。

## 3. 验证结果与证据

下表保留每次验证的实际范围。集合存在重叠、后续增补和工作树变化，**不得将各行相加作为独立测试总数**。

| 验证 | 结果 | 证据 |
|---|---|---|
| S0 登记失败复现 | 修改前真实断言 `task_id=None` | `evidence/download-s0/red-test.txt` |
| S1 登记及相关回归 | 103 passed，5 既有 quarantine 排除 | `evidence/download-s0/green-and-regression.txt` |
| S2 联合后端回归 | 155 passed | `evidence/download-s2/regression.txt` |
| S2 前端专项 / 类型 | 3 项 jsdom 通过；vue-tsc 通过 | `evidence/download-s2/frontend-tests.txt`、`frontend-typecheck.txt` |
| S3 安全、协议、确认 | 110 passed | `evidence/download-s3/focused-tests.txt` |
| S3 登记与 provenance 回归 | 42 passed | `evidence/download-s3/registration-provenance-regression.txt` |
| 最新安全边界专项 | 19 passed，含先前部分用例与新增 MCP 错误用例 | `evidence/download-s3/tool-error-boundary-tests.txt` |

聚焦 Ruff、部分源文件 strict mypy 与既有迁移链检查已有通过记录；不代表全仓门禁全绿。全仓 Ruff/mypy 有大量既有问题；最新 `presets.py` 检查还有 40 项其他区域问题，未扩大范围修复。

测试使用临时文件、SQLite、伪进程流、伪 FTP、内存确认 store、jsdom 与 API doubles。已覆盖真实生产登记、执行器、FastAPI 校验处理器和 Task 响应转换，但**没有真实 Worker/PG/Redis/传输/浏览器 E2E 通过证据**。本次仅整理文档，未重新执行上述历史测试。

## 4. 未完成项与接续条件

1. **S3 网络与硬预算**：真实 DNS 连接绑定、逐跳重定向约束、FTP 数据通道、未知大小与超额传输硬停止、实时配额/磁盘占用及解压炸弹运行验收。登记字节上限是传输后检查，不能替代传输硬预算。
2. **S3 信息与兼容性**：ToolTrace/对话历史全链路凭据保护，以及人工安全下载路径兼容。
3. **S4 可靠性**：唯一工作目录、提交/事务/排队一致性、完整幂等、取消与跨 Worker 恢复、故障对账操作手册。
4. **S5/S6 接入**：完整逐协议能力目录、角色权限矩阵、多 Agent 工具接线及真实身份/确认链路。现有共享 capabilities/Gateway 代码不能代替这些阶段验收。
5. **S7 运行认证**：真实 Worker 来源、挂载、镜像、队列、协议与科研流程 E2E，最终逐能力发布结论。

当前环境复核：Docker socket 存在但连接返回 PermissionError（errno 1），宿主 `/usr/bin/aria2c` 不存在；宿主 EBIDownload 存在不证明 Worker 可运行。见 `evidence/download-s3/runtime-access-check.json`。继续运行验收需要可访问的非生产 Worker、挂载说明、受控 HTTP/FTP 目标及环境使用范围。按原阶段协议，G3 未通过不进入后续依赖阶段，不能翻转关闭门禁获得绿灯。

## 5. 文档、代码入口与交接保护

| 内容 | 入口 |
|---|---|
| 当前活动架构 | [下载架构](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)，尤其 §8–§10 |
| S0/S1 细节 | [基线与红测](download-s0-baseline-and-red-test.md)、[登记与 Dataset 桥接](download-s1-file-registry-dataset-bridge.md) |
| S2 细节 | [协议与来源清单](download-s2-worker-protocol-provenance.md) |
| S3 细节 | [网络、预算与日志安全](download-s3-network-budget-safety.md) |
| 架构决策与清单契约 | [ADR](../adr/download-transport-and-asset-registration.md)、[Runtime Manifest v1](../contracts/cygnusx-download-runtime-manifest-v1.md) |
| 核心实现 | `infrastructure/celery_app/tasks/download.py`、`infrastructure/download/{outputs,provenance,policy}.py` |
| 协议与安全 | `domain/download_contract.py`、`domain/download_security.py`、`application/schemas/download.py` |
| 专项测试 | `tests/unit/test_download_{registration_contract,transport_contract,provenance,worker_protocol_gate,log_security}.py` |

以上代码路径相对 `src/cygnusx/`（测试除外）。工作区包含大量既有和并行改动，部分安全门禁、capabilities 与 UI 内容由共享工作区另行加入；阶段报告保留归属说明，本汇总不将整仓差异归入本次成果。

没有提交、推送、镜像构建、服务重启、生产迁移或历史文件回填。后续逐 hunk 审查，不使用整仓 reset/clean，不删除用户文件或猜测历史 Task 归属。阶段证据中的清单为时点快照，后续改动后需重新生成，不能作为当前源码自动准入证明。
