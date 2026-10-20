# 架构与数据

本章节按**子系统边界**介绍 CygnusX 当前实现的架构。每一页回答三个问题：这个子系统负责什么、一次请求/任务如何在其中流动、修改它时必须遵守哪些门禁。系统级边界、验收状态和各专项 as-built 文档以 [`ARCHITECTURE_DESIGN/`](../../ARCHITECTURE_DESIGN/README.md) 为准。

## 子系统地图

```text
用户请求
  │
  ├─ 入口治理 ── 身份/RBAC/模块门禁/限流/审计（security-model）
  │
  ├─ AI 执行面
  │    ├─ Agent 装配与执行路径（agent-runtime）
  │    ├─ Tool / MCP / Skill（mcp、skills）
  │    ├─ 记忆与知识检索（memory-knowledge）
  │    └─ 模型路由与计费（model-routing-billing）
  │
  ├─ 计算执行面
  │    ├─ 沙箱隔离（sandbox）
  │    ├─ Flow 声明、确认与提交（flow-runtime）
  │    └─ Celery/Worker/Snakemake
  │
  ├─ 数据面
  │    ├─ PostgreSQL/Alembic/仓储（database）
  │    ├─ 存储根与目录协议（storage、data-directory）
  │    └─ 对象存储与文件登记
  │
  └─ 治理面
       ├─ 事件/日志/审计/trace（observability、logging）
       └─ 文档类型与证据等级（documentation-governance）
```

## 内容导航

### 系统级

- [系统架构总览](overview) — 定位、技术栈、四类执行形态、关键数据流与证据纪律
- [文档治理与证据等级](documentation-governance) — 文档类型、命名规则、事实来源优先级

### AI 与执行面

- [Agent 运行时](agent-runtime) — 数据驱动装配、六条 `execution_path`、上下文、事件和轮次治理
- [沙箱与执行隔离](sandbox) — Chat 轻量沙箱 / Studio 一会话一容器、capability、镜像与安全基线
- [MCP 体系](mcp) — 内置 Preset / 外部 Server / 管线 MCP、固定 Flow 工具、确认凭证、MCP Builder
- [Skill 体系](skills) — 平台 Skill 与编码助手 Skill 的边界、三层渐进披露与审计
- [记忆与知识库](memory-knowledge) — pgvector 记忆 v2、Studio 文件记忆、知识库版本与检索
- [模型路由与 Token 计费](model-routing-billing) — Router/ModelSelector、usage 归一化与饼干扣费

### 计算面

- [Flow 运行时](flow-runtime) — 六段 FlowConfig、热重载、AI 工具编译、确认门与 `TaskService.submit()` 九步链

### 数据面

- [数据库基础设施](database) — 116 张 ORM 表、连接池分角色、仓储分层、迁移与漂移检查
- [存储层](storage) — 单存储根、路径工厂、用户/平台目录、sync 与防复发门禁
- [数据目录结构](data-directory) — 顶层目录布局、迁移与备份

### 治理面

- [安全模型](security-model) — 身份、模块门禁、人类确认、源码写门禁、网络与沙箱边界
- [可观测性](observability) — 事件、审计、日志、OpenTelemetry 与运行证据的层级
- [日志架构](logging) — 五域日志、容量保护与排障速查

## 阅读边界

1. **Wiki 讲边界与用法，不复制完整契约。** 数据库表、Agent 执行路径、MCP 确认契约、Skill 注入、沙箱 capability、存储协议或镜像映射的权威定义，必须回到对应的 `ARCHITECTURE_DESIGN/CygnusX_*.md` as-built 文档与当前代码。
2. **文档类型决定可信度。** as-built > 规范 > 提案/规划 > 历史快照；`deprecated/` 只作历史参考。提案和 vision 不能作为现状依据。
3. **“已实现”不等于“可运行”。** 下载、Agent 写操作、Dataset 执行、科研交付等链路带有源码级运行门禁；环境变量不能解除源码常量。状态说明见[科研能力与证据边界](../research/evidence-boundaries)。
4. **变更前先读验证矩阵。** 不同改动类型（核心逻辑、接口契约、前端、配置、子模块）有不同的最小验证命令，见 [AGENTS.md](../../AGENTS.md) 与[开发规范](../development/index)。

## 设计关键词

- **前后端分离**：Vue 3 + FastAPI，Nginx 作为入口与静态资源代理。
- **DDD 分层**：`api/` → `application/` → `domain/` → `infrastructure/`。
- **控制面与计算面分离**：主栈运行 Web / DB / Redis / Nginx / Beat / Flower；Worker 栈独立运行计算任务。
- **声明式流程**：`flows/*.yaml` + `GenericFlowBuilder`，新增 Flow 不再新增 MCP 工具。
- **默认安全**：权限裁剪、能力目录、人类确认、源码写门禁、沙箱最小权限。
- **证据优先**：任何结论必须能回答“谁执行、在哪执行、输入是什么、检查了什么、如何复现”。
