import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import os
import sys
import time

# =========================================================
# 🔐 SERVICE NOW LOGIN DETAILS
# =========================================================

INSTANCE_URL = "https://dev219690.service-now.com"
USERNAME = "admin"
PASSWORD = "Rn^=7gPEQb0o"

# =========================================================
# 📄 XML FILE PATH
# =========================================================

XML_PATH = "terraform_vars.xml"

# =========================================================
# 📋 CATALOG ITEM CONFIGURATION
# =========================================================

CATALOG_ITEM_CONFIG = {
    "name": "Terraform VM Provisioning",
    "short_description": "Request a new virtual machine provisioned via Terraform",
    "description": "Submit a request to provision a new VM using Terraform automation",
    "category": "Hardware",
    "price": "0",
    "workflow": ""
}

# =========================================================


def validate_xml(xml_path):
    """Validate XML file exists and can be parsed"""
    if not os.path.isfile(xml_path):
        print(f"❌ XML file not found: {xml_path}")
        sys.exit(1)
    
    try:
        ET.parse(xml_path)
        print("✅ XML validation passed")
        return True
    except ET.ParseError as e:
        print(f"❌ XML is not valid: {e}")
        sys.exit(1)


def parse_xml_variables():
    """Parse terraform_vars.xml and extract variables for catalog"""
    print("📖 Reading terraform_vars.xml...")
    
    tree = ET.parse(XML_PATH)
    root = tree.getroot()
    
    variables = []
    order = 100
    
    # Parse Locals section
    locals_section = root.find('Locals')
    if locals_section is not None:
        for variable in locals_section.findall('Variable'):
            name_elem = variable.find('Name')
            value_elem = variable.find('Value')
            type_elem = variable.find('Type')
            
            if name_elem is not None and name_elem.text:
                var_config = {
                    "name": name_elem.text,
                    "question_text": name_elem.text.replace('_', ' ').title(),
                    "type": "8",  # Single Line Text
                    "mandatory": "false",
                    "order": str(order)
                }
                
                if value_elem is not None and value_elem.text:
                    var_config["default_value"] = value_elem.text
                
                variables.append(var_config)
                order += 100
                print(f"   ✅ Found local variable: {name_elem.text}")
    
    # Parse Provider settings
    provider_section = root.find('Provider')
    if provider_section is not None:
        for setting in provider_section.findall('Setting'):
            name_elem = setting.find('Name')
            value_elem = setting.find('Value')
            sensitive_elem = setting.find('Sensitive')
            
            if name_elem is not None and name_elem.text:
                # Skip sensitive fields
                is_sensitive = sensitive_elem is not None and sensitive_elem.text == "true"
                if is_sensitive:
                    print(f"   ⚠️  Skipping sensitive field: {name_elem.text}")
                    continue
                
                var_config = {
                    "name": f"provider_{name_elem.text}",
                    "question_text": f"Provider: {name_elem.text.replace('_', ' ').title()}",
                    "type": "8",  # Single Line Text
                    "mandatory": "false",
                    "order": str(order)
                }
                
                if value_elem is not None and value_elem.text:
                    var_config["default_value"] = value_elem.text
                
                variables.append(var_config)
                order += 100
                print(f"   ✅ Found provider setting: {name_elem.text}")
    
    print(f"📊 Total variables extracted: {len(variables)}")
    return variables


def create_update_set():
    """Create a new update set"""
    url = f"{INSTANCE_URL}/api/now/table/sys_update_set"

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    name = f"TerraformCatalog_{timestamp}"

    payload = {
        "name": name,
        "description": "Terraform VM Provisioning Catalog with XML Variables",
        "state": "in progress"
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-UserToken": "no-check"
    }

    resp = requests.post(
        url,
        json=payload,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        headers=headers,
        timeout=30
    )

    print(f"Create Update Set - Status: {resp.status_code}")
    if resp.status_code != 201:
        print(f"Response: {resp.text}")
    
    resp.raise_for_status()
    result = resp.json()["result"]

    print("✅ Update Set created")
    print(f"   sys_id: {result['sys_id']}")
    print(f"   name: {result['name']}")

    return result["sys_id"], result["name"]


def set_current_update_set(update_set_sys_id):
    """Set the current update set for the session"""
    url = f"{INSTANCE_URL}/api/now/table/sys_user_preference"

    payload = {
        "user": "",
        "name": "sys_update_set",
        "value": update_set_sys_id
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-UserToken": "no-check"
    }

    resp = requests.post(
        url,
        json=payload,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        headers=headers,
        timeout=30
    )

    if resp.status_code in [200, 201]:
        print("✅ Set as current update set")
    else:
        print(f"⚠️  Could not set current update set: {resp.status_code}")


