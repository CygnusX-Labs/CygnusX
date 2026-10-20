# 沙箱与执行隔离

CygnusX 有**两套沙箱执行体系**，用途和安全边界不同，不能混用：

| 体系 | 使用者 | 隔离粒度 | 执行协议 |
| --- | --- | --- | --- |
| Chat 轻量沙箱 | 普通 AI 助手的代码/文件操作 | warm pool 复用容器 | Docker SDK exec，按会话标记隔离 |
| Studio 沙箱 | OmicStudio 深度分析 | **一会话一容器** | sandbox-agent Unix Socket，`/exec` NDJSON |

此外还有 AgentTeams 的独立计算 Worker 与 Flow 的 Snakemake 运行时；它们不属于交互沙箱，但同样受镜像、挂载和资源约束。

> **当前状态**：容器安全基线、capability 路由、镜像映射校验和生命周期审计已实现；gVisor/Kata 等更强隔离仍是升级触发条件，不是现状。运行验收以部署环境的实际镜像与配置为准。

## 两套沙箱的差异

| 维度 | Chat 轻量沙箱 | Studio 沙箱 |
| --- | --- | --- |
| 生命周期 | warm pool，任务间复用 | 会话创建即建容器，会话结束回收 |
| 工作区 | `/workspace`，会话后缀隔离 | `/workspace`，input/work/output 分区 |
| 文件 API | 工具与文件适配器 | sandbox-agent 文件 API + 路径防护 |
| 能力 | 代码/文件/轻量命令 | `code` / `browser` / `document` |
| 典型入口 | `chat_sandbox_execute` | `sandbox_execute`、`workspace_*`、`artifact_register` |
| 分析归档 | `sandbox_meta.analysis_archive` 契约 | 工作区、产物与报告版本 |

Chat 沙箱已按 Studio 基线硬化（只读根、非 root、capability 裁剪、资源限制），但仍是共享池模型；不要把 Chat 沙箱当成强隔离的多租户边界。

## 容器安全基线

| 控制项 | 基线 |
| --- | --- |
| 用户 | uid/gid `10001:10001`，禁止 root |
| 权限 | `cap_drop=ALL`、`no-new-privileges` |
| 根文件系统 | 只读；可写目录使用 tmpfs 或显式挂载 |
| 输入 | `/workspace/input` 只读 |
| 资源 | CPU（nano_cpus）、内存、`pids_limit`、磁盘配额（约 10 GiB） |
| 网络 | 默认隔离网络；出站经域名白名单代理 |
| 生命周期审计 | 创建、启动、执行、停止、回收等六类事件 |

`deploy/docker/` 下的 Compose 与镜像 Dockerfile 是这些约束的事实来源；修改时必须同步验证镜像清单和运行时契约。

## capability 与镜像路由

Agent 能使用哪些沙箱能力，由 Agent YAML 的 `features.studio.sandbox_capabilities` 声明；镜像选择由 `studio.images`、Agent 的 `runtime_images` 与 `deploy/image-mapping.yaml` 共同决定。

```text
Agent YAML
  features.studio.sandbox_capabilities → code / browser / document
  runtime_images                        → 基础/专用镜像画像
            │
            ▼
deploy/image-mapping.yaml（镜像清单唯一权威源，当前 17 个，以 `make validate-image-mapping` 为准）
            │  禁 latest；tag 带 git SHA 短号
            ▼
StudioSandboxManager → 容器镜像 + /opt/agent-tools.json 工具清单
            │
            ▼
容器启动后 /tools/list 复核，manifest 漂移审计
```

- 镜像 tag 变更需要同步 6 处：清单 → config_files → build.sh/Makefile/.env.example/config.py → 子镜像重建 → `make validate-image-mapping`。
- 浏览器/文档能力使用独立的 browser-office 镜像；NGS 分析使用专用运行时镜像。
- 未在 Agent YAML 声明的 capability 不应被注入；以 `validate-image-mapping` 和 `test_studio_agent_runtime.py` 作为修改门禁。

## 网络与出站

- Studio 沙箱加入每会话独立的 internal network，不能直接访问主应用网络。
- 出站只能经 `studio-egress-proxy`，代理按域名白名单放行；非白名单请求拒绝。
- Chat 的 `network_request` 工具在请求前做 SSRF 检查；注意 fake-ip 网段（`198.18.0.0/15`）是已知例外。
- 终端使用 `cygnusx-sandbox-net`；不同部署栈的网络名称以 Compose 为准。

详见[安全模型](security-model)与[网络架构权威文档](../../ARCHITECTURE_DESIGN/CygnusX_network_architecture.md)。

## 重要边界

1. **沙箱不是执行准入。** 计算任务能否真正写入 Task/Downloads/Dataset，取决于业务层源码门禁，不由沙箱开关决定。
2. **容器内工具清单是运行时事实。** 构建期登记的 `/opt/agent-tools.json` 与运行期 `/tools/list` 不一致时，以运行期复核和漂移审计为准。
3. **镜像不是“latest 即可”。** 禁止 `latest`；镜像必须可追溯到 git SHA。
4. **不要挂载宿主敏感目录。** 仅按 Compose 声明的白名单挂载共享存储、工作区和只读输入。
5. **沙箱输出需经质量门。** 探索性代码产物不能直接当作正式科研交付。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| Studio 沙箱管理 | `src/cygnusx/infrastructure/sandbox/`、`infrastructure/studio/` |
| sandbox-agent 协议 | `/exec` NDJSON、文件 API、路径防护 |
| Chat 沙箱 | Chat runtime 沙箱适配器 + warm pool |
| 镜像清单 | `deploy/image-mapping.yaml` |
| 镜像与端口契约 | `make validate-image-mapping`、`scripts/test_studio_agent_runtime.py` |
| 审计事件 | 沙箱 `audit.py` 生命周期事件 |

## 关联文档

- 权威基线：[`CygnusX_sandbox_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_sandbox_architecture.md)（唯一规范）、[`CygnusX_chat_execution_layers.md`](../../ARCHITECTURE_DESIGN/CygnusX_chat_execution_layers.md)
- [Agent 运行时](agent-runtime) · [安全模型](security-model) · [Flow 运行时](flow-runtime)
- [云端沙盒终端](../features/sandbox-terminal) · [AI 助手与工作台](../features/ai-chat)
