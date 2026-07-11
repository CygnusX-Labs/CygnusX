# 云端沙盒终端

生信工具箱中的即用即毁隔离容器终端，用户在浏览器中获得交互式 bash shell。

## 架构

```text
浏览器 xterm.js
  ↓ WebSocket
FastAPI 双向代理
  ↓ aiohttp WS
容器内 ttyd:7681 (bash)
  ↑
DockerManager 创建/销毁
```

挂载：`/data/omichub/users/{user_id}/workspace` → `/home/omichub/workspace`

## 配置

所有参数集中在 `tool_configs/terminal/terminal_config.yaml`，修改后自动热重载。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `true` | 功能开关 |
| `image.name:tag` | `omichub/sandbox-terminal:latest` | 容器镜像 |
| `default_resources.memory_mb` | `512` | 默认内存 |
| `lifecycle.idle_timeout` | `1800` | 空闲超时（秒） |
| `lifecycle.max_sessions_per_user` | `2` | 单用户最大并发 |
| `storage.workspace_base` | `/data/omichub/users` | 用户目录基路径 |

## 安全策略

- 根文件系统只读（`read_only=True`）
- `cap_drop ALL` + `no-new-privileges`
- 容器内非 root（`user 1000:1000`）
- 内存/CPU/PID 硬限制
- 仅挂载用户个人 workspace，目录隔离
- `auto_remove=True`，退出即销毁

## 预装工具

`samtools`、`bcftools`、`bedtools`、`fastqc`、`seqkit`、`python3`（numpy/pandas/biopython/pysam）、`vim`、`htop`、`jq`
