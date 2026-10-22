"""At most two curl embedding probes; never retain credentials or vectors."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

OUTPUT = Path('evidence/embedding-provider-siliconflow/step0.json')


def main() -> int:
    values = {**dotenv_values('.env'), **dotenv_values('.env.test'), **os.environ}
    key = values.get('SILICONFLOW_API_KEY') or values.get('EMBEDDING_PLATFORM_API_KEY')
    previous = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    used = int(previous.get('actual_requests', 0))
    report: dict[str, Any] = {
        'model': 'Qwen/Qwen3-Embedding-8B', 'limit': 2,
        'actual_requests': used, 'extraction_calls': 0,
        'source': 'https://api-docs.siliconflow.cn/docs/api/embeddings-post',
        'requests': previous.get('requests', []) if used else [],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if not key:
        report.update(status='blocked', reason='SiliconFlow credential not configured')
        report['requests'] = [
            {'dimensions_parameter': dim, 'request_sent': False, 'returned_dimensions': None}
            for dim in (None, 1024)
        ]
        OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
        return 2
    if used:
        # Never restart an uncertain or previously attempted real request.
        return 2
    for dim in (None, 1024):
        payload: dict[str, Any] = {'model': report['model'], 'input': 'dimension probe'}
        if dim is not None:
            payload['dimensions'] = dim
        report['actual_requests'] += 1
        report['status'] = 'running'
        OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
        config = '\n'.join([
            'url = "https://api.siliconflow.cn/v1/embeddings"',
            'header = ' + json.dumps('Authorization: Bearer ' + str(key)),
            'header = "Content-Type: application/json"',
            'data = ' + json.dumps(json.dumps(payload)),
        ])
        result = subprocess.run(
            ['curl', '--silent', '--max-time', '60', '--retry', '0',
             '--write-out', '\n%{http_code}', '--config', '-'],
            input=config, text=True, capture_output=True, check=False,
        )
        entry: dict[str, Any] = {'dimensions_parameter': dim, 'request_sent': True,
                                 'curl_exit_code': result.returncode}
        try:
            body, code = result.stdout.rsplit('\n', 1)
            data = json.loads(body)
            entry['http_status'] = int(code)
            vector = (data.get('data') or [{}])[0].get('embedding')
            entry['returned_dimensions'] = len(vector) if isinstance(vector, list) else None
            entry['error_present'] = bool(data.get('error')) or int(code) >= 400
        except (ValueError, TypeError, AttributeError, IndexError):
            entry.update(returned_dimensions=None, error_present=True)
        report['requests'].append(entry)
        OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    report['status'] = 'completed'
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
