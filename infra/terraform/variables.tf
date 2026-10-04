variable "subscription_id" {
  description = "Azure subscription that hosts GreenOps (the new, non-student account)"
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
  default     = "F1"
}
variable "alert_email" {
  description = "Mailbox that receives cold-chain alerts"
  type        = string
}
variable "budget_contact_emails" {
  description = "People who receive the USD 1 and USD 5 budget alerts (NFR-07)"
  type        = list(string)
}
