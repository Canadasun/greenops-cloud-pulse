# GreenOps Cloud Pulse on Azure (Part 2, Figure 7). Owner: Marcelbriaud Wafotchoupe (Role 2), with each service's role owner.
locals {
  name = "greenops-${var.env}-${var.name_suffix}"
  tags = { project = "greenops-cloud-pulse", env = var.env, course = "CST8922" }
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.name}-cc"
  location = var.location
  # Azure tag names ignore case, so a policy tag (e.g. "Course") replaces the project tag of the same name
  tags = merge({ for k, v in local.tags : k => v if !contains([for t in keys(var.rg_tags) : lower(t)], lower(k)) }, var.rg_tags)
}

# ---- Ingestion (Role 2): IoT Hub with routing to the built-in endpoint (Alert Function) and the archive
resource "azurerm_iothub" "hub" {
  name                = "iot-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku {
    name     = var.iot_hub_sku
    capacity = 1
  }
  event_hub_partition_count = var.iot_hub_sku == "F1" ? 2 : 4 # the free tier allows exactly 2
  tags                      = local.tags
}

# ---- Storage (Role 4): Blob archive with a 30-day move to the Archive tier, plus storage for the Functions host
resource "azurerm_storage_account" "data" {
  name                     = substr(replace("st${local.name}data", "-", ""), 0, 24)
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.tags
}

resource "azurerm_storage_container" "archive" {
  name                  = "telemetry-archive"
  storage_account_id    = azurerm_storage_account.data.id
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "archive_tier" {
  storage_account_id = azurerm_storage_account.data.id
  rule {
    name    = "archive-after-30-days"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["telemetry-archive/${azurerm_iothub.hub.name}/telemetry/"]
    }
    actions {
      base_blob {
        tier_to_archive_after_days_since_modification_greater_than = 30
      }
    }
  }
}

resource "azurerm_iothub_endpoint_storage_container" "archive" {
  name                       = "archive"
  resource_group_name        = azurerm_resource_group.rg.name
  iothub_id                  = azurerm_iothub.hub.id
  connection_string          = azurerm_storage_account.data.primary_blob_connection_string
  container_name             = azurerm_storage_container.archive.name
  batch_frequency_in_seconds = 300
  encoding                   = "JSON"
  file_name_format           = "{iothub}/telemetry/{YYYY}/{MM}/{DD}/{HH}/{mm}-{partition}"
}

resource "azurerm_iothub_route" "to_alerts" {
  name                = "to-alert-function"
  resource_group_name = azurerm_resource_group.rg.name
  iothub_name         = azurerm_iothub.hub.name
  source              = "DeviceMessages"
  condition           = "true"
  endpoint_names      = ["events"]
  enabled             = true
}

resource "azurerm_iothub_route" "to_archive" {
  name                = "to-archive"
  resource_group_name = azurerm_resource_group.rg.name
  iothub_name         = azurerm_iothub.hub.name
  source              = "DeviceMessages"
  condition           = "true"
  endpoint_names      = [azurerm_iothub_endpoint_storage_container.archive.name]
  enabled             = true
}

# ---- Live data (Role 4): Cosmos DB for NoSQL, three containers (Part 2, Table 2)
# Free tier (1,000 RU/s shared) by default; serverless (pay per request) when the subscription's one free-tier slot is taken.
resource "azurerm_cosmosdb_account" "db" {
  name                = var.cosmos_location == var.location ? "cosmos-${local.name}" : "cosmos-${local.name}-${var.cosmos_location}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.cosmos_location
  offer_type          = "Standard"
  free_tier_enabled   = !var.cosmos_serverless
  dynamic "capabilities" {
    for_each = var.cosmos_serverless ? ["EnableServerless"] : []
    content { name = capabilities.value }
  }
  consistency_policy { consistency_level = "Session" }
  geo_location {
    location          = var.cosmos_location
    failover_priority = 0
  }
  tags = local.tags
}

resource "azurerm_cosmosdb_sql_database" "greenops" {
  name                = "greenops"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.db.name
  throughput          = var.cosmos_serverless ? null : 1000 # shared by all containers – the free-tier allowance
}

resource "azurerm_cosmosdb_sql_container" "containers" {
  for_each            = { telemetry = { pk = "/truck_id", ttl = 604800 }, alerts = { pk = "/truck_id", ttl = -1 }, reference = { pk = "/doc_type", ttl = -1 } }
  name                = each.key
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.db.name
  database_name       = azurerm_cosmosdb_sql_database.greenops.name
  partition_key_paths = [each.value.pk]
  default_ttl         = each.value.ttl
  indexing_policy {
    indexing_mode = "consistent"
    included_path { path = "/*" }
    excluded_path { path = "/\"_etag\"/?" }
    dynamic "composite_index" {
      for_each = each.key == "alerts" ? [1] : []
      content {
        index {
          path  = "/started_at"
          order = "descending"
        }
        index {
          path  = "/id"
          order = "descending"
        }
      }
    }
  }
}

