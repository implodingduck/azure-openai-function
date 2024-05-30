terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "=3.77.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "=3.1.0"
    }
  }
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

locals {
  func_name = "funcuai${random_string.unique.result}"
  loc_for_naming = "eastus"
  tags = {
    "managed_by" = "terraform"
    "repo"       = "azure-openai-function"
  }
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.func_name}-${local.loc_for_naming}"
  location = local.loc_for_naming
}

resource "random_string" "unique" {
  length  = 8
  special = false
  upper   = false
}


data "azurerm_client_config" "current" {}

data "azurerm_log_analytics_workspace" "default" {
  name                = "DefaultWorkspace-${data.azurerm_client_config.current.subscription_id}-EUS"
  resource_group_name = "DefaultResourceGroup-EUS"
} 

resource "azurerm_service_plan" "asp" {
  name                = "asp-${local.func_name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "Y1"
}

resource "azurerm_application_insights" "app" {
  name                = "${local.func_name}-insights"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  application_type    = "other"
  workspace_id        = data.azurerm_log_analytics_workspace.default.id
}

resource "azurerm_storage_account" "sa" {
  name                            = "sa${local.func_name}"
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = azurerm_resource_group.rg.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = false
  tags = local.tags
}

resource "azurerm_linux_function_app" "func" {
  name                = local.func_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  storage_account_name       = azurerm_storage_account.sa.name
  storage_account_access_key = azurerm_storage_account.sa.primary_access_key
  service_plan_id            = azurerm_service_plan.asp.id

  functions_extension_version = "~4"
  site_config {
    application_insights_key = azurerm_application_insights.app.instrumentation_key
    application_insights_connection_string = azurerm_application_insights.app.connection_string
    application_stack {
      python_version = "3.11"
    }
  }
  app_settings = {
    "SCM_DO_BUILD_DURING_DEPLOYMENT"             = "1"
    "API_BASE"                                   = var.openai-base
    "ENGINE"                                     = var.openai-engine
    "APIM_KEY"                                   = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.apim.versionless_id})"
    "PYTHON_ISOLATE_WORKER_DEPENDENCIES"         = "1"
    "PYTHON_ENABLE_INIT_INDEXING"                = "1"
    "ApplicationInsightsAgent_EXTENSION_VERSION" = "~3"
    "OTEL_SERVICE_NAME"                          = local.func_name
    
  }
  identity {
    type         = "SystemAssigned"
  }
  lifecycle {
    ignore_changes = [ tags ]
  }
}

resource "local_file" "localsettings" {
    content     = <<-EOT
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": ""
  }
}
EOT
    filename = "../func/local.settings.json"
}


resource "null_resource" "publish_func" {
  depends_on = [
    local_file.localsettings
  ]
  triggers = {
    index = "${timestamp()}"
  }
  provisioner "local-exec" {
    command = "cd ../func && func azure functionapp publish ${azurerm_linux_function_app.func.name}"
  }
}

data "azurerm_cognitive_account" "this" {
  name                = var.openai-account
  resource_group_name = var.openai-rg
}

resource "azurerm_role_assignment" "openai" {
  scope                = data.azurerm_cognitive_account.this.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}

resource "azurerm_role_assignment" "kv" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}

resource "azurerm_role_assignment" "kvtf" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}


resource "azurerm_key_vault" "this" {
  name                      = "kv-${local.func_name}"
  resource_group_name       = azurerm_resource_group.rg.name
  location                  = azurerm_resource_group.rg.location
  sku_name                  = "standard"
  tenant_id                 = data.azurerm_client_config.current.tenant_id
  enable_rbac_authorization = true

  tags = local.tags
}


resource "azurerm_key_vault_secret" "apim" {
  depends_on = [ azurerm_role_assignment.kvtf ]
  name         = "apimkey"
  value        = var.apim-key
  key_vault_id = azurerm_key_vault.this.id
} 