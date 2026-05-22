import json
import os
import sys
import re

def is_valid_numeric_oid(oid: str) -> bool:
    if not oid:
        return False
    # Standard OID pattern: digits separated by dots
    pattern = r"^\.?([0-9]+\.)*[0-9]+$"
    return bool(re.match(pattern, oid))

def verify_file(file_path: str, feature: str) -> bool:
    print(f"Verifying {file_path}...")
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist.")
        return False
        
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error: Failed to parse JSON: {e}")
        return False
        
    if not isinstance(data, dict):
        print("Error: Root must be a JSON object.")
        return False
        
    if feature not in data:
        print(f"Error: Missing root key '{feature}'.")
        return False
        
    items = data[feature]
    if not isinstance(items, list):
        print(f"Error: '{feature}' must be a list.")
        return False
        
    # Check for duplicate OID + Vendor combinations and format
    seen_oids = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            print(f"Error: Item at index {idx} is not an object.")
            return False
            
        # Verify OIDs
        if feature == "memory":
            m_type = item.get("type", "free_total")
            if m_type == "percentage":
                oid = item.get("oid")
                if not oid:
                    print(f"Error: Memory percentage item at index {idx} must have 'oid'.")
                    return False
                if not is_valid_numeric_oid(oid):
                    print(f"Error: Invalid memory percentage OID at index {idx}.")
                    return False
                oid_key = oid
            else:
                free = item.get("oid_free")
                total = item.get("oid_total")
                if not free or not total:
                    print(f"Error: Memory item at index {idx} must have 'oid_free' and 'oid_total'.")
                    return False
                if not is_valid_numeric_oid(free) or not is_valid_numeric_oid(total):
                    print(f"Error: Invalid memory OIDs at index {idx}.")
                    return False
                oid_key = f"free:{free}|total:{total}"
        elif feature == "fans":
            status = item.get("oid_status")
            rpm = item.get("oid_rpm")
            if not status and not rpm:
                print(f"Error: Fan item at index {idx} must have at least 'oid_status' or 'oid_rpm'.")
                return False
            if status and not is_valid_numeric_oid(status):
                print(f"Error: Invalid fan status OID at index {idx}.")
                return False
            if rpm and not is_valid_numeric_oid(rpm):
                print(f"Error: Invalid fan RPM OID at index {idx}.")
                return False
            oid_key = f"status:{status}|rpm:{rpm}"
        elif feature == "psu":
            status = item.get("oid_status")
            if not status:
                print(f"Error: PSU item at index {idx} must have 'oid_status'.")
                return False
            if not is_valid_numeric_oid(status):
                print(f"Error: Invalid PSU status OID at index {idx}.")
                return False
            oid_key = f"status:{status}"
        elif feature == "poe":
            # POE has multiple optional fields, check what's present
            budget = item.get("oid_budget")
            used = item.get("oid_used")
            port_power = item.get("oid_port_power")
            if not budget and not used and not port_power:
                print(f"Error: PoE item at index {idx} must have at least one PoE OID.")
                return False
            if budget and not is_valid_numeric_oid(budget):
                print(f"Error: Invalid PoE budget OID at index {idx}.")
                return False
            if used and not is_valid_numeric_oid(used):
                print(f"Error: Invalid PoE used OID at index {idx}.")
                return False
            if port_power and not is_valid_numeric_oid(port_power):
                print(f"Error: Invalid PoE port power OID at index {idx}.")
                return False
            oid_key = f"budget:{budget}|used:{used}|port_power:{port_power}"
        elif feature == "device_info":
            mfg = item.get("oid_mfg")
            model = item.get("oid_model")
            firmware = item.get("oid_firmware")
            hostname = item.get("oid_hostname")
            uptime = item.get("oid_uptime")
            if not mfg and not model and not firmware and not hostname and not uptime:
                print(f"Error: Device Info item at index {idx} must have at least one diagnostic OID.")
                return False
            if mfg and not is_valid_numeric_oid(mfg):
                print(f"Error: Invalid Device Info manufacturer OID at index {idx}.")
                return False
            if model and not is_valid_numeric_oid(model):
                print(f"Error: Invalid Device Info model OID at index {idx}.")
                return False
            if firmware and not is_valid_numeric_oid(firmware):
                print(f"Error: Invalid Device Info firmware OID at index {idx}.")
                return False
            if hostname and not is_valid_numeric_oid(hostname):
                print(f"Error: Invalid Device Info hostname OID at index {idx}.")
                return False
            if uptime and not is_valid_numeric_oid(uptime):
                print(f"Error: Invalid Device Info uptime OID at index {idx}.")
                return False
            oid_key = f"mfg:{mfg}|model:{model}|firmware:{firmware}|hostname:{hostname}|uptime:{uptime}"
        else: # cpu, temperature, power
            oid = item.get("oid")
            if not oid:
                print(f"Error: Item at index {idx} must have 'oid'.")
                return False
            if not is_valid_numeric_oid(oid):
                print(f"Error: Invalid OID at index {idx}.")
                return False
            oid_key = oid
            
        # Check vendors list
        vendors = item.get("vendors")
        if not isinstance(vendors, list) or not vendors:
            print(f"Error: Item at index {idx} must have a non-empty list of 'vendors'.")
            return False
            
        # Check for duplicate vendors in the same item
        lower_vendors = [v.lower() for v in vendors]
        if len(lower_vendors) != len(set(lower_vendors)):
            print(f"Error: Duplicate vendors in item at index {idx}: {vendors}")
            return False
            
        # Check for duplicate OID + Vendor across different items
        if oid_key not in seen_oids:
            seen_oids[oid_key] = []
        for v in lower_vendors:
            if v in seen_oids[oid_key]:
                print(f"Error: Duplicate entry for OID '{oid_key}' and vendor '{v}' detected.")
                return False
            seen_oids[oid_key].append(v)
            
    print(f"Successfully verified {file_path}!")
    return True

