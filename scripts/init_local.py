#!/usr/bin/env python3
"""Create local credentials once. Does not overwrite existing configuration or print keys."""
import os
import secrets
from pathlib import Path
root = Path(__file__).resolve().parents[1]
p = root / '.env'
existing = p.read_text() if p.exists() else ''
values = {
    'SESSION_SIGNING_KEY': secrets.token_urlsafe(48),
    'FAULTS_READ_TOKEN': secrets.token_urlsafe(32),
    'INGESTION_TOKEN': secrets.token_urlsafe(32),
    'MAIL_RELAY_TOKEN': secrets.token_urlsafe(32),
    'DELIVERY_CALLBACK_TOKEN': secrets.token_urlsafe(32),
    'SIM_CONTROL_TOKEN': secrets.token_urlsafe(32),
}
known = {line.split('=', 1)[0] for line in existing.splitlines() if '=' in line}
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
with os.fdopen(fd, 'a') as f:
    if existing and not existing.endswith('\n'): f.write('\n')
    for key, value in values.items():
        if key not in known: f.write(f'{key}={value}\n')
p.chmod(0o600)
print('Local credentials are in .env (mode 0600). Open http://localhost:5173 and choose a sample person to sign in.')
