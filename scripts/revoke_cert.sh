#!/usr/bin/env bash
# Revokes one device certificate and rebuilds the CRL; the broker refuses it after a reload (FR-03).
# Usage: scripts/revoke_cert.sh TRK-004
set -euo pipefail
cd "$(dirname "$0")/../broker/certs"
openssl ca -config ca.cnf -revoke "$1.crt" 2>/dev/null
openssl ca -gencrl -config ca.cnf -out crl.pem 2>/dev/null
chmod 644 crl.pem
python3 ../../scripts/stage_certs.py
echo "revoked $1; reload the broker: docker compose kill -s HUP mosquitto"
