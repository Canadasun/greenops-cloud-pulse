#!/usr/bin/env bash
# Registers each truck in Azure IoT Hub with its own X.509 certificate (Role 2 – Marcelbriaud Wafotchoupe; FR-03, FR-04).
# IoT Hub stores only the certificate's SHA-256 thumbprint; the private key never leaves the truck (this PC).
# Usage: bash scripts/register_azure_devices.sh <iot-hub-name>      (needs: az extension add --name azure-iot)
set -euo pipefail
HUB="${1:?IoT Hub name, e.g. from: terraform -chdir=infra/terraform output -raw iot_hub_name}"
CERTS="$(dirname "$0")/../broker/certs"
TRUCKS="${TRUCKS:-TRK-001 TRK-002 TRK-003 TRK-004 TRK-005 TRK-006}"
for t in $TRUCKS; do
  thumb=$(openssl x509 -in "$CERTS/$t.crt" -noout -fingerprint -sha256 | cut -d= -f2 | tr -d ':')
  if az iot hub device-identity show -n "$HUB" -d "$t" >/dev/null 2>&1; then
    az iot hub device-identity update -n "$HUB" -d "$t" --set "authentication.x509Thumbprint.primaryThumbprint=$thumb" -o none
    echo "$t primary thumbprint updated; secondary retained for rotation"
  else
    az iot hub device-identity create -n "$HUB" -d "$t" --am x509_thumbprint --ptp "$thumb" --stp "$thumb" -o none
    echo "$t registered (thumbprint ${thumb:0:12}…)"
  fi
done
