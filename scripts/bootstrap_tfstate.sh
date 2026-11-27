#!/usr/bin/env bash
# Creates the remote home of the Terraform state (Part 1, Table 6; Role 2 – Marcelbriaud Wafotchoupe).
# Run once, before `terraform init -migrate-state`. Safe to run again: every step checks first.
# The state gets its own resource group so destroying the application never deletes its own state.
set -euo pipefail

RG="${TFSTATE_RG:-rg-greenops-tfstate}"
SA="${TFSTATE_ACCOUNT:-stgreenopsg3tfstate}"
CONTAINER="${TFSTATE_CONTAINER:-tfstate}"
LOCATION="${TFSTATE_LOCATION:-canadacentral}"
# College policy requires Environment=Lab and Course=CST8912 on every resource group.
TAGS=(Environment=Lab Course=CST8912 "ProjectCourse=CST8922 Capstone Project" Purpose=terraform-state)

echo "Resource group $RG ($LOCATION)"
az group create --name "$RG" --location "$LOCATION" --tags "${TAGS[@]}" --output none

if ! az storage account show --name "$SA" --resource-group "$RG" --output none 2>/dev/null; then
  echo "Storage account $SA"
  az storage account create --name "$SA" --resource-group "$RG" --location "$LOCATION" \
    --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
    --allow-blob-public-access false --allow-shared-key-access false \
    --tags "${TAGS[@]}" --output none
fi

echo "Blob versioning and 14-day soft delete (a bad state can be rolled back)"
az storage account blob-service-properties update --account-name "$SA" --resource-group "$RG" \
  --enable-versioning true --enable-delete-retention true --delete-retention-days 14 \
  --enable-container-delete-retention true --container-delete-retention-days 14 --output none

# Shared keys are off, so access is by sign-in only: give the signed-in person the data role.
SCOPE=$(az storage account show --name "$SA" --resource-group "$RG" --query id --output tsv)
ME=$(az ad signed-in-user show --query id --output tsv)
if [ -z "$(az role assignment list --assignee "$ME" --scope "$SCOPE" --role "Storage Blob Data Contributor" --query '[].id' --output tsv)" ]; then
  echo "Storage Blob Data Contributor for the signed-in user"
  az role assignment create --assignee-object-id "$ME" --assignee-principal-type User \
    --role "Storage Blob Data Contributor" --scope "$SCOPE" --output none
fi

echo "Blob container $CONTAINER (role assignments can take a few minutes to apply)"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if az storage container create --name "$CONTAINER" --account-name "$SA" --auth-mode login --output none 2>/dev/null; then
    echo "Done. Next: cd infra/terraform && terraform init -migrate-state"
    exit 0
  fi
  echo "  waiting for the role to apply (attempt $attempt)"; sleep 30
done
echo "Container could not be created - check the role assignment" >&2
exit 1
