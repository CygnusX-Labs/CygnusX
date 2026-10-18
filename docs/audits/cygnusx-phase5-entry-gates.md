# Phase5 准入核验

当前档位：**PLAN_ONLY**。分支 `feat/research-agent-phase5`，基线提交 `51011118`（Phase4 已由人工提交）；这不代表 Phase4 的真实验收已通过。

| 条件 | 当前证据 | 结论 |
|---|---|---|
| Phase4 实施报告与代码 | 实施报告、bioopsphase4、ResearchProvenanceService、独立科学/证据 job 存在 | CODE_IMPLEMENTED / ISOLATED_VALIDATED，非 READY |
| Phase4 真实双报告 | Quarto kernel socket 权限失败；报告明确无完整真实 E2E | BLOCKED |
| PostgreSQL / Redis | 本轮重新尝试本地 socket，均 PermissionError errno 1 | BLOCKED；未连接业务数据库 |
| Docker / Worker | Docker socket 同样拒绝，无法回读镜像/挂载/二进制 | BLOCKED |
| MCP 真 Transport / Redis 双进程 CAS | 无新增可复核成功记录，不能用进程内测试替代 | BLOCKED |
| Treasure 来源 / Worker Flow 来源 | 历史 Closure 缺口未出现闭合证据 | BLOCKED |
| 双用户全栈 / 下载预算 / 公开案例 | 无对应新运行证据，未获案例资源预算批准 | BLOCKED |
| Agent 写入 | WRITE_RUNTIME_ACCEPTED=False；Phase4 两开关默认 false | 保持关闭 |

本轮可进行结构化规划、持久化计划草案、只读/prepare 协调、合成隔离测试和基准评估基础设施。计划元数据持久化不等于提交科研业务任务。真实下载/计算/发布仍拒绝，审批不能把门禁变为 READY。G0/G15/G16 未通过前不开展两个真实公开案例，也不预设 GSE/SRR。

本地证据：`evidence/phase5/baseline.json`、`runtime-probes.json`。基线记录原始 dirty 状态、分支、HEAD、diff stat、递归子模块和文件哈希；保留 `.env.example` 与 5 个子模块既有修改，不写这些文件。历史依据为 Phase0B/Closure、Phase2/3 实施报告和 Phase4 完整报告。证据层级分别记录，历史 PASS 不自动升级本轮 Runtime PASS。
