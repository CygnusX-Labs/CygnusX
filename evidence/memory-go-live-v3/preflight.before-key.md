# 记忆系统接通验收 v3：Step 0 准入受阻

按附件与实施文档 Part 10 的“任一不满足 → 停止，只交 preflight”执行。本轮只做只读准入核查，Step 1–7 均未执行，未完成接通验收。机器证据见同目录 `preflight.json`，调用台账见 `call-ledger.json`。

| 准入项 | Web | Worker |
| --- | --- | --- |
| 进程环境中 embedding 模型、Provider UUID、dimensions 三键 | 均缺失 | 均缺失 |
| 按 PID 1 环境与 cwd 重载 Settings | 模型空、Provider 空、维度默认 1024 | 模型空、Provider 空、维度默认 1024 |
| `SILICONFLOW_API_KEY` 进程环境键 | 缺失 | 缺失 |
| 配置 UUID 对应 active、非 default Provider | 无配置 UUID，无法证明 | 无配置 UUID，无法证明 |
| 同名 `provider-embedding-qwen3` 数据库记录 | 查询结果 0 条 | 查询结果 0 条 |
| 当前容器启动至核查时的日志 | 无含 embedding 的 ERROR 行 | 7 条含 embedding 的 ERROR 行 |

宿主进程、根目录 `.env`、`.env.test` 与两容器 PID 1 环境中均未发现非空 `MEMORY_MAINTENANCE_DATABASE_URL`。根目录两个配置文件虽然包含三行 embedding 配置，但不足以证明运行进程已生效；两文件也没有非空 `SILICONFLOW_API_KEY`。

核查方法：读取 `/proc/1/environ` 与 cwd，在独立 Python 解释器按相同环境重载 Settings；不是对现存 Python 对象的内存检查。Provider 查询使用各自业务连接，只运行 `REPEATABLE READ / READ ONLY` 事务中的元数据 SELECT，确认 `transaction_read_only=on`；没有把业务 DSN 当维护 DSN。日志只保留行数，未输出/保存原文、真实用户内容或密钥。Docker 保留日志可能不覆盖已轮转历史，日志错误计数不等于根因诊断。

运行快照：Web 启动于 2026-10-21 07:59 UTC；Worker 启动于 2026-10-18 11:47 UTC。实际 Compose 文件清单已记录在 JSON。两者定义均以 `env_file: ../../.env` 注入根目录配置（`deploy/docker/docker-compose.yml:53`、`deploy/docker/docker-compose.worker.yml:89`）。不凭配置文件存在推断重建完成。

解锁前置：安全注入 `SILICONFLOW_API_KEY`；在实际目标数据库同步 YAML 并取得真实 UUID；将模型/UUID/维度配置带入 Web、Worker 的运行环境；提供明确授权目标的维护 DSN；检查并处理 Worker 的 embedding ERROR。此轮按停止规则未修改配置、Provider、部署或生产阈值。

配置修复后先重跑只读准入核查：

```bash
uv run python evidence/memory-go-live-v3/collect_preflight.py
```

通过后才能进入维度探测与真实写入/召回。后续回填仍须独立遵守“目标库白名单保护 → 备份 → dry-run 展示 → apply”的顺序；当前 `scripts/backfill_memory_embeddings.py` 静态检查未见库名白名单/目标库二次确认，尚不具备直接执行 apply 的条件。本轮未演示任何 apply。

真实调用：embedding 0/150、抽取 0/20，验收调用成本 0；未修改业务代码或数据库，无合成数据需要清理。无需运行业务代码提交门禁，本次验证为实际容器与只读数据库核查，不以旧单测/stub 代替端到端验收。

最新复核时间（UTC）：2026-10-21T08:40:22.203157+00:00。同一 Step 0 阻断仍存在；本次复核也未调用模型或执行写操作。

第三次连续复核（UTC）：2026-10-21T08:41:16.080085+00:00。同一准入阻断仍存在，目标将标记为 blocked；环境补齐或指定正确运行栈后再恢复。Steps 1–7 未执行，累计验收模型调用仍为 0。
