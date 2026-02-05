terraform {
  required_version = ">= 1.5.0"
 
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.0.0, < 5.0.0"
    }
  }
}
 
# --------------------------- Provider ---------------------------
provider "azurerm" {
  features {}
 
  tenant_id       = "147e32ab-2b66-4f09-b4d8-f98e9d3349ae"
  subscription_id = "07003dc0-1924-41eb-b7fe-d8b9353a4484"
  client_id       = "6c75af60-ac4e-4948-8ea1-0e7ecfaa3870"
  client_secret   = "U6L8Q~66uvQs4DwFsy4KD-h7HYxHQRQ4ucjVvaiq"
}
 
# --------------------------- Inputs ---------------------------
locals {
  resource_group_name = "EPH-Training-RG"
  vm_name             = "vaishnavi-vm"
  vm_size             = "Standard_B2s"
  admin_username      = "azureadmin"
  admin_password      = "YourSecurePassw0rd!@" # Must meet Azure complexity rules
}
 
# --------------------------- Resource Group Lookup ---------------------------
data "azurerm_resource_group" "rg" {
  name = local.resource_group_name
}
 
# --------------------------- Networking ---------------------------
resource "azurerm_virtual_network" "vnet" {
  name                = "vaishnavi-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
}
 
resource "azurerm_subnet" "subnet" {
  name                 = "vaishnavi-subnet"
  resource_group_name  = data.azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}
 
resource "azurerm_public_ip" "public_ip" {
  name                = "vaishnavi-publicip"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}
 
resource "azurerm_network_security_group" "nsg" {
  name                = "vaishnavi-nsg"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
 
  security_rule {
    name                       = "RDP"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}
 
resource "azurerm_network_interface" "nic" {
  name                = "vaishnavi-nic"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
 
  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.public_ip.id
  }
}
 
resource "azurerm_network_interface_security_group_association" "nsg_assoc" {
  network_interface_id      = azurerm_network_interface.nic.id
  network_security_group_id = azurerm_network_security_group.nsg.id
}
 
# --------------------------- Windows VM ---------------------------
resource "azurerm_windows_virtual_machine" "winvm" {
  name                = local.vm_name
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = data.azurerm_resource_group.rg.location
  size                = local.vm_size
  admin_username      = local.admin_username
  admin_password      = local.admin_password
  network_interface_ids = [azurerm_network_interface.nic.id]
 
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
 
  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2022-Datacenter"
    version   = "latest"
  }
 
  tags = {
    environment = "dev"
    owner       = "vaishnavi"
  }
}
 
# --------------------------- Outputs ---------------------------
output "windows_vm_name" {
  value = azurerm_windows_virtual_machine.winvm.name
}
 
output "windows_vm_private_ip" {
  value = azurerm_network_interface.nic.private_ip_address
}
 
output "windows_vm_public_ip" {
  value = azurerm_public_ip.public_ip.ip_address
}