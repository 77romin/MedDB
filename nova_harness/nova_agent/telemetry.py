"""Append-only local experiment traces. Never log HTTP headers or environment dumps."""
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


class Trace:
    def __init__(self, path=None, secrets=()):
        self.path = Path(path) if path else None
        self.secrets = tuple(x for x in secrets if x)
        self.lock = threading.Lock()
        self.sequence = 0
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)

    def clean(self, value):
        if isinstance(value, dict):
            return {k: ('[REDACTED]' if str(k).lower() in {'authorization', 'token', 'api_key', 'nova_dev_key', 'nova_run_token'} else self.clean(v)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[REDACTED]')
            return re.sub(r'Bearer\s+[^\s"<>]+', 'Bearer [REDACTED]', value, flags=re.I)
        return value

    def emit(self, event, **fields):
        if not self.path:
            return
        with self.lock:
            self.sequence += 1
            row = self.clean({'seq': self.sequence, 'event': event,
                             'at': datetime.now(timezone.utc).isoformat(), 'monotonic': time.monotonic(), **fields})
            with self.path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
