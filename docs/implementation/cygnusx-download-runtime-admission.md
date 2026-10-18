# 下载能力运行准入方案

2026-10-16 核对；本轮未开放任何未认证方式，没有重新实施 RI01–RI04。

## 当前影响及可信来源

人工表单 → 原 REST → DownloadService；Agent → Gateway Prepare/原人工确认 → DownloadService；历史队列 → Download Worker。Service 在目录、Task 和入队之前执行传输源码门禁；Worker 主入口和各 CLI/FTP 连接再次检查。人工页面和 Agent 都不能自证运行许可。现有下载状态/列表读取仍使用原服务。

当前 `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`；Agent 另有原 `WRITE_RUNTIME_ACCEPTED=False`。人工下载同样阻断是已知影响，不以恢复按钮为由开启。

REST `downloads.py:download_capabilities` 和 Gateway `downloads.describe_capabilities` 调用 `tools/download/config.py:describe_download_capabilities`；DownloadsView 经 `src/api/downloadCapabilities.ts` 使用认证 REST。方法不是页面硬编码的独立真相。页面只在 mounted 获取；API/Gateway 每次描述重算，配置管理器仍有本进程缓存，存在多进程发布不同步风险。

## 版本与失效评估

v1 描述的是源码候选能力，binary_version=null、runtime BLOCKED，不是 Worker 认证票据；当前固定关闭，不会因陈旧页面误放行。不能把 SUPPORTED_BY_CODE 等同 Runtime Ready。

未来可用模式必须以 `(source,method,protocol,binary SHA+version,Worker image digest,网络策略版本,资源策略版本)` 为验收单元。拟增加 admission_revision、contract_digest、issued_at/expires_at、worker_profile_id、环境验收引用；这些字段本轮仅设计，不能伪造一个认证 TTL。

任何 CLI、Worker 镜像、出口/预算策略或来源方法变化都撤销对应准入；服务端每次提交重算并比较 revision，不信前端缓存。前端进入页面、提交前或收到 409/失效事件需重新读取；Gateway 同规则。短 TTL、跨进程配置发布和撤销通知要联合验收。失败时保持关闭，不能把无效票据降级成旧配置运行。

## 分方式 Runtime Gate

| 方式 | 必须核实 | 当前 |
|---|---|---|
| SRA aws/ftp | 真实CLI --version/二进制SHA、SRR/PRJNA解析、真实下载终点、临时凭据脱敏、硬预算与取消 | BLOCKED |
| HTTP/HTTPS | DNS连接固定/最终出口、重定向每跳、TLS、私网/metadata拒绝、流式字节/并发/超时预算 | BLOCKED |
| FTP目录 | 实际FTP服务器、深度/循环/文件预算、数据连接出口、超时与中断 | BLOCKED |
| aliyun/volc/huawei | 实际CLI、云授权最小权限、endpoint及最终目的地、令牌不落日志、同类预算 | BLOCKED |
| 历史任务重启 | 原参数合法性、当前授权、当前认证profile、已有输出不接管、不自动重放 | BLOCKED |

生产源码门禁的解除只能在对应负例及成功例全部验收后另行评审；当前全局门禁不能表达按方式认证，因此本轮不开放任一方式。没有新下载器、任意二进制参数或第二套调度器。

## PostgreSQL登记与失败恢复验收

独立测试DB运行原迁移链、原 FileRegistry/Worker/DatasetImportService。并发同 Task/同路径登记验证唯一性和配额仅记一次；不同owner/Task冲突拒绝；撤销项目/模块、配额同时变化需锁与授权核验；不能用SQLite验证这些锁。

在文件生成后、首条登记前、登记中、事务提交前后及队列ACK前后分别杀测试Worker。重启后先只读盘点真实 Task/FileRecord/路径/SHA/配额，不自动重传；成功但无输出、部分输出、未知投递保留 PARTIAL/需对账。原子失败不能遗留半套 FileRecord/Directory/配额。保留原字节和异常证据，使用原 reconcile，不从路径猜项目身份。

准入记录需要命令、环境版本/digest、真实主键、期望与实际SQL结果、配额前后、文件SHA和故障点。没有环境时只能批准测试计划，不能标PASS_RUNTIME。
