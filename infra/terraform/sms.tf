# ---- SMS alerts (F13, Role 3 – Shi Wang): Azure Monitor sends the text messages, so no phone number has to be bought.
# The Functions app calls this small workflow once per cargo emergency; the metric rule below notices that the workflow started and
# texts the action group. Without phone numbers (the default) nothing here is created and the SMS channel stays off.
resource "azurerm_logic_app_workflow" "sms" {
  count               = local.sms_enabled ? 1 : 0
  name                = "logic-${local.name}-cargo-emergency"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  tags                = local.tags
}

resource "azurerm_logic_app_trigger_http_request" "sms" {
  count        = local.sms_enabled ? 1 : 0
  name         = "cargo-emergency"
  logic_app_id = azurerm_logic_app_workflow.sms[0].id
  schema = jsonencode({ type = "object", required = ["alert_id", "truck_id", "type", "text"], properties = {
    alert_id = { type = "string" }, truck_id = { type = "string" }, type = { type = "string" }, text = { type = "string" }
  } })
}

# Keeps the text of each request in the workflow's run history, which is the audit trail of what was requested and when.
resource "azurerm_logic_app_action_custom" "sms_record" {
  count        = local.sms_enabled ? 1 : 0
  name         = "record-request"
  logic_app_id = azurerm_logic_app_workflow.sms[0].id
  body         = jsonencode({ type = "Compose", runAfter = {}, inputs = "@triggerBody()" })
}

resource "azurerm_monitor_action_group" "on_call" {
  count               = local.sms_enabled ? 1 : 0
  name                = "ag-${local.name}-on-call"
  resource_group_name = azurerm_resource_group.rg.name
  short_name          = "GreenOps"
  tags                = local.tags
  dynamic "sms_receiver" {
    for_each = nonsensitive(toset(keys(var.sms_phones))) # the labels are not secret, the numbers are
    content {
      name         = sms_receiver.value
      country_code = "1"
      phone_number = var.sms_phones[sms_receiver.value]
    }
  }
}

resource "azurerm_monitor_metric_alert" "cargo_emergency" {
  count               = local.sms_enabled ? 1 : 0
  name                = "Cargo emergency - open the GreenOps dashboard"
  resource_group_name = azurerm_resource_group.rg.name
  scopes              = [azurerm_logic_app_workflow.sms[0].id]
  description         = "A truck's cargo left its safe temperature or humidity range."
  severity            = 1
  frequency           = "PT1M"
  window_size         = "PT1M"
  auto_mitigate       = false # no second text when the minute is over
  tags                = local.tags
  criteria {
    metric_namespace = "Microsoft.Logic/workflows"
    metric_name      = "RunsStarted"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0
  }
  action { action_group_id = azurerm_monitor_action_group.on_call[0].id }
}
