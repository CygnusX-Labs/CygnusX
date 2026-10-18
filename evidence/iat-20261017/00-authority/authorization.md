# ENV-01 授权与资源边界（脱敏）

- ENVIRONMENT_ID: cygnusx-iat-20261017-zj
- 操作者: zj (uid=1000, docker 组) — 本机为授权 disposable 非生产环境
- 授权范围: 仓库已有 deploy/acceptance 隔离栈的启动/停止/日志采集; 只读审计源码; 独立 PG 测试数据读写; 隔离 Redis key 操作; 本机 Chromium UI 驱动
- 明确禁止: 提交/推送 git; 操作生产栈 (cygnusx project 的生产容器只读观察); 翻转冻结门禁 (DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED / WRITE_RUNTIME_ACCEPTED / agent_*_write_enabled); 真实外部下载; FLUSHALL/down -v/rm -rf 未知对象
- 隔离栈: Compose project cygnusx-ri095-acceptance (internal network, 无宿主发布端口, UID 10001, cap_drop ALL)
- PG: 独立实例, db=project_export_test_ri095, user=ri095_acceptance, PG 14.23, alembic head=projectreport01
- Redis: 独立实例 7.4.11, broker=db1, result=db2, delegation/confirmation keyspace=db0 (测试专用)
- 测试用户: iat_user_a / iat_user_b (本环境注册, 测试密码仅本环境有效)
- 私有 env: /home/zj/ri095-private/acceptance.env (mode 600, 不入 git)
- 清理责任: 运行结束后 control.py stop 保留卷与证据; 卷保留至负责人确认保留期

硬停止检查: 全部连接指向隔离实例, 无生产对象, 门禁保持关闭 ✓