def get_catalog_sys_id(catalog_name="Service Catalog"):
    """Get the sys_id of a catalog"""
    url = f"{INSTANCE_URL}/api/now/table/sc_catalog"

    params = {
        "sysparm_query": f"title={catalog_name}",
        "sysparm_limit": 1
    }

    headers = {
        "Accept": "application/json",
        "X-UserToken": "no-check"
    }

    resp = requests.get(
        url,
        params=params,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        headers=headers,
        timeout=30
    )

    resp.raise_for_status()
    result = resp.json()["result"]

    if not result:
        print(f"⚠️  Catalog '{catalog_name}' not found, using first available")
        return get_first_catalog()
    
    return result[0]["sys_id"]


def get_first_catalog():
    """Get the first available catalog"""
    url = f"{INSTANCE_URL}/api/now/table/sc_catalog"

    params = {"sysparm_limit": 1}

    headers = {
        "Accept": "application/json",
        "X-UserToken": "no-check"
    }

    resp = requests.get(
        url,
        params=params,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        headers=headers,
        timeout=30
    )

    resp.raise_for_status()
    result = resp.json()["result"]

    if not result:
        raise RuntimeError("No catalogs found in instance")
    
    return result[0]["sys_id"]


def get_category_sys_id(category_name):
    """Get the sys_id of a category"""
    url = f"{INSTANCE_URL}/api/now/table/sc_category"

    params = {
        "sysparm_query": f"title={category_name}",
        "sysparm_limit": 1
    }

    headers = {
        "Accept": "application/json",
        "X-UserToken": "no-check"
    }

    resp = requests.get(
        url,
        params=params,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        headers=headers,
        timeout=30
    )

    resp.raise_for_status()
    result = resp.json()["result"]

    if not result:
        print(f"⚠️  Category '{category_name}' not found, will create without category")
        return None
    
    return result[0]["sys_id"]


def create_catalog_item(update_set_sys_id):
    """Create a catalog item"""
    print("📋 Creating Service Catalog Item...")

    url = f"{INSTANCE_URL}/api/now/table/sc_cat_item"

    catalog_sys_id = get_catalog_sys_id()
    category_sys_id = get_category_sys_id(CATALOG_ITEM_CONFIG["category"])

    payload = {
        "name": CATALOG_ITEM_CONFIG["name"],
        "short_description": CATALOG_ITEM_CONFIG["short_description"],
        "description": CATALOG_ITEM_CONFIG["description"],
        "sc_catalogs": catalog_sys_id,
        "price": CATALOG_ITEM_CONFIG["price"],
        "active": "true",
        "sys_update_set": update_set_sys_id
    }

    if category_sys_id:
        payload["category"] = category_sys_id

    if CATALOG_ITEM_CONFIG.get("workflow"):
        payload["workflow"] = CATALOG_ITEM_CONFIG["workflow"]

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-UserToken": "no-check"
    }

    resp = requests.post(
        url,
        json=payload,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        headers=headers,
        timeout=30
    )

    print(f"Create Catalog Item - Status: {resp.status_code}")
    if resp.status_code not in [200, 201]:
        print(f"Response: {resp.text}")

    resp.raise_for_status()
    result = resp.json()["result"]

    print("✅ Catalog Item created")
    print(f"   sys_id: {result['sys_id']}")
    print(f"   name: {result['name']}")

    return result["sys_id"]


def add_catalog_variables(catalog_item_sys_id, update_set_sys_id, variables):
    """Add variables to the catalog item from XML"""
    print("📝 Adding catalog variables from XML...")

    url = f"{INSTANCE_URL}/api/now/table/item_option_new"
    created_vars = []

    for var in variables:
        payload = {
            "cat_item": catalog_item_sys_id,
            "name": var["name"],
            "question_text": var["question_text"],
            "type": var["type"],
            "mandatory": var["mandatory"],
            "order": var["order"],
            "active": "true",
            "sys_update_set": update_set_sys_id
        }

        if "default_value" in var:
            payload["default_value"] = var["default_value"]

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-UserToken": "no-check"
        }

        resp = requests.post(
            url,
            json=payload,
            auth=HTTPBasicAuth(USERNAME, PASSWORD),
            headers=headers,
            timeout=30
        )

        resp.raise_for_status()
        result = resp.json()["result"]
        created_vars.append(result["sys_id"])
        print(f"   ✅ Created variable: {var['question_text']}")

    return created_vars


