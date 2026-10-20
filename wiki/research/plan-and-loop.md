# 科研计划与科研闭环

本页覆盖两个相邻机制：**ResearchPlan** 负责项目内科研意图与步骤状态的版本化协调；**科研闭环**负责会话工作区、执行历史、环境还原、长任务与 Notebook 导出。它们都不替代 Task、Dataset、Run 或报告。

> **当前状态**：ResearchPlan 默认关闭，启用后仍为 **PLAN_ONLY**；真实执行门禁、生产发布与科学 Benchmark 未验收。科研闭环的工作区归档、执行历史、环境还原、长任务契约与 Notebook 导出已实现，真实运行仍按部署验收。

## 一、ResearchPlan（PLAN_ONLY）

```text
模型提交 draft
  → 服务器从身份上下文确定 owner/project
  → 生成 ID、版本、digest、审阅状态与步骤状态
  → 人工审阅
  → 写步骤进入 WAITING_APPROVAL（PLAN_ONLY 阻断）
  → 新版本不继承旧审批
```

| 边界 | 说明 |
| --- | --- |
| 不替代 | RunPlan、MASPlan、Task、Dataset、报告 |
| 不新增 | LLM 循环、下载器、统计执行器 |
| 草稿权 | 模型只能提交 draft；owner/project 由服务器确定 |
| 版本 | 新版本重新审阅，不继承旧审批 |
| 表 | 仅 `research_plans`，迁移 `bioopsphase5_research_plans` |
| 保护 | ORM 与 PostgreSQL trigger 保护意图字段；trigger 未在真实库演练 |
| 状态 | PLAN_ONLY；写步骤 `WAITING_APPROVAL` |

代码入口：`api/v1/research_plans.py`、`application/services/research_plan_service.py`、`application/schemas/research_plan.py`、`domain/research/plan_state.py`。

前端注意：

- 按当前项目与指定版本隔离响应；迟到响应不得覆盖新项目/版本；
- `/projects/{project_id}?planId={plan_id}` 从服务器按真实 ID 恢复历史版本，不依赖最近 20 项列表；
- 旧版本通过 `superseded_by` 链接新版本；历史版本不显示审阅推进入口。

科研适用性校验：消费服务器 Handoff，读取实际 species/metadata.organism 并保留冲突；缺稳定样本身份/组织/处理条件要求审阅；重复样本不增加重复数；自由文本不能提供统计数值；Artifact cell API 检查注册路径、归属、SHA 与实际表格单元格。

## 二、科研闭环

### 工作区生命周期

```text
active
  → 90 天不活跃：休眠打包
  → archive
  → 保留 180 天后删除
```

| 项 | 值 |
| --- | --- |
| 工作区配额 | 500 GB |
| 归档配额 | 50 GB |
| 归档登记 | `workspace_archives` |
| 恢复范围 | 仅 `workspace/` 子树 |
| 恢复操作 | 零容器操作；不启动/重建容器 |
| 到期清理 | 按保留策略 |

### 不可变执行历史

- `chat_message_events` 记录会话事件，信封含 `payload_hash`；
- 产物以 SHA-256 对账；
- 支持双读重建，避免只依赖一份投影；
- 取消/恢复/终态必须可追溯。

### 声明式环境还原

- 从 `conda-explicit.txt` / `environment.yml` 用 micromamba 一次性还原；
- 受科研模式门控；
- **已知限制**：生产只读 rootfs 下环境还原会降级；不要把它当作已完全可用。

### 长任务三契约（>600 秒）

1. 先落盘：先创建幂等 job 行，再执行；
2. 终态不可重开：completed/failed/cancelled 不重新打开；
3. reconcile-only：Web 进程只提交与对账，不直接跑长任务；Beat 负责恢复。

### 科研形态

| 开关 | 作用 |
| --- | --- |
| 渲染形态 | cell 投影 + 确定性 `.ipynb` 导出 |
| 工作区协议 | 科研工作区目录与文件约定 |
| PTC `llm_query` | system 锚定 + 同窗审计的受控模型调用 |

### 其他机制

- Chat warm pool 已按 Studio 基线硬化；
- LangGraph 审批闸（ADR-0002）；
- 科研模式默认关闭；开启需部署、权限与验收同时满足。

## 三、Benchmark 边界

`benchmarks/research_agent/v1/` 目前有 **12 个未人工审定的合成契约候选**，只验证约束行为：

- 不代表研究发现；
- 不代表真实科研交付能力；
- 不是三种系统的性能比较；
- 详细协议见 `benchmarks/research_agent/v1/evaluation_protocol.md`。

## 常见误区

1. `PLAN_ONLY` ≠ 可以执行：写步骤被 `WAITING_APPROVAL` 阻断；
2. 计划版本 ≠ 审批继承：新版本必须重新审阅；
3. Notebook 导出 ≠ 环境可复现：环境还原仍可能降级；
4. 工作区归档 ≠ 科研交付包：归档用于恢复，Manifest/Export 用于交付；
5. Benchmark 合成候选 ≠ 科学评测结果。

## 修改门禁

1. 改计划状态/审批 → 更新状态机与 trigger，验证版本隔离与越权。
2. 改工作区生命周期 → 验证归档/恢复/清理与配额，不启动容器。
3. 改长任务 → 保持 job-first、终态不可重开、reconcile-only。
4. 改 Notebook 导出 → 保持确定性；同一输入应产生相同输出。
5. 改科研模式 → 同时检查渲染、工作区协议与 PTC 三个开关。

## 关联文档

- 权威基线：[`CygnusX_research_plan_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_research_plan_architecture.md)、[`CygnusX_research_loop_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_research_loop_architecture.md)
- [科研交付链](delivery) · [报告体系](reports) · [科研能力与证据边界](evidence-boundaries)
- [存储层](../architecture/storage) · [Agent 运行时](../architecture/agent-runtime)
