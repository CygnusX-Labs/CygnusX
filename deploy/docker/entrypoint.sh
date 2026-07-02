#!/bin/sh
# OmicHub 容器启动入口
#
# 在启动主进程前，按需自动应用数据库迁移，保证 schema 与代码同步：
#   - 仅当 RUN_MIGRATIONS=1 时执行（只赋给 web 容器，避免多容器并发迁移竞争）；
#   - 执行 `alembic upgrade head`，幂等（已在 head 则 no-op）；
#   - 迁移失败则容器不启动（fail-fast，避免带病运行）。
set -e

if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "[entrypoint] Applying database migrations: alembic upgrade head"
  alembic upgrade head
fi

exec "$@"
