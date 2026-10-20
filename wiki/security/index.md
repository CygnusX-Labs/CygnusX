# 安全

本章节汇总 CygnusX 的安全加固措施、生产环境检查项与密钥管理要求。完整的安全链路、身份作用域、
人工确认和源码门禁见[安全模型](../architecture/security-model)。

## 内容导航

- [安全加固清单](hardening-checklist) — 15 项已知风险修复与生产检查项
- [环境变量与密钥](env-variables) — 生产密钥、配置组与操作原则
- [安全模型](../architecture/security-model) — 身份、项目作用域、确认门与源码门禁
- [沙箱与工作台](../architecture/sandbox) — 容器隔离与网络出口

## 核心安全原则

- **默认安全**：任何用户数据、文件、任务、管理接口都必须经过认证、授权与所属关系校验。
- **最小作用域**：请求绑定当前用户、项目、模块和资源所有权；跨会话、跨项目默认不可见。
- **人类确认**：写入、执行、发布和正式交付由人类 JWT 端点确认；模型不能自证确认，
  确认凭证一次性并绑定参数哈希。
- **源码门禁**：运行写入受 `WRITE_RUNTIME_ACCEPTED=False` 等源码常量保护，环境变量不能解除；
  下载、Dataset 分析、Worker 可见性分别有独立验收门。
- **密钥外置**：JWT、Redis、AI Provider、TOTP 等密钥只通过环境变量注入，不入仓库。
- **最小权限容器**：沙箱非 root、只读根文件系统、drop capabilities、网络出口白名单、资源硬限制。
- **审计可追溯**：关键写操作、权限变化、任务和异常访问保留可检索的审计与结构化日志。

## 首次部署必填环境变量

```bash
JWT_SECRET_KEY=your-random-secret-here
APP_SECRET_KEY=your-random-secret-here
REDIS_PASSWORD=your-redis-password-here
AI_PROVIDER_KEY_ENCRYPTION_KEY=your-fernet-key-here
FLOWER_BASIC_AUTH=user:password
OMICHBUB_INIT_ADMIN_PASSWORD=your-strong-password
```

> `AI_PROVIDER_KEY_ENCRYPTION_KEY` 一旦设置并写入数据后不可更改，否则已加密字段将无法解密。
> `OMICHBUB_*` 是当前初始化脚本使用的历史变量名，请保持与 `.env.example` 和
> `scripts/init_admin.py` 一致。
> 上述值仅为占位符；生产环境必须使用随机值并通过密钥管理系统注入，禁止写入 Wiki、仓库或日志。

## 当前运行门禁

| 门禁 | 当前值 | 影响 |
| --- | --- | --- |
| `WRITE_RUNTIME_ACCEPTED` | `False`（源码常量） | 所有 Task/写运行路径不可达，环境变量不能解除 |
| Dataset `worker_paths_verified` | `false`（源码生成） | 冻结 Handoff 不声称 Worker 可见，阻塞分析执行 |
| `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED` | `False` | 下载传输未获运行验收 |
| `DATASET_IMPORT_WRITE` / `ANALYSIS_SUBMIT_FROM_DATASET` / `COUNTS_DEG_FLOW_ENABLED` | 默认 `false` | Dataset 写与流程提交默认关闭 |
| `tool_gateway_read_enabled` | 默认 `false` | 寻宝鼠/共享 Gateway 读取默认关闭 |

门禁状态与验收证据见[科研证据边界](../research/evidence-boundaries)；不得通过修改源码常量或
伪造 Handoff 字段绕过。

## 相关页面

- [安全模型](../architecture/security-model)
- [沙箱与工作台](../architecture/sandbox)
- [MCP 体系](../architecture/mcp)
- [生产环境检查清单](../deployment/production-checklist)
