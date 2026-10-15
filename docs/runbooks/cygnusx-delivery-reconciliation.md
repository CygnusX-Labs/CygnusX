# CygnusX 科研交付对账与回滚

当前运行准入 BLOCKED；本规程不授权连接生产或解除门禁。

## 准入

核实 Phase0B Closure 和 Phase1–3 未关闭项，完成隔离 PostgreSQL 迁移/并发、Redis CAS/TTL/故障、MCP STDIO/HTTP 鉴权、Worker 镜像/二进制/挂载/版本回读。之后取得小型非生产数据来源和预算批准才做 G17。禁止直接修改源码门禁充当验收。

评审后先迁移再启用只读。写入还需源码运行门禁、既有 operation flags 和 delivery write flag 全部通过。Quarto Python 由可信运维固定到已验证含 nbformat/Jupyter 的环境；隔离内核需要 socket 权限。本轮沙箱不具备该权限，不在生产临时安装依赖。

## 诊断与恢复

1. owner 身份读取 Task provenance / 项目 research-delivery，核查 actual Task/link、DatasetVersion、Handoff、参数和 Flow 摘要。提案 ID 不能替代 Task ID。
2. 分开看分析、输入、产物、证据及交付状态；分析 success + manifest 缺失仍不交付。保留输入/输出原件，不修改旧 Handoff/Snapshot。
3. 检查既有 `/reports/jobs/{job_id}` 的错误码、attempt_count、retryable。对失败报告调用既有 `/reports/jobs/{job_id}/retry`，只重试冻结事实对应的报告；禁止调用分析或下载 submit/retry。
4. 显式人工对账：人类 JWT POST `/tasks/{task_id}/research-delivery/reconcile`，body `{request_key: 新UUID, repair_reports: true}`。业务门禁在对账副作用前检查；同 key 复用 job。此入口只登记既有输出与报告，不重放科研计算。
5. 科学报告修复使用新归档/版本；证据 HTML 丢失只允许从同一快照重建完全相同 SHA-256/大小的字节。已有损坏归档、缺失 PDF、模板不匹配保留 PARTIAL/BLOCKED，从可信备份人工恢复，不能静默覆盖。
6. SUBMITTING / RECONCILIATION_REQUIRED 或队列投递不明：先查实际 Task 与队列记录，人工确认是否已接收；绝不自动再提交昂贵分析。

## 回滚与保全

先关闭两个 delivery flags，暂停新对账/报告消费，保留全部用户文件、Dataset、FileRecord、Task、Report 和 Snapshot。依据 `evidence/phase4/baseline.json` 与 baseline-files/ 仅逆向本轮 hunk；禁止整文件 reset/revert 覆盖既有 dirty 成果。

日常撤回使用关闭开关，不直接 downgrade。若确需 `bioopsphase4 → bioopsphase3`，先离线备份新 observation 及关联字段，确认应用不再读取新列，在隔离库验证后另行批准。downgrade 删除新增证据表/列，不删除既有核心记录或用户文件，但会丢失本阶段关系，未备份不得执行。

## 再验收

运行完整隔离测试、前端类型/构建、门禁矩阵；补齐真实 PG/Redis/MCP/Worker/BioReport 与经批准公开科研案例。当前不准入需要自动执行/发布的 Phase5。