# ---- Functions (Roles 3, 4, 5): Flex Consumption, Python 3.12, managed identity, Application Insights
resource "azurerm_log_analytics_workspace" "logs" {
  name                = "log-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  retention_in_days   = 30
  daily_quota_gb      = 0.5 # cost cap: logging pauses for the day instead of billing past the free allowance
  tags                = local.tags
}

resource "azurerm_application_insights" "appi" {
  name                = "appi-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  workspace_id        = azurerm_log_analytics_workspace.logs.id
  application_type    = "web"
  tags                = local.tags
}

resource "azurerm_storage_container" "deploy" {
  name                  = "function-releases"
  storage_account_id    = azurerm_storage_account.data.id
  container_access_type = "private"
}

resource "azurerm_service_plan" "flex" {
  name                = "asp-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "FC1"
  tags                = local.tags
}

resource "azurerm_function_app_flex_consumption" "func" {
  name                        = "func-${local.name}"
  resource_group_name         = azurerm_resource_group.rg.name
  location                    = azurerm_resource_group.rg.location
  service_plan_id             = azurerm_service_plan.flex.id
  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.data.primary_blob_endpoint}${azurerm_storage_container.deploy.name}"
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = azurerm_storage_account.data.primary_access_key
  runtime_name                = "python"
  runtime_version             = "3.12"
  maximum_instance_count      = 40
  instance_memory_in_mb       = 512
  identity { type = "SystemAssigned" }
  site_config {
    application_insights_connection_string = azurerm_application_insights.appi.connection_string
    cors {
      allowed_origins = ["https://${azurerm_static_web_app.dashboard.default_host_name}", "http://localhost:5173"]
    }
  }
  app_settings = {
    AzureWebJobsStorage     = azurerm_storage_account.data.primary_connection_string # timer + IoT Hub checkpoints
    TRIGGER_MODE            = "iothub"
    IOTHUB_EVENTS           = "Endpoint=${azurerm_iothub.hub.event_hub_events_endpoint};SharedAccessKeyName=iothubowner;SharedAccessKey=${azurerm_iothub.hub.shared_access_policy[0].primary_key};EntityPath=${azurerm_iothub.hub.event_hub_events_path}"
    IOTHUB_EVENTHUB_NAME    = azurerm_iothub.hub.event_hub_events_path
    COSMOS_ENDPOINT         = azurerm_cosmosdb_account.db.endpoint
    OPERATOR_TOKENS         = jsonencode(var.operator_tokens)
    DELIVERY_CALLBACK_TOKEN = var.delivery_callback_token
    IOT_HUB_SKU             = var.iot_hub_sku
    IOT_HUB_MONTHLY_USD     = tostring(var.iot_hub_monthly_usd)
    FLEET_WATCHER_SCHEDULE  = "0 */1 * * * *"
    LOGIC_APP_URL           = azurerm_logic_app_trigger_http_request.alert.callback_url
    ALERT_EMAIL_TO          = join(",", var.alert_emails)
  }
  tags = local.tags
}

# Functions read and write Cosmos DB with their managed identity – no database key in the app settings.
resource "azurerm_cosmosdb_sql_role_assignment" "func_data" {
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.db.name
  role_definition_id  = "${azurerm_cosmosdb_account.db.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002" # Built-in Data Contributor
  principal_id        = azurerm_function_app_flex_consumption.func.identity[0].principal_id
  scope               = azurerm_cosmosdb_account.db.id
}

# ---- Email (Role 3): Logic App (HTTP trigger) -> Azure Communication Services email from an Azure-managed domain
resource "azurerm_email_communication_service" "email" {
  name                = "ecs-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  data_location       = var.email_data_location
  tags                = local.tags
}

resource "azurerm_email_communication_service_domain" "managed" {
  name              = "AzureManagedDomain"
  email_service_id  = azurerm_email_communication_service.email.id
  domain_management = "AzureManaged"
}

resource "azurerm_communication_service" "acs" {
  name                = "acs-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  data_location       = var.email_data_location
  tags                = local.tags
}

resource "azurerm_communication_service_email_domain_association" "link" {
  communication_service_id = azurerm_communication_service.acs.id
  email_service_domain_id  = azurerm_email_communication_service_domain.managed.id
}

data "azurerm_managed_api" "acsemail" {
  name     = "acsemail"
  location = azurerm_resource_group.rg.location
}

resource "azurerm_api_connection" "acsemail" {
  name                = "acsemail"
  resource_group_name = azurerm_resource_group.rg.name
  managed_api_id      = data.azurerm_managed_api.acsemail.id
  display_name        = "GreenOps alert email"
  parameter_values    = { api_key = azurerm_communication_service.acs.primary_connection_string }
  lifecycle { ignore_changes = [parameter_values] } # Azure never returns the secret, so do not re-apply it every plan
  depends_on = [azurerm_communication_service_email_domain_association.link]
}

resource "azurerm_logic_app_workflow" "alerts" {
  name                = "logic-${local.name}-alerts"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  workflow_parameters = { "$connections" = jsonencode({ type = "Object", defaultValue = {} }) }
  parameters = { "$connections" = jsonencode({ acsemail = {
    connectionId = azurerm_api_connection.acsemail.id, connectionName = azurerm_api_connection.acsemail.name, id = data.azurerm_managed_api.acsemail.id
  } }) }
  tags = local.tags
}

