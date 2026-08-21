# 协作室（AgentTeams）现阶段架构 · 2026-08-21

> 定位：**as-built 现状文档**。记录 2026-08-21 路线图五批施工收口后协作室的真实架构，
> 所有结论以代码与运行栈实测为准（文件引用带行号，commit 见《协作室后续优化路线图-执行总结-2026-08-21》）。
> 与愿景/评审文档的关系：本文是「现在是什么」，愿景与评级见
> `docs/info/26.8.21/协作室框架现状全景与优化点_2026-08-21.md`、
> `协作室L4愿景符合度审查报告-2026-08-21.md`。

---

## 1. 总体拓扑

```
用户浏览器
   │  Vue3 前端（AgentTeamsRoomView / AgentTeamsCaseView）
   ▼  /api/v1/agent-teams/*（JWT）
┌─────────────────────────────────────────────────────────┐
│ 平台 omichub-web（FastAPI）                              │
│  房间响应/意图路由 · Case 服务 · 会诊 · 血缘/判决/自省     │
│  PostgreSQL（业务态+血缘+判决）                          │
└───────┬───────────────────────────────────┬─────────────┘
        │ X-Integration-Token                │ Matrix mirror（房间消息镜像）
        ▼                                     ▼
┌──────────────────────┐            ┌──────────────────┐
│ Bridge（FastAPI）     │──events──▶ │ MinIO 事件卷      │
│ Case 状态机/派单/归档  │            │ Redis 共享状态     │
└───────┬──────────────┘            └──────────────────┘
        │ consult（只读/工作区执行经 Gateway 仲裁）
        ▼
┌──────────────────────┐
│ Gateway（规划网关）    │──▶ 平台 Agent 运行时（会诊/执行）
└──────────────────────┘
        ▲ inbox 轮询 / claim / heartbeat / 上报
┌──────┴───────────────────────────────────────┐
│ Worker 集群（analysis / quality / delivery /  │
│ code / viz / scrna / professional-pool×2）    │
└───────────────────────────────────────────────┘
```

运行栈组件（`deploy/agentteams/docker-compose.agentteams.yml` 实测）：
`omichub-agentteams-gateway`、`omichub-agentteams-bridge`、`omichub-agentteams-state`、
`agentteams-worker-{code,viz,scrna,analysis,quality,delivery}`、professional-pool×2、
phylo-worker；平台侧 `omichub-web`、`omichub-worker`、`omichub-beat`、`omichub-minio`、
`omichub-cache`（Redis）、`omichub-db`、`omichub-pgbouncer`、`omichub-rocketmq-*`、
`omichub-matrix-dev-{synapse,element}`（房间镜像的开发态 Matrix）。

## 2. 房间层（未立项阶段）

- **房间命名空间**：未立项房间的事件流挂在 `room-<room_id>` 伪 case_id 命名空间下
  （`ROOM_NAMESPACE_ID_PREFIX`，`src/omichub/application/services/agentteams_service.py`），
  与正式 Case 共用审计总线但不是工单，不计入 Case 运营指标。
- **意图路由四态**：`classify_execution_intent` → `EXECUTE / TOOL_EXECUTE / CLARIFY / CHAT`
  （`agentteams_execution_intent.py:82-88`）。**硬约束（批 2.1）**：路由无命中强制走澄清卡或
  LLM 会诊，禁止直达通用助手静默兜底（`agentteams_room_response_service.py:855` 起）。
- **能力咨询**：`ability_catalog_query` / `room_state_query` 两个只读 MCP 工具经
  `annotations`（readOnlyHint）在 `safe_only` 会诊下放行；Agent YAML 顶层 `mcp_tools`
  白名单已激活（此前为死配置）。权威目录源 `data/ai/agent_ability.yaml`，
  与 `GET /capabilities` 注册表快照口径一致（批 0.2 抽查实证）。
- **立项**：执行类需求 → `room.proposal_confirm` 立项确认卡 → confirm-proposal → 创建 Case。
- **Matrix 镜像**：房间消息经 `room_mirror.py` 镜像到 Matrix 房间（开发态 synapse）。

## 3. Case 执行层（Bridge）

Bridge（`integrations/agentteams/bridge/omichub_agentteams_bridge/`）是 Case 的权威状态机：

