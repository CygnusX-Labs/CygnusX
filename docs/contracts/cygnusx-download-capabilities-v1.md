# Download Capability Contract v1

当前实现入口：`GET /api/v1/downloads/capabilities` 与既有 `downloads.describe_capabilities` Gateway Tool，共用 `tools/download/config.py::describe_download_capabilities`。Vue通过`src/api/downloadCapabilities.ts`读取；平台AI和寻宝鼠沿已有Gateway/MCPClient/ToolBridge。没有新增MCP或下载调度器。

`schema_version=cygnusx.download_capabilities.v1`。每个source包含source_type、supported_methods、method_parameters、input_accession_types、protocols、binary_name、binary_version、verification_status、runtime_readiness、enabled_by_configuration、limitations。

- `SUPPORTED_BY_CODE`：平台与已核对源码的兼容方法，不表示实际Worker版本已核验。
- binary_name只返回受信配置的文件名/工具名，不回传宿主路径；binary_version=null，因为本轮未读取真实Worker。
- enabled_by_configuration只表示已有YAML/Settings特性开关，不能绕过运行准入。
- runtime_readiness/runtime_status始终BLOCKED，write_enabled=false。源码下载与Agent执行门禁均关闭。
- capabilities不是批准凭证。read/prepare不自动下载；人类批准也不解除运行门禁。

| 来源 | 代码方法 | 边界 |
|---|---|---|
| sra（含ENA关联） | aws、ftp | 平台选用已知旧EBIDownload/新Polariseq源码共同方法；实际Worker未认证；GSE/GSM先解析；Dataset raw仍只选已解析SRR |
| direct_link | 配置允许的http/https/ftp子集 | GEO supplementary只能来自权威候选；aria2最终DNS/redirect/出口/硬预算未认证，因此执行阻断 |
| cloud_storage | aliyun、volc、huawei | oss/tos/obs对应原CLI；无通用s3/云盘提取；IP/凭据/本地主机URI拒绝 |
| existing_project_file | attach_file_record | 无传输，仍走已有FileRecord授权/校验/人审；此文档不替代Dataset feature gate |

**历史兼容**：已有Task仍可查询原参数；不重写旧记录。aws/ftp保持原义；aspera/prefetch/auto在Schema/Service/Worker前拒绝，不静默转成其他方法。高级CLI筛选未接入时继续拒绝。用户/Agent不可指定task_id、owner/project、二进制路径或任意CLI参数。

limits区分：max_links、max_ftp_depth/files/遍历超时、registration_max_files/bytes均为已实现的明确边界；transfer_max_bytes=null、transfer_budget_enforced=false。Prepare估计配额和传输后的登记预算不是网络硬限额。本轮没有运行下载CLI，不能标VERIFIED_BINARY或PASS_RUNTIME。

安全执行层：`infrastructure/download/policy.py`的`DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`在Service创建目录/Task/队列之前及Worker/CLI调用前拒绝。当前既有外部CLI不能保证DNS校验与连接固定、可信重定向和传输中预算；所以没有仅凭API首次URL检查开放模式。后续RI05必须单独验收受控出口/目标固定/超限终止/版本与挂载后，才评审源码门禁变更。环境变量不能解除该门禁。