resource "azurerm_logic_app_trigger_http_request" "alert" {
  name         = "alert-received"
  logic_app_id = azurerm_logic_app_workflow.alerts.id
  schema = jsonencode({ type = "object", properties = {
    to      = { type = "string" }, alert_id = { type = "string" }, truck_id = { type = "string" }, type = { type = "string" },
    details = { type = "string" }, started_at = { type = "string" }
  } })
}

resource "azurerm_logic_app_action_custom" "send_email" {
  depends_on   = [azurerm_logic_app_action_custom.claim_dispatch]
  name         = "send-alert-email"
  logic_app_id = azurerm_logic_app_workflow.alerts.id
  body = jsonencode({
    type     = "ApiConnection"
    runAfter = { "claim-email-dispatch" = ["Succeeded"] }
    inputs = {
      host    = { connection = { name = "@parameters('$connections')['acsemail']['connectionId']" } }
      method  = "post"
      path    = "/emails:sendGAVersion"
      queries = { "api-version" = "2023-03-31" }
      # No in-run retries: a throttled (429) send would be repeated at once. The Function backs off and gives up instead.
      retryPolicy = { type = "none" }
      body = {
        senderAddress = "DoNotReply@${azurerm_email_communication_service_domain.managed.from_sender_domain}"
        recipients    = { to = [for e in var.alert_emails : { address = e }] }
        importance    = "High"
        content = {
          subject = "GreenOps alert: @{triggerBody()?['type']} on @{triggerBody()?['truck_id']}"
          html    = "<h2>GreenOps Cloud Pulse alert</h2><p><b>Truck:</b> @{triggerBody()?['truck_id']}<br><b>Alert:</b> @{triggerBody()?['type']}<br><b>Details:</b> @{triggerBody()?['details']}<br><b>Started:</b> @{triggerBody()?['started_at']} (UTC)<br><b>Alert ID:</b> @{triggerBody()?['alert_id']}</p><p>Open the dashboard to acknowledge it.</p>"
        }
      }
    }
  })
}

# ---- Dashboard (Role 5): Static Web Apps, Free plan
resource "azurerm_static_web_app" "dashboard" {
  name                = "swa-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = "eastus2" # Static Web Apps is offered in a few regions; it only serves the static files
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = local.tags
}

# ---- Cost guardrails (Role 4, NFR-07): budget alerts at 1 and 5 in the billing currency (CAD on the student subscription)
resource "azurerm_consumption_budget_resource_group" "budget" {
  name              = "budget-${local.name}"
  resource_group_id = azurerm_resource_group.rg.id
  amount            = 5
  time_grain        = "Monthly"
  time_period { start_date = "2026-10-01T00:00:00Z" }
  notification {
    enabled        = true
    threshold      = 20 # 20 % of 5 = 1
    operator       = "GreaterThan"
    contact_emails = var.budget_contact_emails
  }
  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    contact_emails = var.budget_contact_emails
  }
}

# Report the email action outcome instead of interpreting the trigger's 202 as sent.
resource "azurerm_logic_app_action_custom" "delivery_result" {
  name         = "report-email-result"
  logic_app_id = azurerm_logic_app_workflow.alerts.id
  body = jsonencode({
    type     = "Http"
    runAfter = { "send-alert-email" = ["Succeeded", "Failed", "TimedOut"] }
    inputs = {
      method      = "POST"
      uri         = "https://${azurerm_function_app_flex_consumption.func.default_hostname}/api/alerts/@{triggerBody()?['alert_id']}/delivery"
      headers     = { Authorization = "Bearer ${var.delivery_callback_token}", "Content-Type" = "application/json" }
      body        = { status = "@if(equals(actions('send-alert-email').status, 'Succeeded'), 'sent', 'failed')", workflow_id = "@workflow().run.name" }
      retryPolicy = { type = "exponential", count = 8, interval = "PT10S" }
    }
    runtimeConfiguration = { secureData = { properties = ["inputs", "outputs"] } }
  })
  depends_on = [azurerm_logic_app_action_custom.send_email]
}

# A persisted claim prevents a repeated trigger request from starting another email send.
resource "azurerm_logic_app_action_custom" "claim_dispatch" {
  name         = "claim-email-dispatch"
  logic_app_id = azurerm_logic_app_workflow.alerts.id
  body = jsonencode({
    type     = "Http"
    runAfter = {}
    inputs = {
      method  = "POST"
      uri     = "https://${azurerm_function_app_flex_consumption.func.default_hostname}/api/alerts/@{triggerBody()?['alert_id']}/dispatch"
      headers = { Authorization = "Bearer ${var.delivery_callback_token}", "Content-Type" = "application/json" }
      body    = { workflow_id = "@workflow().run.name" }
    }
    runtimeConfiguration = { secureData = { properties = ["inputs", "outputs"] } }
  })
}
