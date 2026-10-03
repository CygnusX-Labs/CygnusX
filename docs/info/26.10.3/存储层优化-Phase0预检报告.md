# 存储层优化 · Phase 0 预检报告

> 执行：2026-10-04 · 依据《存储层优化实施方案.md》§2 · 环境：feat/skill-route-first + live compose 栈

## 0.1 G-A 安全证伪（门禁）——✅ 不可达，通过

**按 path/id 解析文件的端点逐一审查 + 实测：**

| 端点 | 路径解析逻辑 | 越权测试结果 |
|---|---|---|
| `GET /files/preview?path=` | `validate_workspace_path`（file_service.py:279）拒绝绝对路径与 `..`，前缀强制 `users/{uid}/`（:557 `rel = f"users/{user_id}/{normalized}"`） | 平台全局目录（output/、studio/、.sandbox-pool/）**构造不出**——任何 path 都被钉死在 users/{uid}/ 下 |
| `GET /files/{id}/download` | `get_file_path`（:742）按 file_id 查 `file_records` + `get_visible` 归属校验 + `_require_read_access`，越权 404 | id 类端点无法凭空构造路径——只读 DB 已登记且归属本用户的记录 |
| `POST /files/{id}/presigned-download` | 同上（`create_presigned_download`:619） | 同上 |
| `GET /files/picker` | `list_visible(user_id)`（:879）只返回本人可见记录 | 无 path 入参 |
| `GET /tracks/`（nginx 直链） | `location ^~ /tracks/ { alias /data/cygnusx/; allow RFC1918; deny all }`（live 容器 nginx.conf:166-179） | **实测全部 404/403**（见下） |

**/tracks/ 实测（构造请求）**：
- `curl http://127.0.0.1:8888/tracks/output/agentteams/{case}/downloads/` → **404**
- `curl .../tracks/users/{uid}/downloads/PRJNA1285930/SRR34360215.sra` → **404**
- `curl .../tracks/bin/EBIDownload`、`.../tracks/blast/db/` → **404**
- 容器内自访 → **403**（容器源 IP 192.168.80.4 命中 allow 名单仍 403，XFF 伪造无效）

**根因（意外发现，比 G-A 更重要）**：live nginx 容器内 **`/data/cygnusx` 不存在**（`docker exec cygnusx-nginx ls /data/cygnusx` → No such file or directory；容器只挂载了 `/data/omichub -> /data/omichub`）。alias 指向空处 → **当前 /tracks/ 直链对一切路径 404，JBrowse 直链功能整体失效**。这是 STORAGE_PATH 迁移（/data/cygnusx → /data/omichub）时 alias 没跟着改的硬编码残留（G-B 家族），与方案 §3.3 的 5 处硬编码同源——**应在 Phase 1 一并修复**（alias 改 `${STORAGE_PATH}/`），修好后 /tracks/ 恢复可达，届时 allow 名单（RFC1918）是唯一防线（设计如此，注释已声明公网需改鉴权代理，非本方案范围）。

**G-A 结论：落档——平台全局目录不可达，无安全事件，Phase 1+ 放行。**（附带产出：/tracks/ alias 失效 bug 待 Phase 1 修复）

## 0.2 GC 存量 —— 极小

```
du -sh /data/omichub/output/agentteams → 12K
结构：bioops_2e66118b9a1a48fca9656c097d2a0a5e/downloads/（单 Case，几乎空）
```
GC 服务硬编码 `/data/cygnusx`（agentteams_evidence_gc_service.py:47 `_clean_local_workdir`）从未在真实数据根生效——但 live 数据量 12K，**无积压风险**。Phase 1 修复后首轮清理预期清 0~1 个 Case 目录。

## 0.3 mas_workspace_root / WorkspaceLayout —— 活故障确认