def attach_xml(update_set_sys_id):
    """Attach XML file to update set for reference"""
    print("📎 Attaching terraform_vars.xml to Update Set...")

    url = (
        f"{INSTANCE_URL}/api/now/attachment/file"
        f"?table_name=sys_update_set"
        f"&table_sys_id={update_set_sys_id}"
        f"&file_name={os.path.basename(XML_PATH)}"
    )

    with open(XML_PATH, "rb") as f:
        files = {
            "file": (os.path.basename(XML_PATH), f, "application/xml")
        }

        headers = {
            "Accept": "application/json"
        }

        resp = requests.post(
            url,
            auth=HTTPBasicAuth(USERNAME, PASSWORD),
            files=files,
            headers=headers,
            timeout=60
        )

    resp.raise_for_status()
    result = resp.json()["result"]

    print("✅ XML attached successfully")
    print(f"   attachment sys_id: {result['sys_id']}")

    return result["sys_id"]


def export_update_set(update_set_sys_id, update_set_name):
    """Export the update set as XML file"""
    print("📦 Exporting Update Set as XML...")
    
    url = f"{INSTANCE_URL}/sys_remote_update_set.do"
    
    params = {
        "XML": "",
        "sysparm_sys_id": update_set_sys_id,
        "sysparm_action": "export"
    }
    
    resp = requests.get(
        url,
        params=params,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        timeout=60
    )
    
    resp.raise_for_status()
    
    # Save exported XML
    export_filename = f"{update_set_name}_export.xml"
    with open(export_filename, "wb") as f:
        f.write(resp.content)
    
    print(f"✅ Update Set exported to: {export_filename}")
    return export_filename


def mark_complete(update_set_sys_id):
    """Mark update set as complete"""
    print("✅ Marking Update Set as Complete...")

    url = f"{INSTANCE_URL}/api/now/table/sys_update_set/{update_set_sys_id}"

    payload = {"state": "complete"}

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-UserToken": "no-check"
    }

    resp = requests.patch(
        url,
        json=payload,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        headers=headers,
        timeout=30
    )

    resp.raise_for_status()
    print("✅ Update Set marked as complete")


def main():
    """Main execution flow"""
    print("=" * 60)
    print("🚀 TERRAFORM CATALOG CREATOR WITH XML EXPORT")
    print("=" * 60)

    # Validate XML
    validate_xml(XML_PATH)
    
    # Parse variables from XML
    variables = parse_xml_variables()
    
    if not variables:
        print("⚠️  No variables found in XML. Creating catalog with default fields...")
        variables = [
            {
                "name": "vm_name",
                "question_text": "Virtual Machine Name",
                "type": "8",
                "mandatory": "true",
                "order": "100"
            }
        ]

    print(f"\n🔗 Connecting to {INSTANCE_URL} as {USERNAME}...\n")

    # Create update set
    update_set_sys_id, update_set_name = create_update_set()
    
    # Set as current update set
    set_current_update_set(update_set_sys_id)
    time.sleep(2)
    
    # Attach XML to update set
    attach_xml(update_set_sys_id)
    time.sleep(2)
    
    # Create catalog item
    catalog_item_sys_id = create_catalog_item(update_set_sys_id)
    time.sleep(2)
    
    # Add variables from XML to catalog item
    add_catalog_variables(catalog_item_sys_id, upda te_set_sys_id, variables)
    time.sleep(2)
    
    # Mark update set as complete
    mark_complete(update_set_sys_id)
    time.sleep(2)
    
    # Export update set as XML
    export_filename = export_update_set(update_set_sys_id, update_set_name)

    # Success summary
    print("\n" + "=" * 60)
    print("🎉 CATALOG CREATED & UPDATE SET EXPORTED!")
    print("=" * 60)
    print(f"✅ Update Set: {update_set_name}")
    print(f"✅ Variables from XML: {len(variables)}")
    print(f"✅ Exported XML: {export_filename}")
    print(f"\n🔗 View Update Set:")
    print(f"   {INSTANCE_URL}/nav_to.do?uri=sys_update_set.do?sys_id={update_set_sys_id}")
    print(f"\n📋 View Catalog Item:")
    print(f"   {INSTANCE_URL}/nav_to.do?uri=sc_cat_item.do?sys_id={catalog_item_sys_id}")
    print(f"\n🛒 Service Catalog Items List:")
    print(f"   {INSTANCE_URL}/sc_cat_item_list.do")
    print(f"\n📦 Export XML file saved locally: {export_filename}")
    print("=" * 60)


if __name__ == "__main__":
    main()