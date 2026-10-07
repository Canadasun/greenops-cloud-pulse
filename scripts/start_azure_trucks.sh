#!/usr/bin/env bash
# Starts the six simulated trucks on this PC against the Azure deployment (reads the addresses from Terraform).
set -euo pipefail
cd "$(dirname "$0")/.."
export IOTHUB_HOSTNAME=$(terraform -chdir=infra/terraform output -raw iot_hub_hostname)
export FUNCTION_URL=$(terraform -chdir=infra/terraform output -raw function_url)
docker compose -f docker-compose.azure.yml up -d --build
echo "Trucks are sending to $IOTHUB_HOSTNAME. Stop them with: docker compose -f docker-compose.azure.yml down"
