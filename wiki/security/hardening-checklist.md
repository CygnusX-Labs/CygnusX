# 安全加固清单

本清单汇总 `SECURITY_AUDIT.md` 识别的 24 项安全修复及生产检查项。

## 24 项安全修复概览

| 编号 | 风险 | 修复位置 |
|---|---|---|
| #1 | 路径穿越 → 任意文件读取 | `file_service.py` / `report_service.py` |
| #2 | `/tracks/` 无鉴权暴露用户数据 | `nginx.conf` / `nginx.prod.conf` |
| #3 | 生产环境默认 JWT 密钥 | `config.py` |
| #4 | Redis 无密码 + 端口暴露 | `docker-compose.yml` / `config.py` |
| #5 | AI Provider key / TOTP secret 明文落盘 | `config.py` |
| #6 | MCP stdio/SSE 的 RCE/SSRF | `mcp/client.py` / `mcp_service.py` |
| #7 | nginx 缺失安全头 + 聊天上传无校验 | `nginx.conf` / `files.py` |
| #8 | Flower 监控无鉴权 | `docker-compose.yml` |
| #9 | 云存储 URI 只校验 scheme | `schemas/download.py` |
| #10 | cookie balance Redis 频道无命名空间 | `cookie_pubsub.py` |
| #11 | 登录端点仅全局限流 | `auth.py` / `login_rate_limit.py` |
| #12 | 终端会话 ID 熵低 | `terminal_service.py` |
| #13 | WebSocket 异常 detail 回传客户端 | `sandbox.py` |
| #14 | AI key 可能进异常日志 | `openai_compatible.py` |
| #15 | WebSocket 未校验用户禁用状态 | 多个 WebSocket 端点 |
| #16 | Chat 附件读取 SSRF | `chat_service.py` |
| #17 | MCP stdio command 路径遍历 / args 未校验 | `mcp/client.py` |
| #18 | AI Tool Call 参数无 schema 校验 | `ai_tools.py` |
| #19 | 登录限流 XFF 首个 IP 可伪造 | `login_rate_limit.py` |
| #20 | JWT 无吊销机制 | `security.py` / `deps.py` / user model |
| #21 | 沙盒容器未做网络隔离 | `sandbox/pool.py` / `config.py` |
| #22 | 聊天文件上传全局可访问 | `files.py` / `chat_service.py` |
| #23 | TOTP `required` 策略未生效 | `auth_service.py` |
| #24 | 依赖存在已知 CVE（ecdsa） | `pyproject.toml` / `security.py` |

## 首次部署必填环境变量

```bash
JWT_SECRET_KEY=your-random-secret
APP_SECRET_KEY=your-random-secret
REDIS_PASSWORD=your-redis-password
AI_PROVIDER_KEY_ENCRYPTION_KEY=your-fernet-key
FLOWER_BASIC_AUTH=admin:your-strong-password
```

## 生产检查项

- [ ] `APP_ENV=production`、`APP_DEBUG=false`
- [ ] 所有密钥已设置且非默认值
- [ ] DB/Redis 端口不暴露
- [ ] Flower 关闭
- [ ] SSL 证书挂载
- [ ] `/tracks/` 仅限内网
- [ ] 沙盒网络隔离
- [ ] 聊天附件按用户隔离
- [ ] `pip-audit` 无高危漏洞
