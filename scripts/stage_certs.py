#!/usr/bin/env python3
"""Prepare least-privilege certificate mounts, without copying the CA private key."""
from pathlib import Path
import shutil
root = Path(__file__).resolve().parents[1] / 'broker/certs'
for private_key in root.glob('*.key'):
    private_key.chmod(0o600)
for service, identities in [('mosquitto', ['mosquitto']), ('router', ['router']), ('simulator', [f'TRK-{i:03}' for i in range(1, 7)])]:
    dest = root / service
    dest.mkdir(mode=0o700, exist_ok=True)
    for name in ['ca.crt', 'crl.pem'] + [name + ext for name in identities for ext in ['.crt', '.key']]:
        source = root / name
        if source.exists():
            shutil.copyfile(source, dest / name)
            (dest / name).chmod(0o600 if name.endswith('.key') else 0o644)
