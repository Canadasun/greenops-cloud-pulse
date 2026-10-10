# ---- Cloud trucks (Role 1 – Ying Song; Role 2 – Marcelbriaud Wafotchoupe): the six simulated trucks run as an
# Azure Container Apps job instead of on one member's PC. Anyone with Contributor on the resource group starts a run
# with "Run now"; the run stops itself after var.truck_run_minutes, so a forgotten demo cannot use up the IoT Hub F1
# daily message quota or the Container Apps free grant.
# No private registry (it would cost more than the rest of the system): a public Microsoft Python image installs the
# simulator's one dependency at start and runs the code and certificates from an Azure Files share.
# Fill or refresh the share with scripts/upload_truck_files.sh.

resource "azurerm_storage_share" "truck_sim" {
  name               = "truck-sim"
  storage_account_id = azurerm_storage_account.data.id
  quota              = 1
}

# azurerm cannot choose the environment mode and Azure now defaults to "Express", which cannot mount the Azure Files
# share, so this one resource is created through azapi as a workload-profiles environment. Only the pay-per-use
# Consumption profile is used: there is no fixed fee.
resource "azapi_resource" "trucks_env" {
  type      = "Microsoft.App/managedEnvironments@2025-10-02-preview"
  name      = "cae-${local.name}-wp"
  parent_id = azurerm_resource_group.rg.id
  location  = azurerm_resource_group.rg.location
  tags      = local.tags
  body = {
    properties = {
      environmentMode  = "WorkloadProfiles"
      workloadProfiles = [{ name = "Consumption", workloadProfileType = "Consumption" }]
      appLogsConfiguration = {
        destination = "log-analytics"
        logAnalyticsConfiguration = {
          customerId = azurerm_log_analytics_workspace.logs.workspace_id
          sharedKey  = azurerm_log_analytics_workspace.logs.primary_shared_key
        }
      }
    }
  }
  response_export_values    = ["properties.environmentMode"]
  schema_validation_enabled = false # environmentMode is newer than the provider's embedded API schema
}

resource "azurerm_container_app_environment_storage" "truck_sim" {
  name                         = "truck-sim"
  container_app_environment_id = azapi_resource.trucks_env.id
  account_name                 = azurerm_storage_account.data.name
  share_name                   = azurerm_storage_share.truck_sim.name
  access_key                   = azurerm_storage_account.data.primary_access_key
  access_mode                  = "ReadOnly"
}

resource "azurerm_container_app_job" "trucks" {
  name                         = "job-trucks-${var.env}-${var.name_suffix}"
  resource_group_name          = azurerm_resource_group.rg.name
  location                     = azurerm_resource_group.rg.location
  container_app_environment_id = azapi_resource.trucks_env.id
  replica_timeout_in_seconds   = var.truck_run_minutes * 60 + 600 # safety stop if the run does not end by itself
  replica_retry_limit          = 0
  workload_profile_name        = "Consumption"
  tags                         = local.tags

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "trucks"
      image   = "mcr.microsoft.com/azurelinux/base/python:3.12"
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["sh", "-c", "pip3 install --quiet --no-cache-dir -r /sim/requirements.txt && cd /sim && exec python3 -m greenops_sim.runner"]

      env {
        name  = "IOTHUB_HOSTNAME"
        value = azurerm_iothub.hub.hostname
      }
      env {
        name  = "FAULTS_URL"
        value = "https://${azurerm_function_app_flex_consumption.func.default_hostname}/api/sim/trucks"
      }
      env {
        name  = "RUN_FOR_S"
        value = tostring(var.truck_run_minutes * 60)
      }
      env {
        name  = "INTERVAL_S"
        value = "10"
      }
      env {
        name  = "JOURNEY_S"
        value = "1800"
      }
      env {
        name  = "CERT_DIR"
        value = "/sim/certs"
      }
      env {
        name  = "CONTRACTS_DIR"
        value = "/sim/contracts"
      }
      env {
        name  = "PYTHONDONTWRITEBYTECODE"
        value = "1"
      }

      volume_mounts {
        name = "truck-sim"
        path = "/sim"
      }
    }

    volume {
      name         = "truck-sim"
      storage_name = azurerm_container_app_environment_storage.truck_sim.name
      storage_type = "AzureFile"
    }
  }
}
