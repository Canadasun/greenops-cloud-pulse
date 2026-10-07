#!/usr/bin/env bash
# Creates the device-identity certificates for the local IoT Hub stand-in (Role 2 – Marcelbriaud Wafotchoupe).
#   • a private Certificate Authority (CA) – only devices signed by it can connect (FR-03)
#   • one certificate per truck, CN = truck_id (the broker uses the CN as the device name, FR-04)
#   • certificates for the broker itself and for the router service
#   • a "rogue" device signed by a different CA, used to prove unregistered devices are refused
#   • a certificate revocation list (CRL) so a stolen truck certificate can be blocked
# Output goes to broker/certs/ (ignored by Git – certificates are never committed).
set -euo pipefail
cd "$(dirname "$0")/../broker/certs"
umask 077
if [ -f ca.key ]; then
  echo "CA already exists; refusing to replace device identities. Use issue_cert.sh or an explicit rotation procedure." >&2
  exit 1
fi
DAYS=825
TRUCKS="${TRUCKS:-TRK-001 TRK-002 TRK-003 TRK-004 TRK-005 TRK-006}"
rm -rf ca-db && mkdir -p ca-db && touch ca-db/index.txt && echo 1000 > ca-db/serial && echo 1000 > ca-db/crlnumber
cat > ca.cnf <<CNF
[ ca ]
default_ca = greenops
[ greenops ]
dir = ./ca-db
database = \$dir/index.txt
serial = \$dir/serial
crlnumber = \$dir/crlnumber
new_certs_dir = ./ca-db
certificate = ./ca.crt
private_key = ./ca.key
default_md = sha256
default_days = $DAYS
default_crl_days = 365
policy = anything
copy_extensions = copy
[ anything ]
commonName = supplied
CNF
openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 3650 -subj "/CN=GreenOps Device CA" 2>/dev/null
issue() { # name, extra SAN
  openssl req -newkey rsa:2048 -nodes -keyout "$1.key" -out "$1.csr" -subj "/CN=$1" ${2:+-addext "subjectAltName=$2"} 2>/dev/null
  openssl ca -batch -config ca.cnf -in "$1.csr" -out "$1.crt" -notext 2>/dev/null
  rm -f "$1.csr"
}
issue mosquitto "DNS:mosquitto,DNS:localhost,IP:127.0.0.1"
issue router
issue e2e-tester
issue TRK-099   # spare test device: the end-to-end tests revoke it to prove revocation works
for t in $TRUCKS; do issue "$t"; done
openssl ca -gencrl -config ca.cnf -out crl.pem 2>/dev/null
# rogue device: valid-looking certificate from a CA the broker does not trust
openssl req -x509 -newkey rsa:2048 -nodes -keyout rogue-ca.key -out rogue-ca.crt -days 30 -subj "/CN=Unknown CA" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -keyout TRK-666.key -out TRK-666.csr -subj "/CN=TRK-666" 2>/dev/null
openssl x509 -req -in TRK-666.csr -CA rogue-ca.crt -CAkey rogue-ca.key -CAcreateserial -out TRK-666.crt -days 30 2>/dev/null
rm -f TRK-666.csr rogue-ca.srl
chmod 600 *.key
chmod 644 *.crt crl.pem
python3 ../../scripts/stage_certs.py
echo "certificates written to broker/certs: $(ls *.crt | tr '\n' ' ')"