- `core/config.py:162` `mas_workspace_root: str = "/data/cygnusx"` 默认值；`.env` **无覆盖**（grep 零命中）、compose 无 `MAS_WORKSPACE_ROOT`、live 容器 env 无该项 → **MAS 全部走旧根默认值**（活故障）。
- `WorkspaceLayout(` 实例化点 **7 处**（mas_service.py:40 + celery_app/tasks/mas.py ×6），**全部显式传 root**（`WorkspaceLayout(self._settings.mas_workspace_root)` / `(get_settings().mas_workspace_root)`）→ 修 config 默认值即可全覆盖，调用点无需逐个改。方案 §3.3 说"默认参数移除、强制显式传"仍可做，但实例化点已全部显式，风险极低。
- 佐证：worker 容器内 `/data/cygnusx/` 只剩一个 `logs` 目录（且属旧残留）；`/data/cygnusx/users/user-1/workspace`（08-27 mtime）是旧根时代 MAS 测试残留。
- 另：`deploy/mas/mas-apptainer-worker.env.example:11` `MAS_WORKSPACE_ROOT=/data/cygnusx` 也是硬编码残留，Phase 1 一并改。

## 0.4 agentteams_data_tool_service.py:259 fallback —— 潜伏（未见 live 触发）

```python
destination_root = Path(str(context.extra.get("workdir") or
    f"/data/cygnusx/output/agentteams/{case_id}/downloads")).resolve()
```
- 触发条件：`ToolInvocationContext.extra["workdir"]` 缺失。该 extra 的写入方是 `parallel_subagent_service.py:1376`（会诊 fan-out 子代理工具执行时注入 `subagent_workdir`）。
- **全仓检索 `subagent_workdir` 消费方：除写入处外零命中**——即 extra 传了但没人读，`agentteams_data_tool_service` 读的是 `workdir` 键（另一名字）。两条线索交叉确认**挂载断裂**（方案 §3.2 的 Gap）：子代理的 workdir 既没挂进沙盒容器，data tool 也读不到 `subagent_workdir`。fallback 到 `/data/cygnusx/output/agentteams/{case}/downloads` 后 `mkdir(parents=True)` 会**在宿主旧根创建目录**——但 `/data/cygnusx` 在 web 容器内不存在（挂载的是 /data/omichub），mkdir 会抛 OSError → 实际表现为产物落盘失败而非静默写旧根。live 无 agentteams 下载产物目录增长，判定**潜伏未触发**。
- 修法确认：fallback 改走 `get_storage_config().data_root / "output/agentteams/{case_id}/downloads"`（Phase 1.3）+ 接通挂载（Phase 1.2）。

## 0.5 /data/cygnusx 旧根写入检测 —— 09-20 后无写入

```
find /data/cygnusx -newermt '2026-10-01' → 空
9 月后变更仅：bin/EBIDownload{,.yaml}（2026-09-20 18:57，部署脚本一次性复制）
/data/cygnusx/users/user-1/workspace（08-27，MAS 旧根残留）
```
**无进程在写旧根**（bin 是部署产物非运行时写入）。旧根可安全归档/删除（另列运维事项，不在本方案动）。

## 0.6 temp 清理任务执行确认

beat 已登记 `cleanup-expired-archives`（celery.py:116，每日 02:00 → `storage.cleanup_expired`）且 beat/worker 均健康运行。`file_records` 中 status='temp'/'uploading' 记录数为 0，temp/ 物理为空。昨晚（10-04 02:00）执行证据需查 `docker logs cygnusx-worker | grep cleanup_expired`——按方案「仅记录不阻塞」。

## 汇总

| # | 结论 | 对后续 Phase 影响 |
|---|---|---|
| 0.1 G-A | **通过**（全局目录不可达）；附带发现 /tracks/ alias 失效 | Phase 1 放行；新增修复项：nginx alias 改 `${STORAGE_PATH}/`（nginx.conf:168 + nginx.prod.conf:121 + JBrowseLinkGenerator 注释） |
| 0.2 | GC 存量 12K，无积压 | Phase 1 修复后首轮清理量可忽略 |
| 0.3 | mas_workspace_root 活故障；7 实例化点全显式传 root | Phase 1 只改 config 默认值 + env example |
| 0.4 | fallback 潜伏；`subagent_workdir` 零消费方证实挂载断裂 | Phase 1.2/1.3 修法按方案执行 |
| 0.5 | 旧根 9-20 后零写入 | 修复无并发写入风险 |
| 0.6 | 任务已调度，无积压待清 | 仅记录 |
