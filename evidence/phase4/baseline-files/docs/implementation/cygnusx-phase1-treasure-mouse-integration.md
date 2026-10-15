# CygnusX BioOps Phase 1 实施报告

日期：2026-10-15
结论：**PARTIAL / BLOCKED**。代码完成了隔离只读集成基础，但不能发布给真实用户。

## WP1-0 至 WP1-7

- WP1-0：选择 Vue Native；ADR 见 `docs/architecture/cygnusx-treasure-agent-integration-adr.md`。
- WP1-1：新增 FastAPI `research-agent` BFF，使用 `CurrentUserId`；Node 增加内部令牌与 platform-only 入口。旧 Nginx 入口返回 404。
- WP1-2：会话创建、读取、流式请求和取消均以后端 owner/project/session 校验为准；未选项目保持 null。
- WP1-3：保留 delta/tool/cards/polariseq/grounding/end/error/cancel；结果写入平台消息 metadata，取消不取消平台 Task。
- WP1-4：`TreasureMouseView.vue` 改为 Vue 原生页面，包含项目选择、平台会话、SSE、工具轨迹、证据卡和响应式 composer；无独立登录、导航、模型设置。
- WP1-5：新会话复用 `ChatSessionModel`/`ChatMessageModel`；旧账号与历史不迁移、不自动合并。
- WP1-6：新增 Pydantic/TypeScript `DiscoveryProposal`，仅作为未验证只读线索；不创建 Dataset/FileRecord/Task。
- WP1-7：`TREASURE_NATIVE_UI_ENABLED` 默认 false；`TREASURE_AGENT_WRITE_TOOLS_ENABLED` 后端 false；Node 仅允许内部 discovery 路径。

## 变更文件

主要文件：`src/cygnusx/api/v1/research_agent.py`、`src/cygnusx/application/services/research_treasure_service.py`、`src/cygnusx/application/schemas/research_agent.py`、`src/cygnusx/core/config.py`、`src/cygnusx/api/v1/router.py`、`frontend/src/views/TreasureMouseView.vue`、`frontend/src/api/researchAgent.ts`、`frontend/src/components/research/DiscoveryProposalCard.vue`、Node `server/local.mjs`、两个平台 Nginx 配置、Compose 与 `.env.example`。

## 测试结果

- PASS：`pytest -q tests/unit/test_research_treasure_phase1.py -m unit`，3 passed。
- PASS：`cd frontend && npx vue-tsc --noEmit`。
- PASS：`cd frontend && npm run build`。
- PARTIAL：`cd frontend && npm test`，512/519 tests passed；7 个失败来自既有 AgentTeams/AI Chat 测试断言，未触及本轮科研寻宝鼠文件。
- PASS：Node 寻宝鼠回归套件 10/11；已有 `validateSearchQuery.test.ts` 启动子进程失败，单独复跑仍失败，未归因于本次改动。
- BLOCKED：`uv run ruff/mypy` 无法运行，uv 缓存目录只读；当前 pyenv 环境也没有 `mypy`/`ruff` 命令。
- BLOCKED：未能执行 Docker/Redis/真实 FastAPI→Node SSE、真实外部科研检索与浏览器三 viewport 验收。Phase 0B Closure G-02/G-04/G-05/G-06/G-07/G-08/G-11/G-12 仍未通过。

## 安全与回滚

本轮没有下载、分析提交或平台 Task 取消入口。Node 独立账号/历史卷未删除；旧公开路径已拒绝。默认 feature flag 关闭，恢复旧 UI 前必须重新设计受平台认证保护的隔离代理。解除 BLOCKED 的条件是完成 Phase 0B 运行门禁、注入非生产凭证、启动隔离 Compose 并通过双用户/双项目、Node 内部认证、SSE 恢复/取消及响应式手工验收。
