terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    azapi   = { source = "Azure/azapi", version = "~> 2.0" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # Remote state (Part 1, Table 6): one versioned copy in Azure with locking, created by scripts/bootstrap_tfstate.sh.
  # Sign-in only (no storage keys); the blob lease stops two people applying at once.
  backend "azurerm" {
    resource_group_name  = "rg-greenops-tfstate"
    storage_account_name = "stgreenopsg3tfstate"
    container_name       = "tfstate"
    key                  = "greenops-demo-g3.tfstate"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

provider "azapi" {
  subscription_id = var.subscription_id
}
