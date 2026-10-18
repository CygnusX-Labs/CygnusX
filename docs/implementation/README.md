# 实施与验收罗盘

本目录保存 CygnusX 下载、Agent Runtime 与科研交付相关的阶段报告和实施记录。本文是查找入口，不是架构事实源，也不替代具体报告中的命令、日志和验收条件。修改实现前，先按 [架构文档索引](../../ARCHITECTURE_DESIGN/README.md) 找到对应 as-built 文档；判断是否通过时，以代码、当前证据和对应阶段报告为准。

希望快速了解当前进度、`BLOCKED` 原因和下一步，请先看[统一验收罗盘](罗盘.md)。

## 从这里开始

| 你要做什么 | 先看 | 然后看 |
|---|---|---|
| 了解下载 / Agent 接入全貌与阶段状态 | [下载与共享 Agent 罗盘](download-compass.md) | 对应阶段报告和 `evidence/download-*` |
| 接续 2026-10-18 的 R3、G3-E2 与 S6/S7 验收 | [Agent Runtime 验收罗盘](cygnusx-agent-runtime-acceptance-compass.md) | [验收交接记录](../../evidence/iat-r3-20261018/handoff.md) 与当前矩阵 |
| 查找 S5-C 原始运行阻塞调查 | [S5-C 原始验收报告](download-s5c-agent-runtime-acceptance.md) | [S5-C1 代码闭环](download-s5c1-agent-runtime-code-closure.md)、[S5-C2 运行验收](download-s5c2-agent-runtime-acceptance.md) |
| 查看 R3 的实现边界 | [R3 Runtime/UI 闭环](cygnusx-iat-r3-runtime-ui-closure.md) | [R2 证据复核](cygnusx-iat-r2-runtime-evidence-closure.md) |
| 查看 G3 受信执行与未完成项 | [G3-E2 Trusted HTTP 运行记录](cygnusx-g3-e2-trusted-http-runtime.md) | `evidence/g3-e2-20261018/` |
| 继续 S4 可靠性验证 | [S4-A 实现](download-s4a-task-reliability-implementation.md)、[S4-B0 加固](download-s4b0-reliability-hardening.md)、[S4-B1 运行验收](download-s4b1-runtime-reliability-acceptance.md)、[PG-11 应用层写入保护审计](cygnusx-iat-r3-pg11-source-audit.md) | 矩阵对应行与运行证据 |

## 2026-10-18 接续材料

以下日期目录材料是实施范围、提示和交接模板，不是验收通过证据：

- [实施优化方案](../info/26.10.18/01_CygnusX_实施优化方案.md)
- [IAT-R3 实施提示](../info/26.10.18/02_Codex_IAT-R3_实施提示词.md)
- [G3-E2 实施提示](../info/26.10.18/03_Codex_G3-E2_实施提示词.md)
- [证据与 S6-S7 交接模板](../info/26.10.18/04_验收证据与S6-S7交接模板.md)
- [2026-10-18 验收矩阵](../info/26.10.18/CygnusX_Integration_Test_Matrix_2026-10-18.csv)

矩阵汇总由 `scripts/summarize_acceptance_matrix.py` 生成；使用 `--strict-evidence` 可在任一 `PASS_*` 行缺少证据路径或目标文件时失败。

对应证据目录为 [`evidence/iat-r3-20261018/`](../../evidence/iat-r3-20261018/) 和 [`evidence/g3-e2-20261018/`](../../evidence/g3-e2-20261018/)。交接记录列出本轮实际执行、未执行及资源缺口；`manifest.sha256` 用于校验已登记证据文件。

## 当前状态怎么读

截至 2026-10-18 的记录，R3 为 `PARTIAL_ISOLATED / RUNTIME_BLOCKED`，G3-E2 为 `PARTIAL_CODE / RUNTIME_BLOCKED`。这表示隔离测试或部分代码工作已有结果，但所需的真实运行验收条件尚未满足；它不是一个统一异常，也不等于代码没有进展。

主要未闭环项：

- R3：缺少获准的产品服务环境来完成真实 Provider/API/SSE、Node 回调、数据库断言和浏览器工作流验收。
- S4：隔离可靠性回归已完成部分断言；真实 PostgreSQL、Broker、Worker/Beat 的故障与恢复场景仍需专用环境验证。
- G3-E2：Worker 控制客户端和部分回执/nonce 契约已有隔离验证；Supervisor 服务端、操作系统级出站与资源限制、进程停止清理和真实 PG 迁移验证尚未完成。
- S6/S7：前置条件未全部满足，因此 S6 尚未准入，S7 尚未开始。

具体缺什么、哪些场景跳过，以及下一步需要什么资源，分别以 [验收罗盘](cygnusx-agent-runtime-acceptance-compass.md)、[环境记录](../../evidence/iat-r3-20261018/environment.md) 和相应运行报告为准。不得仅凭单测通过、文档中的计划或 `SKIPPED` 将状态升级为 `PASS_RUNTIME` / `PASS_E2E`。

状态术语：

- `PASS_ISOLATED`：限定隔离测试通过，不证明已部署服务或真实用户流程可用。
- `PASS_RUNTIME`：在获准的隔离运行环境中取得目标服务链路证据。
- `PASS_E2E`：完整用户可见流程有 API、浏览器及必要后端断言支撑。
- `BLOCKED` / `RUNTIME_BLOCKED`：当前缺少必要前置条件，或环境限制了对应验收；查看具体场景的阻塞原因和解除条件。
- `NOT_TESTED` / `SKIPPED`：没有可作为通过依据的结果。

## 推进与安全边界

1. 先确认目标阶段和验收场景，再读对应阶段报告与架构基线。
2. 运行前明确授权范围、隔离环境身份、测试数据生命周期和清理责任；真实服务证据须记录环境与服务身份。
3. 逐场景记录命令、退出码、原始日志、替身范围和未通过项；保留历史矩阵，不用新结果覆盖旧快照。
4. 只有新证据直接覆盖某个验收条件时，才更新该行状态，并同步阶段报告、交接记录和证据清单。
5. 未完成发布评审前，保持下载传输、Agent 写入和相关运行门禁关闭；本导航文档本身不授予运行或发布权限。
