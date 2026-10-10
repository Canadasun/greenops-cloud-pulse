#!/usr/bin/env bash
# Copies the truck simulator, its reference data and the six truck certificates to the Azure Files share that the
# cloud truck job runs from (Role 1 – Ying Song; certificates: Role 2 – Marcelbriaud Wafotchoupe).
# Run it after `terraform apply` and again whenever the simulator code or a truck certificate changes.
# Usage: bash scripts/upload_truck_files.sh
set -euo pipefail
cd "$(dirname "$0")/.."
RG=$(terraform -chdir=infra/terraform output -raw resource_group)
ACCOUNT=$(terraform -chdir=infra/terraform output -raw storage_account)
KEY=$(az storage account keys list -g "$RG" -n "$ACCOUNT" --query "[0].value" -o tsv)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/greenops_sim" "$STAGE/contracts" "$STAGE/certs"
cp simulator/requirements.txt "$STAGE/"
cp simulator/greenops_sim/*.py "$STAGE/greenops_sim/"
cp contracts/*.json "$STAGE/contracts/"
cp broker/certs/simulator/TRK-00[1-6].crt broker/certs/simulator/TRK-00[1-6].key "$STAGE/certs/"

az storage file upload-batch --account-name "$ACCOUNT" --account-key "$KEY" -d truck-sim -s "$STAGE" -o none
echo "Uploaded $(find "$STAGE" -type f | wc -l) files to the truck-sim share in $ACCOUNT."
