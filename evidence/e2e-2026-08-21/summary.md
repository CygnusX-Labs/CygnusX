# Track B 地基 e2e 验收汇总（2026-08-21）

> 任务书：docs/info/26.8.21/协作室双线施工任务书-三件套实现与地基e2e验收.md Part 2
> 状态图例：🟩 绿 / 🟥 红 / 🟨 部分覆盖或带观察项 / ⬜ 未覆盖

## 环境准备（Part 2.1）

- 镜像新鲜度：开工时 web/beat 镜像构建于 2026-08-20 22:26(+0800)，bridge 22:36，
  而 23:47–00:38 有新一轮源码改动（v3 复审 A1/A2/A3/B1、confirm-proposal 幂等、/health SHA），
  **运行镜像不含最新代码** → 已重建（web/beat compose build + up；bridge/gateway/agentteams workers
  经 `make docker-up-agentteams`；omichub worker/phylo-worker 因 src bind mount 仅 restart）。
- 重建后 `/health`（web）= git_sha 4680155 / build_time 2026-08-20T17:29:51Z；
  `/healthz`（bridge）= build_sha 4680155 / minio_enabled=true / minio_reachable=true。
  ⚠️ SHA=HEAD 4680155，但工作树有 232 个未提交改动，SHA 无法反映工作树内容（红线禁 git 提交）。
- alembic：`current == heads == u4v5w6x7y8z9`（web 容器 entrypoint 启动自迁移已生效）。
- 备注：验收过程中用户侧两次运行 `make docker-reload`（02:05/02:12 +0800），栈被整体重建；
  相关用例在重建后复验。
- 证据：env/pre_rebuild_snapshot.md, env/post_rebuild_snapshot.md

## 用例结果

| # | 用例 | 结果 | 证据 |
| --- | --- | --- | --- |
| E2E-1 | 全链路（发言→路由→澄清→立项→审批→执行） | 待定 | E2E-1/ |
| E2E-2 | 参数契约 limit 边界 | 🟥 limit=101/200 被 422 抹平（未钳制） | E2E-2/ |
| E2E-3 | 未知领域（16S）显式 fallback | 待定 | E2E-3/ |
| E2E-4 | 规划失败显式化 | 待定 | E2E-4/ |
| E2E-5 | 删除对账 | 待定 | E2E-5/ |
| E2E-6 | 气泡可见（前端渲染） | 待定 | E2E-6/ |
| E2E-7 | hi 不建 Case | 🟩（观察项：回复形态为 ask_user 选项卡而非纯文本气泡） | E2E-7/ |
| E2E-8 | MinIO 恢复 + 损坏快照拒启动 | 待定 | E2E-8/ |
| E2E-9 | 游标分页不重不漏、与 audit-chain 一致 | 待定（首轮发现空页死循环疑点，待复验） | E2E-9/ |
| E2E-10 | 新链路物化（产物入项目目录） | 待定 | E2E-10/ |
| E2E-11 | 直答降级 | 待定 | E2E-11/ |

## 发现的地基 bug（走主干 hotfix，本任务未改代码）

- **BUG-E2E-01**：POST /api/v1/agent-teams/rooms 恒 500（MissingGreenlet）。
  Matrix 建房成功回写 matrix_room_id 触发二次 flush（UPDATE），
  `TimestampMixin.updated_at` 的 `onupdate=func.now()` 使属性在 UPDATE 后被 expire，
  `_room_payload`（agentteams.py:687）同步读取触发懒加载 IO → 500 → 房间回滚。
  详见 env/BUG-01-room-create-500.md。影响：平台层建房不可用，E2E-7/9/10/11 房间入口受阻
  （本任务用「容器内同 Service 调用 + commit」绕过解锁下游验证，不改代码）。

## 环境最终状态

（收尾时填写）

## 遗留问题

（收尾时填写）
