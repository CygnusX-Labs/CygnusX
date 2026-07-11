# 生产环境检查清单

部署到生产前逐项确认：

- [ ] `APP_ENV=production`、`APP_DEBUG=false`
- [ ] `JWT_SECRET_KEY`、`APP_SECRET_KEY`、`REDIS_PASSWORD`、`AI_PROVIDER_KEY_ENCRYPTION_KEY` 已设置且非默认值
- [ ] `OMICHBUB_INIT_ADMIN_PASSWORD` 为强密码
- [ ] 数据库端口在 `docker-compose.prod.yml` 中关闭
- [ ] Redis 端口在 `docker-compose.prod.yml` 中关闭
- [ ] Flower 服务 `replicas: 0`
- [ ] SSL 证书已挂载到 nginx
- [ ] `/tracks/` 仅允许受信内网访问
- [ ] 沙盒容器网络隔离：`SANDBOX_NETWORK_ISOLATED=true`
- [ ] 聊天附件按用户隔离
- [ ] `pip-audit` 无高危以上漏洞

## 关键环境变量

| 变量 | 要求 |
|---|---|
| `JWT_SECRET_KEY` | ≥32 字节随机字符串 |
| `APP_SECRET_KEY` | 随机字符串 |
| `REDIS_PASSWORD` | 强密码 |
| `AI_PROVIDER_KEY_ENCRYPTION_KEY` | Fernet 32 字节 base64，设置后不可更改 |
| `OMICHBUB_INIT_ADMIN_PASSWORD` | 强密码 |
