# Phase 0B 任务对账 Runbook

用途：确认记录进入 `SUBMITTING` 后，业务副作用与 Redis 状态写回不在同一事务时，
人工恢复任务事实，避免重复创建下载或分析任务。仅限授权运维人员在隔离/生产维护窗口执行。

## 1. 触发条件

- 确认记录为 `SUBMITTING` 且超过正常提交超时。
- Redis 状态写回失败，但 worker/平台日志显示已到达业务提交边界。
- Redis 恢复后发现确认记录与 Task/FileRecord 状态不一致。

## 2. 必须收集的非敏感关联键

`confirmation_id`、`tool_invocation_id`、`task_id`（若已返回）、`request_id`、
`correlation_id`、owner/user UUID、flow_id、execution status、runtime version、
错误码和时间窗口。禁止记录 API key、JWT、confirmation 原值、下载凭据和完整请求体。

## 3. 对账顺序

1. 以 owner + confirmation_id 查询确认记录，核对参数哈希、flow/tool 名、expires_at、
   `SUBMITTING` 时间和 session。不得把另一个 owner 的记录改为当前 owner。
2. 以 task_id 查询 Task；若存在已创建任务，核对 owner、flow_id、idempotency_key、
   参数摘要和队列投递证据。匹配则记录“业务已创建”，不得再次 submit。
3. 若无 task_id，按 request/correlation/tool_invocation 在应用日志、任务事件、队列
   记录和 FileRecord 中查找。只接受可证明的同一请求证据，不按时间相近猜测。
4. 下载任务额外核对 work_dir 是否在 owner 根目录、FileRecord user_id、storage_path、
   Directory 链和下载 worker 状态。发现跨 owner 或 symlink 逃逸，立即隔离产物并阻断继续。
5. 分析任务额外核对生成的 analysis YAML、样本表、比较组和实际 Worker 参数；发现
   最终校验不一致，标记安全事件，不重放。
6. 有匹配 task 时：把确认记录补写为 `SUBMITTED`（带 task_id）或按现有状态机的管理
   修复接口处理，并保存审计事件；无匹配 task 时：将记录标记为 `INVALID`/人工拒绝，
   由新的人类确认重新开始，禁止复用旧 confirmation_id。
7. 所有决策记录 operator、时间、证据引用、旧状态、新状态、task_id 和错误码；不写秘密。

## 4. 禁止事项

- 不自动重试未知是否已执行的业务提交。
- 不把 `user_confirmed=True`、`_confirmed=True` 或伪造 Header 当作凭证。
- 不从 Redis 删除记录来“清理”不确定状态。
- 不跨 owner 查询或修复任务。
- 不直接运行真实大规模下载或生信流程作为对账手段。

## 5. 关闭条件

仅当确认记录、Task/Download、队列/Worker、FileRecord（如适用）和审计事件形成同一
owner/request/task 证据链，并由第二名授权人员复核后关闭。修复完成后重新运行相关
G-06/G-08/G-09/G-10，并把结果和 Manifest 时间戳写回 Closure 报告。

## 6. 隔离环境迁移执行清单

以下命令必须在有 Docker daemon、Unix/loopback socket 和临时 Redis 权限的专用 runner 执行，
使用测试 `.env`，不得挂载生产凭据或连接生产 Redis/PostgreSQL：

```bash
# 1. 版本与 Compose 证据
docker version
docker compose --env-file .env.phase0b.test -f deploy/docker/docker-compose.yml \
  -f deploy/docker/docker-compose.worker.yml config --quiet
docker compose ... up -d db cache web worker
docker inspect --format '{{json .Config.Labels}} {{.Image}}' \
  cygnusx-treasure-mouse-chat cygnusx-treasure-mouse-web cygnusx-worker

# 2. Redis 双消费者、TTL、故障恢复
uv run pytest tests/integration/test_phase0b_redis.py -q -m integration

# 3. 外部 MCP transport（仅回环）
cd mcp-server
.venv/bin/python tests/test_phase0b_runtime.py -v

# 4. 双用户 HTTP/任务/下载闭环
cd ..
uv run pytest tests/integration/test_phase0b_http.py \
  tests/integration/test_phase0b_services.py -q -m integration
uv run python scripts/audit_runtime_provenance.py \
  --output docs/audits/cygnusx-runtime-provenance-manifest.json --strict
```

执行前必须确认 Compose 中的 image tag、build SHA、Worker 挂载和临时 Redis URL 都来自测试
环境；执行后保存 `docker inspect`、容器内 `--version`、Redis 测试输出、MCP initialize/tool
调用日志及脱敏 Manifest。任何一项无法取得容器内证据，保持 BLOCKED，不得用宿主机版本替代。
