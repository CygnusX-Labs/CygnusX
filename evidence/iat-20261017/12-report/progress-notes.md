# IAT-20261017 验收记录（进行中）

> 环境: cygnusx-iat-20261017-zj · 非生产隔离验收 · 主仓 HEAD d9c92cf6ee1c
> 隔离栈: cygnusx-ri095-acceptance（internal network, UID 10001, PG14.23, Redis7.4）

## 已完成（真实运行证据）

### P0 环境准入
- ENV-01 授权: /home/zj/ri095-private/acceptance.env (mode 600, flags 全 false), control.py fail-closed 校验
- ENV-02 工作树: evidence/iat-20261017/01-baseline/env-02-manifest.txt (HEAD + 636 dirty + submodule SHA)
- ENV-03/05/06: evidence/iat-20261017/03-env-runtime/env-03-06-runtime-identity.log (PG/Redis/Worker 身份+digest+queue)
- ENV-04 IPC: evidence/iat-20261017/03-env-runtime/env-04-ipc.log (exit 0)
- ENV-07 冻结门禁: evidence/iat-20261017/03-env-runtime/env-07-frozen-gate.log (gate 关闭+运行时拒绝)

### P1 隔离基线 (PASS_ISOLATED)
- upload gate: 1 passed (exit 0)
- download reliability: 34 passed (exit 0)
- agent/gateway/langgraph: 133 passed (exit 0)
- redis integration: 1 skipped (BLOCKED: 无本地 redis-server)
- G3 boundary: 9 skipped (NOT_TESTED)

### P2 S4-B1 (PASS_RUNTIME, 真实 PG)
- p2_harness: 14/14 PASS — PG-01..07, FR-05, FR-06, REC-01, REC-03, REC-05, MQ-04, MQ-02
- p2_fr_harness: 4/4 PASS — FR-01..04 (真实 FileRegistry + SHA-256 独立复核)

### P3 S5-C2 (PASS_RUNTIME, 真实 PG+Redis)
- p3_s5_harness: 8/8 PASS — AG-02, AG-04, AG-05, AG-07, AG-09, AG-10, AG-13, AG-16
- AG-01 HTTP callback: 进行中 (JWT secret 对齐修复后待重跑)

### G3
- BLOCKED: TrustedExecutionAdapter 为 Protocol-only, 无 OS Supervisor 实现, trusted_http_driver skip

## 待完成
- AG-01 重跑
- P4 浏览器评估 (先前 attempt1: BLOCKED — Chromium sandbox 无法在容器启动, host apparmor_restrict_unprivileged_userns=1)
- 验收矩阵 CSV 填写
- 最终报告
