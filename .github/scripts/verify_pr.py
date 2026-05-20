#!/usr/bin/env python3
import os
import json
import difflib
import sys

# Define base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_DIR = os.path.join(BASE_DIR, "custom_components", "snmp_switch_manager", "database")
VENDORS_FILE = os.path.join(DB_DIR, "vendors.json")

def extract_enterprise_info(oid):
    """Extract enterprise number and sysObjectID prefix from an OID."""
    if not oid:
        return "", ""
    parts = oid.strip().lstrip(".").split(".")
    # A standard enterprise OID is .1.3.6.1.4.1.XXXXX... (at least 7 elements)
    if len(parts) >= 7 and parts[0] == "1" and parts[1] == "3" and parts[2] == "6" and parts[3] == "1" and parts[4] == "4" and parts[5] == "1":
        ent_num = parts[6]
        return ent_num, f"1.3.6.1.4.1.{ent_num}"
    return "", ""

def load_vendors():
    """Load existing vendors list."""
    if not os.path.exists(VENDORS_FILE):
        return {"vendors": []}
    try:
        with open(VENDORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading vendors.json: {e}")
        return {"vendors": []}

def save_vendors(vendors_data):
    """Save vendors list sorted alphabetically by name."""
    vendors_data["vendors"] = sorted(vendors_data["vendors"], key=lambda x: x["name"].lower())
    with open(VENDORS_FILE, "w", encoding="utf-8") as f:
        json.dump(vendors_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

def get_existing_vendor_names(vendors_data):
    """Get list of active vendor names from vendors.json."""
    return [v["name"] for v in vendors_data.get("vendors", [])]

def get_casing_and_spelling_match(vendor_name, existing_names):
    """Check for case-insensitive match or fuzzy spelling match."""
    vendor_lower = vendor_name.lower().strip()
    
    # 1. Exact case-insensitive match check
    for name in existing_names:
        if name.lower().strip() == vendor_lower:
            return name
            
    # 2. Fuzzy spelling match check (cutoff=0.75 for tight matching)
    close_matches = difflib.get_close_matches(vendor_name, existing_names, n=1, cutoff=0.75)
    if close_matches:
        return close_matches[0]
        
    return None

def normalize_oid(o):
    """Normalize OID by stripping dots."""
    if not o:
        return ""
    o_str = str(o).strip()
    if o_str.startswith("."):
        return o_str[1:]
    return o_str

def main():
    print("🔍 Starting SNMP Switch Manager PR Verification Script...")
    
    if not os.path.exists(DB_DIR):
        print(f"❌ Database directory does not exist: {DB_DIR}")
        sys.exit(1)
        
    vendors_data = load_vendors()
    existing_vendor_names = get_existing_vendor_names(vendors_data)
    
    any_files_modified = False
    
    # Step 1: Scan and validate all feature database files
    for filename in os.listdir(DB_DIR):
        if not filename.endswith(".json") or filename == "vendors.json":
            continue
            
        file_path = os.path.join(DB_DIR, filename)
        feature = filename[:-5]
        print(f"📂 Verifying {filename}...")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.strip():
                    db = {feature: []}
                else:
                    db = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON format in {filename}: {e}")
            sys.exit(1)
            
        if not isinstance(db, dict) or feature not in db:
            print(f"❌ Schema error in {filename}: Root must be a dictionary with key '{feature}'")
            sys.exit(1)
            
        items = db[feature]
        if not isinstance(items, list):
            print(f"❌ Schema error in {filename}: '{feature}' value must be a list")
            sys.exit(1)
            
        normalized_items = []
        file_modified = False
        
        # Step 2: Iterate through entries and apply self-healing checks
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                print(f"❌ Schema error in {filename} at index {index}: Item must be a dictionary")
                sys.exit(1)
                
            # Ensure vendors list exists
            vendors = item.get("vendors")
            if not vendors or not isinstance(vendors, list):
                print(f"❌ Schema error in {filename} at index {index}: 'vendors' must be a non-empty list")
                sys.exit(1)
                
            # Normalize and correct spelling/casing for vendors in this item
            new_vendors = []
            for vendor in vendors:
                corrected = get_casing_and_spelling_match(vendor, existing_vendor_names)
                if corrected and corrected != vendor:
                    print(f"✨ Auto-corrected vendor casing/spelling in {filename}: '{vendor}' -> '{corrected}'")
                    new_vendors.append(corrected)
                    file_modified = True
                else:
                    new_vendors.append(vendor.strip())
            item["vendors"] = new_vendors
            
            # Normalize OID keys
            for key in item.keys():
                if key.startswith("oid") and isinstance(item[key], str):
                    norm = normalize_oid(item[key])
                    if norm != item[key]:
                        item[key] = norm
                        file_modified = True
                        
            # Check if this OID structure is a duplicate of a previously seen item in this run
            duplicate_found = False
            for prev in normalized_items:
                match = False
                if feature in ["cpu", "temperature", "power"]:
                    match = prev.get("oid") == item.get("oid")
                elif feature == "memory":
                    if prev.get("type", "free_total") == "percentage":
                        match = prev.get("oid") == item.get("oid")
                    else:
                        match = (prev.get("oid_free") == item.get("oid_free") and 
                                 prev.get("oid_total") == item.get("oid_total"))
                elif feature == "fans":
                    match = (prev.get("oid_rpm") == item.get("oid_rpm") or 
                             prev.get("oid_status") == item.get("oid_status"))
                elif feature == "psu":
                    match = prev.get("oid_status") == item.get("oid_status")
                elif feature == "poe":
                    match = (prev.get("oid_budget") == item.get("oid_budget") or 
                             prev.get("oid_used") == item.get("oid_used") or 
                             prev.get("oid_port_power") == item.get("oid_port_power"))
                elif feature == "device_info":
                    match = (prev.get("oid_mfg") == item.get("oid_mfg") or
                             prev.get("oid_model") == item.get("oid_model") or
                             prev.get("oid_firmware") == item.get("oid_firmware") or
                             prev.get("oid_hostname") == item.get("oid_hostname") or
                             prev.get("oid_uptime") == item.get("oid_uptime"))
                             
                if match:
                    # Duplicate OID detected! Let's combine vendor lists cleanly
                    duplicate_found = True
                    for v in item["vendors"]:
                        if v not in prev["vendors"]:
                            prev["vendors"].append(v)
                            file_modified = True
                            print(f"✨ Consolidated vendor '{v}' into existing OID entry in {filename}")
                    break
                    
            if not duplicate_found:
                normalized_items.append(item)
                
        # Write back changes to the file if modified
        if len(items) != len(normalized_items) or file_modified:
            db[feature] = normalized_items
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"💾 Saved corrected/normalized data to {filename}")
            any_files_modified = True

    # Step 3: Self-Healing vendors.json compilation
    print("🛠️ Auto-extracting and compiling vendors.json...")
    all_unique_vendors = set()
    vendor_to_oids = {}
    
    # Scan all database files to extract unique vendors and representative OIDs
    for filename in os.listdir(DB_DIR):
        if not filename.endswith(".json") or filename == "vendors.json":
            continue
            
        file_path = os.path.join(DB_DIR, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                db = json.load(f)
                feature = filename[:-5]
                for item in db.get(feature, []):
                    for v in item.get("vendors", []):
                        all_unique_vendors.add(v)
                        # Store representative OID to extract enterprise numbers if needed
                        if v not in vendor_to_oids:
                            for key in item.keys():
                                if key.startswith("oid") and item[key] and isinstance(item[key], str):
                                    vendor_to_oids[v] = item[key]
                                    break
        except Exception:
            pass
            
    # Check if any vendors are missing from vendors.json
    vendors_modified = False
    for v in all_unique_vendors:
        has_vendor = False
        for existing in vendors_data["vendors"]:
            if existing["name"].lower() == v.lower():
                has_vendor = True
                break
                
        if not has_vendor:
            # Found a new vendor! Automatically compile its enterprise info
            print(f"✨ Auto-registering brand-new vendor in vendors.json: '{v}'")
            rep_oid = vendor_to_oids.get(v, "")
            ent_num, prefix = extract_enterprise_info(rep_oid)
            
            vendors_data["vendors"].append({
                "name": v,
                "enterprise_number": ent_num,
                "sys_object_id_prefix": prefix
            })
            vendors_modified = True
            
    if vendors_modified:
        save_vendors(vendors_data)
        print("💾 Auto-updated and compiled database/vendors.json successfully!")
        any_files_modified = True
    else:
        print("✅ vendors.json is already fully synchronized and up-to-date!")
        
    print("🎉 PR Verification and Self-Healing completed successfully!")

if __name__ == "__main__":
    main()
