variable "subscription_id" {
  description = "Azure subscription that hosts GreenOps"
  type        = string
}
variable "location" {
  description = "Region – Canada Central keeps cargo data in Canada (Part 1, Section 5.6)"
  type        = string
  default     = "canadacentral"
}
variable "env" {
  description = "Environment name: dev (destroy when idle) or demo (24/7 recordings)"
  type        = string
  default     = "dev"
}
variable "iot_hub_sku" {
  description = "F1 = free, 8,000 messages/day (course use); B1 = USD 10/month (24/7 demo)"
  type        = string
  default     = "B1"
}
variable "alert_emails" {
  description = "Mailboxes that receive cold-chain alerts (Role 3 owner + Role 5)"
  type        = list(string)
  validation {
    condition     = length(var.alert_emails) > 0
    error_message = "Give at least one alert recipient."
  }
}
variable "budget_contact_emails" {
  description = "People who receive the CAD 2 and CAD 10 budget alerts (NFR-07)"
  type        = list(string)
}
variable "name_suffix" {
  description = "Short suffix that keeps the global names (IoT Hub, Cosmos DB, storage, Function app) unique"
  type        = string
  default     = "g3"
}
variable "cosmos_location" {
  description = "Cosmos DB region – Canada Central has refused new accounts at busy times; East US 2 is the fallback"
  type        = string
  default     = "canadacentral"
}
variable "email_data_location" {
  description = "Where Azure Communication Services keeps email data"
  type        = string
  default     = "Canada"
}
variable "rg_tags" {
  description = "Extra resource-group tags required by the subscription's policy (e.g. the college lab policy)"
  type        = map(string)
  default     = {}
}
variable "cosmos_serverless" {
  description = "true = serverless Cosmos DB (pay per request) instead of the free tier"
  type        = bool
  default     = false
}

variable "operator_emails" {
  description = "Microsoft account email -> display name of the people who may acknowledge alerts and set demo faults. Everyone else who signs in can only view."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for email, name in var.operator_emails : can(regex("^[^@ ]+@[^@ ]+$", email)) && length(trimspace(name)) > 0])
    error_message = "Map each operator's email address to a nonempty name."
  }
}
variable "sms_phones" {
  description = "Label -> Canadian or US mobile number (10 digits) that receives cargo-emergency texts. Empty = SMS off. Keep it in azure.auto.tfvars only."
  type        = map(string)
  sensitive   = true
  default     = {}
  validation {
    condition     = alltrue([for n in values(var.sms_phones) : can(regex("^[0-9]{10}$", n))])
    error_message = "Use 10 digits without spaces, for example 6135550123."
  }
}
variable "delivery_callback_token" {
  description = "Separate random service credential for Logic App email-result callbacks."
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.delivery_callback_token) >= 32
    error_message = "Use a random token of at least 32 characters."
  }
}
variable "iot_hub_monthly_usd" {
  description = "Configured base-cost assumption shown in the dashboard; not current pricing or a total bill forecast."
  type        = number
  default     = 10
}
variable "truck_run_minutes" {
  description = "How long one cloud truck run lasts. 6 trucks x 6 readings/min x 90 min = 3,240 messages, so two runs a day fit the IoT Hub F1 limit of 8,000."
  type        = number
  default     = 90
}
