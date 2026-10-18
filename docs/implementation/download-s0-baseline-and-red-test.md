# 下载 S0：基线与真实登记红测试

基线日期：2026-10-16；范围按用户提供的逐阶段提示词首次执行 S0+S1，本报告不代表 S2–S7 已实施。开工先读 ARCHITECTURE_DESIGN/README.md 与下载活动架构；已完整阅读两份实施任务书和既有专项审计。所有旧结论已按当前文件重新核对。

## Stage S0 / Gate G0

- VERIFIED_CODE：Worker `_register_downloaded_files` 仍走 DataFile/FileRepository、checksum空、无task_id、source默认upload；Dataset reconcile按FileRecord.task_id取文件。统一FileRegistry已有task_id/source/checksum参数；无需新表或迁移。
- 主仓分支/HEAD、全量dirty、diff stat、递归子模块状态分别保存在 `evidence/download-s0/{branch,head,status,diff-stat,submodules}.txt`。既有大量Phase3/Agent/前端修改和docs/info删除均为开工前状态；本轮未reset/clean/stash/checkout，也未提交或推送。
- 本轮允许修改：下载Worker、其局部输出校验与工具配置、专用契约测试、下载架构与阶段报告。DatasetImportService、Gateway、FileRegistry及Agent/前端脏文件保持原样；基线内容和SHA在 `evidence/download-s0/before/`、`before-sha256.json`。

## FAIL_BEFORE：不是double写字段的测试

`tests/unit/test_download_registration_contract.py::test_f01_f10_real_worker_register_to_dataset_reconcile` 建临时用户根、真实FASTQ内容、SQLite Task/Ingestion/Version，调用原Worker真实登记入口。测试未构造FileRecord，实际断言失败为：

```text
assert record.task_id == task.id
AssertionError: assert None == UUID(...)
1 failed
```

命令：

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True MPLCONFIGDIR=/tmp/cygnusx-matplotlib \
.venv/bin/python -m pytest tests/unit/test_download_registration_contract.py -q -p no:cacheprovider
```

日志：`evidence/download-s0/red-test.txt`。这是修改实现前的运行结果，不是后来构造的失败示例。最终测试签名随生产入口增加显式task_id；测试仍不手工补FileRecord字段。

测试使用既有SQLite OfflineDB/fixture，补充真实SQL refresh/scalar/savepoint桥接，无真实PG/Redis。初次运行因沙箱线程事件循环自唤醒/关闭阶段停等，经明确中止确认后诊断；测试加入定时唤醒及在线程唤醒仍有效时shutdown_default_executor，真实to_thread/文件/SQL操作均未被替换。诊断日志另存red-test-diagnostic.txt，不以超时当成业务断点。测试显式启用本地模型成本表缓存，避免导入期的非必要远程更新。

## G0 决策与保护

G0=PASS_ISOLATED：当前基线、失败断言、真实生产登记入口和隔离范围已证明。未调用下载CLI、Queue、生产API/DB、真实Redis/PG、Docker或外部来源；未开启源码写门禁/worker_paths_verified。没有依赖安装、锁文件修改或生产迁移。后续G1另见S1报告。