- **派单与认领**：Work Item 由 flow YAML/`_shared` 声明或按 capability 派生；
  `role_agent_map` 把 legacy 角色别名解析为 canonical worker identity（BUG-E2E-03，
  `service.py:_canonical_work_item_target`）；Worker 按 identity 轮询 inbox → claim（租约）→
  heartbeat → 执行 → 上报。
- **看门狗（批 3.1 修复）**：平台侧 `AgentTeamsCaseWatchService._scan_session` 改走
  `refresh_case`（即 Bridge `/reconcile`），卡死 Case 不再依赖用户打开 Case 视图才被发现；
  `omic_task_stall_timeout_seconds=900` 等魔数已按实测口径登记。
- **只读会诊与工作区执行**：Worker 的 `execute_readonly_work_item` 经 Bridge 转发 Gateway
  `consult`；F1 起 `source_refs`/`execution_summary` 原样透传到平台产物登记路径。
- **质量门（F1/F2 硬约束）**：上报 `artifact_hashes` 必须携带 `source_refs`，
  缺失即 422 拒绝并回写 `room.artifact_rejected` 审计事件，状态机不迁移。
- **交付**：manifest 内嵌产物 MD5 清单与 `artifact_lineage`（血缘事实随单输出，
  权威版本行在平台 DB）。

## 4. 数据与取证

### 4.1 审计事件总线

- Bridge 事件持久化在 **MinIO 事件卷**（每 case 一卷），Redis 作共享状态后端（可选）；
  启动时全量重放重建内存索引与幂等 receipt。
- 事件分类：business（状态迁移/决策）/ stream（瞬态逐字符输出）/ operational（心跳轮询计数，
  单独聚合成 `operational_events__*` 指标键）。
- 平台侧统一查询入口：`GET /cases/{case_id}/audit-chain`（`AgentTeamsAuditChainService`，
  拼接房间关联事件 + Case 事件，检测断裂链）。

### 4.2 PG 血缘与判决三表（`infrastructure/database/models/chat.py`）

| 表 | 模型 | 内容 |
|---|---|---|
| `case_artifact_versions` | `CaseArtifactVersionModel` (:112) | 产物版本行：artifact_id + version_no 递增、checksum_sha256、producing_event_id、environment_snapshot |
| `case_artifact_dependencies` | `CaseArtifactDependencyModel` (:152) | 血缘 DAG 边（downstream ← upstream，relation=input_to/derived_from） |
| `qc_verification_checks` | `QcVerificationCheckModel` (:181) | agent-qc 结构化判决：claim_hash、verdict（pass/warn/fail/降级）、claim_snapshot、reason |

### 4.3 自省查询面（F4）

- `POST /introspection/query`、`GET /introspection/schema`——**仅 X-Integration-Token
  服务端到服务端**（Bridge `OmicHubClient.query_case_facts` 转发），scope 绑定在平台 DB
  强制，SQL 绕过（UNION/子查询/注释/别名）有 10 条 ASGI 集成测试卡口
  （`tests/integration/test_agentteams_introspection_api.py`）。
- 路径已加入 `AuthMiddleware.SELF_AUTHENTICATED_PREFIXES`（批 3.2 修出的真 bug：
  此前在中间件层 401，端点从未可达）。
- 模板含 `artifact_versions / event_timeline / pending_approvals / artifact_lineage / schema`。

### 4.4 房间归档（批 4.5，口径 §2 归档 ≠ 删除）

- `POST /v1/rooms/{id}/archive|/unarchive` + `_room_archive_loop` 周期扫描
  （`room_archive_days=30`）：事件卷两阶段迁移到 MinIO 冷存前缀 `archive/rooms/<id>/`，
  启动时按前缀探针重建已归档集合；已归档命名空间的 business 写入显式 409
  （stream/operational 不受影响）；活动性判定只认 business 事件。
- 指标：`room_namespace_archived_count` 与按房间展平的 `room_events__*`。

## 5. 安全与身份

三类令牌，各走各的通道：

1. **用户 JWT**——前端到平台 `/api/v1/agent-teams/*`；Case/房间端点统一走
   requester_ref 归属校验（`AgentTeamsService.get_case` 口径）。
