#!/usr/bin/env bash
# Registers one more device: issues a certificate signed by the GreenOps Device CA (Role 2).
# Usage: scripts/issue_cert.sh TRK-007     (run scripts/make_certs.sh once first)
set -euo pipefail
cd "$(dirname "$0")/../broker/certs"
umask 077
openssl req -newkey rsa:2048 -nodes -keyout "$1.key" -out "$1.csr" -subj "/CN=$1" 2>/dev/null
openssl ca -batch -config ca.cnf -in "$1.csr" -out "$1.crt" -notext 2>/dev/null
rm -f "$1.csr"; chmod 644 "$1.crt"; chmod 600 "$1.key"
python3 ../../scripts/stage_certs.py
echo "issued $1"
