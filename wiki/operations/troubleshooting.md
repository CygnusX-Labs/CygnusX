# 问题排查

## 登录后页面空白

- 浏览器强制刷新 `Ctrl+Shift+R`
- 检查 `docker logs omichub-web`
- 确认 nginx 挂载最新 `frontend/dist`，执行 `make docker-reload`

## 上传文件失败

- 检查 Nginx/后端上传大小限制
- 大文件建议通过服务器本地拷贝
- 检查 `/data/omichub/uploads` 权限

## 任务一直等待中

- Worker 栈是否已启动：`make docker-up-worker`
- Redis 是否可连接：`docker logs omichub-cache`
- Worker 日志是否有报错：`make docker-logs-worker`

## 任务运行失败

查看任务详情「实时日志」，重点检查：

- 输入文件路径是否正确
- 样本信息是否完整（分组、配对）
- 参考基因组是否已配置
- 工作目录磁盘空间
- Conda 环境/容器镜像是否包含所需软件

## 数据库相关 500 错误

```bash
make check-alembic-heads
```

若存在 Multiple Heads：

```bash
make migrate-merge
```

## 权限事故

如果登录页提示系统内部错误，且日志报 `/app/logs/omichub.log` 权限错误：

```bash
make docker-fix-permissions
docker restart omichub-web omichub-worker omichub-beat
```

## AI 助手无法回复

- 确认已配置 AI Provider（`data/ai_providers.yaml` 或 `.env`）
- 检查网络能否访问模型 API
- 查看后端日志中的 API 调用失败记录
