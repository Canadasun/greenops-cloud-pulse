output "resource_group" { value = azurerm_resource_group.rg.name }
output "iot_hub_name" { value = azurerm_iothub.hub.name }
output "iot_hub_hostname" { value = azurerm_iothub.hub.hostname }
output "dashboard_url" { value = "https://${azurerm_static_web_app.dashboard.default_host_name}" }
output "function_app" { value = azurerm_function_app_flex_consumption.func.name }
output "function_url" { value = "https://${azurerm_function_app_flex_consumption.func.default_hostname}" }
output "cosmos_account" { value = azurerm_cosmosdb_account.db.name }
output "storage_account" { value = azurerm_storage_account.data.name }
output "logic_app" { value = azurerm_logic_app_workflow.alerts.name }
output "email_sender" { value = "DoNotReply@${azurerm_email_communication_service_domain.managed.from_sender_domain}" }
output "app_insights" { value = azurerm_application_insights.appi.name }
output "swa_deployment_token" {
  value     = azurerm_static_web_app.dashboard.api_key
  sensitive = true
}
output "truck_job" { value = azurerm_container_app_job.trucks.name }
