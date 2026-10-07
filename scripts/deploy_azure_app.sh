#!/usr/bin/env bash
# Publishes the code to the Azure resources created by Terraform:
#   Functions (Roles 3, 4, 5) -> Flex Consumption Function app, with contracts/ bundled in
#   Dashboard (Role 5)        -> Static Web Apps, built to call the Function app directly
set -euo pipefail
cd "$(dirname "$0")/.."
TF="terraform -chdir=infra/terraform output -raw"
FUNC_APP=$($TF function_app); FUNC_URL=$($TF function_url)

stage=$(mktemp -d)
cp -r functions/. "$stage/"
(cd "$stage" && rm -rf .venv tests .pytest_cache local.settings.json && find . -name __pycache__ -prune -exec rm -rf {} +)
cp -r contracts "$stage/contracts"
(cd "$stage" && func azure functionapp publish "$FUNC_APP" --python)
rm -rf "$stage"

# Separate output folder, so the local dist/ (used by the browser tests) is never an Azure build
(cd dashboard && VITE_API_BASE="$FUNC_URL" npx vite build --outDir dist-azure --emptyOutDir)
npx --yes @azure/static-web-apps-cli@2 deploy dashboard/dist-azure --deployment-token "$($TF swa_deployment_token)" --env production
echo "Dashboard: $($TF dashboard_url)"