def verify_rename_rules(file_path: str) -> bool:
    print(f"Verifying {file_path}...")
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist.")
        return False
        
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error: Failed to parse JSON: {e}")
        return False
        
    if not isinstance(data, dict):
        print("Error: Root must be a JSON object.")
        return False
        
    if "rename_rules" not in data:
        print("Error: Missing root key 'rename_rules'.")
        return False
        
    items = data["rename_rules"]
    if not isinstance(items, list):
        print("Error: 'rename_rules' must be a list.")
        return False
        
    seen_ids = set()
    seen_patterns = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            print(f"Error: Item at index {idx} is not an object.")
            return False
            
        r_id = item.get("id")
        pattern = item.get("pattern")
        replace = item.get("replace")
        
        if not r_id or not pattern or replace is None:
            print(f"Error: Rename rule at index {idx} must have 'id', 'pattern', and 'replace'.")
            return False
            
        if r_id in seen_ids:
            print(f"Error: Duplicate rename rule id '{r_id}' detected.")
            return False
        seen_ids.add(r_id)
        
        if pattern in seen_patterns:
            print(f"Error: Duplicate rename rule pattern '{pattern}' detected.")
            return False
        seen_patterns.add(pattern)
        
        # Verify it compiles as regex
        try:
            re.compile(pattern)
        except Exception as e:
            print(f"Error: Invalid regex pattern '{pattern}' in rule '{r_id}': {e}")
            return False
            
    print(f"Successfully verified {file_path}!")
    return True

def verify_interface_filters(file_path: str) -> bool:
    print(f"Verifying {file_path}...")
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist.")
        return False
        
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error: Failed to parse JSON: {e}")
        return False
        
    if not isinstance(data, dict):
        print("Error: Root must be a JSON object.")
        return False
        
    if "interface_filters" not in data:
        print("Error: Missing root key 'interface_filters'.")
        return False
        
    items = data["interface_filters"]
    if not isinstance(items, list):
        print("Error: 'interface_filters' must be a list.")
        return False
        
    seen_ids = set()
    seen_rule_types = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            print(f"Error: Item at index {idx} is not an object.")
            return False
            
        f_id = item.get("id")
        label = item.get("label")
        vendors = item.get("vendors")
        rule_type = item.get("rule_type")
        
        if not f_id or not label or not vendors or not rule_type:
            print(f"Error: Interface filter at index {idx} must have 'id', 'label', 'vendors', and 'rule_type'.")
            return False
            
        if not isinstance(vendors, list) or not vendors:
            print(f"Error: 'vendors' at index {idx} must be a non-empty list of strings.")
            return False
            
        if f_id in seen_ids:
            print(f"Error: Duplicate interface filter id '{f_id}' detected.")
            return False
        seen_ids.add(f_id)
        
        if rule_type in seen_rule_types:
            print(f"Error: Duplicate interface filter rule_type/conditions '{rule_type}' detected.")
            return False
        seen_rule_types.add(rule_type)
        
    print(f"Successfully verified {file_path}!")
    return True

def verify_interface_classification(file_path: str) -> bool:
    print(f"Verifying {file_path}...")
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist.")
        return False
        
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error: Failed to parse JSON: {e}")
        return False
        
    if not isinstance(data, dict):
        print("Error: Root must be a JSON object.")
        return False
        
    for key in ["virtual_tokens", "physical_tokens"]:
        if key not in data:
            print(f"Error: Missing key '{key}' in interface classification database.")
            return False
            
        tokens = data[key]
        if not isinstance(tokens, list):
            print(f"Error: '{key}' must be a list of strings.")
            return False
            
        seen = set()
        for idx, token in enumerate(tokens):
            if not isinstance(token, str) or not token.strip():
                print(f"Error: Token at index {idx} in '{key}' must be a non-empty string.")
                return False
                
            if token in seen:
                print(f"Error: Duplicate token '{token}' in '{key}' detected.")
                return False
            seen.add(token)
            
    print(f"Successfully verified {file_path}!")
    return True

def main():
    db_dir = "custom_components/snmp_switch_manager/database"
    features = ["cpu", "memory", "fans", "psu", "temperature", "power", "poe", "device_info"]
    
    success = True
    for feature in features:
        file_path = os.path.join(db_dir, f"{feature}.json")
        if not verify_file(file_path, feature):
            success = False
            
    # Verify modular JSON rules
    if not verify_rename_rules(os.path.join(db_dir, "rename_rules.json")):
        success = False
    if not verify_interface_filters(os.path.join(db_dir, "interface_filters.json")):
        success = False
    if not verify_interface_classification(os.path.join(db_dir, "interface_classification.json")):
        success = False
            
    if not success:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