2. **Worker Token**——`/v1/worker-tokens` 签发/吊销，Worker inbox/claim/heartbeat 凭它。
3. **X-Integration-Token**——Bridge↔平台内部面（自省查询、schema 文档），用户不可达。

其他边界：会诊 `safe_only` 只放行 readOnlyHint 工具；房间已归档即只读；
血缘登记缺 source_refs 即拒；能力声明以目录/注册表为准，查询失败显式回问不静默回落。

## 6. 前端展示位（批 4.1 新增）

`AgentTeamsCaseView.vue` 证据栏两个卡片：

- **产物血缘**：`GET /cases/{case_id}/artifact-lineage`（用户可读，批 4.1 新增端点），
  渲染版本列表（artifact_id、version_no、大小、时间、上游引用）。
- **质量判决分布**：同端点返回的 `qc_verdicts`（counts 全量 GROUP BY 聚合 + 最近判决行），
  pass/warn/fail/inconclusive 计数徽章；拉取失败静默降级为空态。

## 7. 关键文件地图

| 层 | 文件 |
|---|---|
| 意图路由 | `src/omichub/application/services/agentteams_execution_intent.py` |
| 房间响应 | `src/omichub/application/services/agentteams_room_response_service.py`（2035 行） |
| Case 服务 | `src/omichub/application/services/agentteams_service.py`（1849 行） |
| 会诊 | `src/omichub/application/services/agent_consultation_service.py`（996 行） |
| 血缘 | `src/omichub/application/services/agentteams_artifact_lineage_service.py` |
| 判决读取 | `src/omichub/application/services/agentteams_qc_verification_service.py` |
| 自省 | `src/omichub/application/services/agentteams_introspection_service.py` |
| 审计链 | `src/omichub/application/services/agentteams_audit_chain_service.py` |
| 能力注册表 | `src/omichub/application/services/agentteams_capability_registry.py` |
| 平台 API | `src/omichub/api/v1/agentteams.py` |
| Bridge | `integrations/agentteams/bridge/omichub_agentteams_bridge/{app,service,audit,minio_store,case_store,client,models,config}.py` |
| Gateway | `integrations/agentteams/gateway/omichub_agent_gateway/` |
| Worker | `integrations/agentteams/worker/{worker_runner,production_runner,claim_next,*_runner}.py` |
| 团队定义 | `integrations/agentteams/teams/bioops-delivery.yaml` |
| 前端 | `frontend/src/views/AgentTeams{Room,Case}View.vue`、`frontend/src/api/agentTeams.ts`、`frontend/src/utils/agentTeams*.ts` |

## 8. 观测与配额

- Bridge `/v1/metrics`：Case 运营指标 + operational 计数 + 房间命名空间事件量（含归档数）。
- F5 token 预算（批 4.3 补齐模板口径）：完整路由 system prompt 实测 **4743 tokens**
  = 模板 1497 + 目录 2801 + flow 446。
- CI：`.github/workflows/ci.yml` 只卡新增失败；72 条存量失败在 quarantine
  （burn-down 见 `docs/info/26.8.21/协作室测试quarantine-burn-down-2026-08-21.md`）。

## 9. 已知限制与后续（诚实清单）

1. **room.agent_stream 仍在持久流**：每 24 字符一条持久事件，MinIO 模式下读-改-写
   写放大，且 room mirror 未跳过它（用户可见刷屏）——L4 报告 #2，缺陷级，待排期。
2. **CaseStore 幽灵态窗口**：mutating 方法先改内存后持久化，MinIO 无 Redis 部署下
   进程生命周期内不自愈——L4 报告 #6，缺陷级，待排期。
3. **correlation_id 无写入点**：提取口径已定义，跨服务 trace 属后续（L4 #4，已知限制）。
4. **会诊异常事件无 causation_event_id**：写入点拿不到触发 event_id（L4 #3，已知限制）。
5. **F9 B 臂未实测**：等 `TEAMING_EVAL_LLM_*` 凭证；stub 口径统计效力不足。
6. **扩展项未动**：L2→L4 Phase D LLM 兜底、provenance 三层标注。
7. **主仓工作区约 650 个 W0–W4 历史未提交改动**待按 N1 对账表分组核验入库。
