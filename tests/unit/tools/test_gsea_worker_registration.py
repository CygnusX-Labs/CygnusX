"""从新进程的默认 Worker 加载链验证 GSEA 可消费，避免测试间导入掩盖漏注册。"""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_default_worker_registers_gsea_and_routes_it_to_analysis() -> None:
    script = """
from cygnusx.infrastructure.celery_app.celery import celery_app
assert 'cygnusx.tools.gsea.tasks' in celery_app.conf.include
celery_app.loader.import_default_modules()
name = 'cygnusx.tools.gsea.tasks.run_gsea_task'
assert name in celery_app.tasks
assert celery_app.amqp.router.route({}, name)['queue'].name == 'analysis'
print('GSEA_WORKER_REGISTRATION_OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=45,
        env={**os.environ, "LITELLM_LOCAL_MODEL_COST_MAP": "True"},
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "GSEA_WORKER_REGISTRATION_OK" in result.stdout
