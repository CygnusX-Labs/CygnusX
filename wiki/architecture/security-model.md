# 安全模型

CygnusX 的安全边界不是单一登录检查，而是**入口治理 → 能力裁剪 → 人类确认 → 源码门禁 → 运行隔离**的多层组合。理解这条链，才能分清“功能已实现”和“操作已被允许”。

> **当前状态**：身份、模块门禁、确认凭证、沙箱最小权限和网络白名单均已实现；下载、Agent 写操作、Dataset 执行等仍受源码级运行门禁保护。**源码常量不因环境变量而解除。**

## 安全链路

```text
请求
  → Auth（JWT / API Key）
  → RBAC / 模块门禁（MODULE_LOCKED.yaml）
  → Cookie / 限流
  → 审计中间件
  → 应用服务重新校验 owner / project / scope
  → 能力目录裁剪（工具 / MCP / Skill / Agent）
  → 人类确认（高风险写操作）
  → 源码运行门禁（WRITE_RUNTIME_ACCEPTED 等）
  → 沙箱 / Worker 隔离执行
```

每一层都必须独立成立；不能因为“前端已隐藏按钮”就假设后端安全，也不能因为“后端返回 403”就认为功能不存在。

## 身份、项目与权限

| 检查点 | 规则 |
| --- | --- |
| 主体 | 来自真实 JWT/API-Key owner resolver，模型参数不能指定 owner/project/scopes |
| 项目归属 | 查询 Project 的 `user_id`，不从路径名推断 |
| 会话归属 | 每次 invoke/approve/execute 重新检查 active session |
| 模块权限 | `disabled_modules` 与管理员规则；前后端共同消费 `data/MODULE_LOCKED.yaml` |
| 项目状态 | 删除/转移/停用后旧关联立即拒绝 |
| 委托 | Node 委托使用独立 JWT key domain、固定 issuer/audience、短 TTL（300 秒）、jti + Redis NX 防重放 |
| scope | Node 委托 scope 与服务端最新 scope 取交集，不能扩大 |

Agent 工具层不存储 Token、原始私有对话或确认 secret；完整执行参数只在确认记录的 Redis TTL 内存在。

## 人类确认：模型不能自证

高风险写操作采用**服务端确认凭证**：

```text
prepare：服务端校验 + 参数快照 + 契约版本/哈希冻结 + 归属绑定
   → PENDING
人类 JWT：确认卡批准
   → APPROVED（Redis CAS）
execute/submit：原子消费，一次性
   → 业务服务
```

- 同一凭证重试返回既有结果（幂等），不新建任务；
- 过期后必须重新 prepare；
- `_confirmed` 模型布尔已废弃，任何通道都不接受模型自证；
- 确认卡展示完整不可编辑参数、摘要、TTL 和阻断原因。

## 源码运行门禁

以下常量是**代码事实**，不是环境变量：

| 门禁 | 位置/含义 |
| --- | --- |
| `WRITE_RUNTIME_ACCEPTED = False` | Agent 工具网关：写操作执行前拒绝 |
| `tool_gateway_read_enabled = false` | 读目录默认关闭 |
| `worker_paths_verified = false` | Dataset Handoff 未完成 Worker 路径验收 |
| `DATASET_IMPORT_WRITE` / `ANALYSIS_SUBMIT_FROM_DATASET` / `COUNTS_DEG_FLOW_ENABLED` | 默认 false |
| `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED = False` | 下载传输未完成运行验收 |
| `LEGACY_PIPELINE_TOOLS` | 旧 Flow 工具兼容切换，默认仍为 true |

即使业务开关打开，源码门禁仍会在业务边界前返回 `WRITE_GATE_BLOCKED` 或同等状态。解除门禁需要独立评审 + 当前源码验收，而不是改 `.env`。

## 沙箱与网络边界

| 边界 | 基线 |
| --- | --- |
| 容器用户 | uid/gid 10001，非 root |
| 权限 | `cap_drop=ALL`、`no-new-privileges` |
| 根文件系统 | 只读；可写目录 tmpfs/显式挂载 |
| 输入 | `/workspace/input` 只读 |
| 网络 | Studio 每会话独立 internal network |
| 出站 | 域名白名单代理，非白名单拒绝 |
| SSRF | `network_request` 前置地址检查；fake-ip 网段 `198.18.0.0/15` 为已知例外 |
| 资源 | CPU/内存/pids/磁盘配额 |

不要挂载 Docker socket、宿主 home、数据库配置或密钥进沙箱。终端与 Studio 的网络名称以 Compose 为准，见[沙箱与执行隔离](sandbox)。

## 密钥与配置

- 密钥只放 `.env` 或部署密钥管理系统；`.env.example` 只保留占位符。
- 不把密钥、真实服务器地址、用户数据路径写入 Wiki、日志、示例或提交。
- 日志中的审计事件只记录必要元数据；不记录完整提示词、用户隐私正文或确认 secret。
- 修改模块注册、镜像清单、确认契约属于保护模块，必须走对应验证门禁。

## 已知限制

- MCP SSE URL 校验不能覆盖所有网络层风险；`/mcp/call` 无独立应用层 token 鉴权与频率限制。
- `WRITE_RUNTIME_ACCEPTED` 等门禁的解除缺乏当前源码的真实多用户/Redis/Worker 验收。
- 数据库不提供防管理员篡改保证；Handoff 的 SHA-256 不是数字签名，执行前仍需复验文件。
- 历史运行证据有 Run ID/提交/镜像范围，不自动适用于当前工作树。

## 发布前检查

使用[安全加固清单](../security/hardening-checklist)与[生产环境检查清单](../deployment/production-checklist)，至少确认：

1. 默认管理员密码/密钥已更换；
2. DB/Redis/MinIO 端口未暴露公网；
3. 模块门禁与角色权限符合部署；
4. 下载/写操作门禁状态与发布说明一致；
5. 日志与审计可查，且未泄露敏感信息。

## 关联文档

- [沙箱与执行隔离](sandbox) · [MCP 体系](mcp) · [Agent 运行时](agent-runtime)
- [环境变量与密钥](../security/env-variables) · [安全加固清单](../security/hardening-checklist)
- 权威基线：[`CygnusX_agent_tool_gateway.md`](../../ARCHITECTURE_DESIGN/CygnusX_agent_tool_gateway.md)、[`CygnusX_download_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)、[`CygnusX_dataset_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md)
