output "iot_hub_hostname" { value = azurerm_iothub.hub.hostname }
output "dashboard_url" { value = "https://${azurerm_static_web_app.dashboard.default_host_name}" }
output "function_app" { value = azurerm_function_app_flex_consumption.func.name }
