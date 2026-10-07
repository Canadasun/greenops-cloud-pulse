#!/usr/bin/env python3
"""Prepare least-privilege certificate mounts, without copying the CA private key.

Each service folder is readable by its owner and its group only. The containers run as UID/GID 1000, so on a host
where the files belong to another user (e.g. the CI runner) give the folders to group 1000 once
(sudo chgrp -R 1000 ...); the setgid bit keeps that group on files written here later."""
from pathlib import Path
import shutil
root = Path(__file__).resolve().parents[1] / 'broker/certs'
for private_key in root.glob('*.key'):
    private_key.chmod(0o600)
for service, identities in [('mosquitto', ['mosquitto']), ('router', ['router']), ('simulator', [f'TRK-{i:03}' for i in range(1, 7)])]:
    dest = root / service
    dest.mkdir(exist_ok=True)
    dest.chmod(0o2750)
    for name in ['ca.crt', 'crl.pem'] + [name + ext for name in identities for ext in ['.crt', '.key']]:
        source = root / name
        if source.exists():
            shutil.copyfile(source, dest / name)
            (dest / name).chmod(0o640 if name.endswith('.key') else 0o644)
