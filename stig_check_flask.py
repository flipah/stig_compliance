# Import required libraries
from netmiko import ConnectHandler, NetmikoAuthenticationException, NetMikoTimeoutException
from paramiko.ssh_exception import SSHException
from flask import Flask, render_template, request
import logging
import json
import re

# Enable debugging logs for Netmiko
#logging.basicConfig(filename='netmiko_debug.log', level=logging.DEBUG)

# Initialize Flask application
app = Flask(__name__)

# --- Flask Routes ---

@app.route('/')
def index(): # This is the initial website that is called upon (The home page)
    """Render the initial HTML form for user input."""
    return render_template('index.html', name='SOCOM SPECTER')

@app.route('/submit', methods=['POST'])
def check_stigs(): # Combines all the funtions and sends out the results to the post check html
    """
    Main route to handle the STIG checking process.
    This function orchestrates getting user input, connecting to devices,
    running validation checks, and rendering the results.
    """
    # 1. Get form input
    ip_addrs, username, password, en_secret, rtr = get_form_input()

    # 2. Open all golden configuration files once
    bulk_show, gcr_file, gcs_file, rtr_golden_acls, sw_golden_acls, gint_file = open_golden_files()

    results_per_device = {}

    # 3. Loop through each IP address to connect and validate config
    if rtr is not None: # This is the NIPR RTR checks
        for device_ip in ip_addrs:
            # Connect to device and get running configs
            connection_result = connect_to_device(device_ip, username, password, en_secret, bulk_show)

            # If connection fails, store the error and move to the next device
            if "error" in connection_result:
                results_per_device[device_ip] = {"error": connection_result["error"]}
                continue

            running_config = connection_result["running_config"]
            running_acls = connection_result["running_acls"]

            # Validate STIG configuration against the golden config
            missing_commands_by_section = validate_rtr(running_config, gcr_file)

            # Validate ACLs
            missing_acls = validate_acls(running_acls, rtr_golden_acls)

            # Store results for the current device
            results_per_device[device_ip] = {
                "missing_commands": missing_commands_by_section,
                "missing_acls": missing_acls
            }

    else: # This is the NIPR SW checks
        for device_ip in ip_addrs:
            # Connect to device and get running configs
            connection_result = connect_to_device(device_ip, username, password, en_secret, bulk_show)
            
            # If connection fails, store the error and move to the next device
            if "error" in connection_result:
                results_per_device[device_ip] = {"error": connection_result["error"]}
                continue
            
            # Gets the "show" commands data from the connect_to_data function
            running_config = connection_result["running_config"]
            running_acls = connection_result["running_acls"]
            """    
            switchport_info = connection_result["switchport_info"]
            interface_info = connection_result["interface_info"]
            """                
            # Validate STIG configuration against the golden config
            missing_commands_by_section = validate_sw(running_config, gcs_file)

            # Validate ACLs
            missing_acls = validate_acls(running_acls, sw_golden_acls)

            # Validates interface information
            missing_interface_configs = validate_interfaces(
                connection_result["switchport_info"],
                connection_result["interface_info"],
                gint_file
            )

            # Store results for the current device
            results_per_device[device_ip] = {
                "missing_commands": missing_commands_by_section,
                "missing_acls": missing_acls,
                "missing_interface_configs": missing_interface_configs
            }                      
    
    accordion_data = restructure_for_accordion(results_per_device)
    
    # 2. Pass the NEW data structure to the template.
    #    We no longer need the old 'format_combined_output' function.
    return render_template('specter_post.html', name='SOCOM SPECTER', accordion_data=accordion_data)
    
    """
    # Format the final output string from all device results
    final_output = format_combined_output(results_per_device)

    # Render the results page
    return render_template('specter_post.html', name='SOCOM SPECTER', result=final_output)
    """    

# --- Helper Functions ---

def get_form_input(): # Gathers the user inputed information from the html site
    """
    Safely get user input from the submitted form by checking the TACACS option first.
    """
    # Use .get() to safely retrieve values, avoiding KeyErrors
    ip_addrs = request.form.getlist('ip_addrs')
    on_tacacs = request.form.get('on_tacacs') # Will be 'yes' or 'no'
    enclave = request.form.get('enclave') # Will be 'nipr' or 'transport'
    device_type = request.form.get('device_type') # Will be 'router', 'switch', or 'imaging_switch'

    rtr = None
    sw = None
    imaging_sw = None
    username = None
    password = None
    en_secret = None # Default to None

    if on_tacacs == 'yes':
        # Device is on TACACS, get TACACS credentials
        username = request.form.get('tacacs_username')
        password = request.form.get('tacacs_password')
        # en_secret is not needed for TACACS
        
    else: # Assumes 'no' or missing
        # Device is not on TACACS, get local credentials
        username = request.form.get('username')
        password = request.form.get('password')
        en_secret = request.form.get('en_secret')
    
    if enclave == 'lan':
        if device_type == 'router':
            rtr = request.form.get('device_type')
        elif device_type == 'switch':
            sw = request.form.get('device_type')
        else:
            imaging_sw = request.form.get('device_type')

    return ip_addrs, username, password, en_secret, imaging_sw, rtr

def open_golden_files(): # Opens the golden configurations and whats expected
    """Reads all the golden configuration files and returns their content."""
    with open('golden/bulk_config_file.txt', 'r') as f:
        bulk_show = f.read().splitlines()
    
    with open('golden/golden_config_rtr.json', 'r') as f:
        gcr_file = json.load(f)

    with open('golden/golden_config_sw.json', 'r') as f:
        gcs_file = json.load(f)
    
    with open('golden/golden_interfaces.json', 'r') as f:
        gint_file = json.load(f)
    
    # Unclass RTR ACLs
    rtr_golden_acls = {}
    rtr_acl_files = {
        "1": "golden/golden_acl1_file.txt",
        "2": "golden/golden_acl2_file.txt",
        "5": "golden/golden_acl5_file.txt",
        "55": "golden/golden_acl55_file.txt"
    }
    
    for name, path in rtr_acl_files.items():
        try:
            with open(path, 'r') as f:
                rtr_golden_acls[name] = [[line.strip(), 'false'] for line in f.readlines()]
        except FileNotFoundError:
            print(f"Warning: Golden ACL file not found at {path}")
            rtr_golden_acls[name] = []
    
    # Unclass SW ACLs
    sw_golden_acls = {}
    sw_acl_files = {
        "1": "golden/golden_acl1_file.txt",
        "2": "golden/golden_acl2_file.txt",
        "5": "golden/golden_acl5_file.txt",
        "55": "golden/golden_acl55_file.txt",
        "REDIRECT": "golden/golden_redirect_acl_file.txt"
    }
    
    for name, path in sw_acl_files.items():
        try:
            with open(path, 'r') as f:
                sw_golden_acls[name] = [[line.strip(), 'false'] for line in f.readlines()]
        except FileNotFoundError:
            print(f"Warning: Golden ACL file not found at {path}")
            sw_golden_acls[name] = []


    return bulk_show, gcr_file, gcs_file, rtr_golden_acls, sw_golden_acls, gint_file

def connect_to_device(device_ip, username, password, en_secret, bulk_show): # # Connects to the device and performs show commands
    """Connects to a single device and retrieves its configuration."""
    print('Connecting to ' + device_ip)
    ios_device = {
        'device_type': 'cisco_xe',
        'ip': device_ip,
        'username': username,
        'password': password,
        'secret': en_secret,
        'read_timeout_override': 120,
    }

    try:
        with ConnectHandler(**ios_device) as net_connect:
            net_connect.enable()
            running_config = net_connect.send_config_set(bulk_show)
            switchport_info = net_connect.send_command("show interfaces switchport", use_genie=True)
            interface_info = net_connect.send_command("show running-config all | section ^interface", use_genie=True)
            running_acls = {
                "1": net_connect.send_command("show access-list 1"),
                "2": net_connect.send_command("show access-list 2"),
                "5": net_connect.send_command("show access-list 5"),
                "55": net_connect.send_command("show access-list 55"),
                "REDIRECT": net_connect.send_command("show access-list REDIRECT")
            }
            return {"running_config": running_config, "switchport_info": switchport_info, "interface_info": interface_info, "running_acls": running_acls}
    except (NetmikoAuthenticationException, NetMikoTimeoutException, SSHException, EOFError) as e:
        error_message = f"{type(e).__name__} for {device_ip}: {e}"
        print(error_message)
        return {"error": error_message}
    except Exception as e:
        error_message = f"An unexpected error occurred with {device_ip}: {e}"
        print(error_message)
        return {"error": error_message}

def validate_sw(running_config, gcs_file): # Validate nipr switch configurations
    """Validates the running configuration against the STIG rules in the golden config file."""
    sections_to_compare = list(gcs_file.get('sections', {}).keys())
    running_config_set = set(line.strip() for line in running_config.splitlines() if line.strip())
    missing_commands_by_section = {}
    
    special_patterns = {
        'ip domain': r'ip domain(-| )name example',
        'no ip domain': r'no ip domain(-| )lookup',
        'ip ssh server algorithm encryption': r'ip ssh server algorithm encryption aes256.*',
        'ip ssh server algorithm mac': r'ip ssh server algorithm mac hmac-sha2-512.*',
        'ip ssh server algorithm kex': r'ip ssh server algorithm kex ecdh-sha2-nistp384.*',
        'ip ssh dh min size': r'ip ssh dh min size (4096|2048)',
        'aaa common-criteria policy': r'aaa common-criteria policy PW_POLICY.*',
        'username networks privilege': r'username networks privilege 0.*',
        'ntp authentication-key': r'ntp authentication-key 32 sha2.*',
        'path': r'path (flash|bootflash):.*',
        'logging source-interface': r'logging source-interface.*',
        'enable secret': r'enable secret.*',
        'snmp-server contact': r'snmp-server contact.*',
        'service-policy input system': r'service-policy input system-c( |o)pp-policy',
        'ip radius source': r'ip radius source.*'
    }

    for section_key in sections_to_compare:
        missing_commands = []
        for command in gcs_file.get('sections', {}).get(section_key, []):
            command = command.strip()
            command_found = False
            
            # Check for special patterns first
            for prefix, pattern in special_patterns.items():
                if command.startswith(prefix):
                    if any(re.match(pattern, running_cmd) for running_cmd in running_config_set):
                        command_found = True
                    break
            
            # If not a special pattern, check for a direct match
            if not command_found and command in running_config_set:
                command_found = True
            
            if not command_found:
                missing_commands.append(command)
        
        if missing_commands:
            missing_commands_by_section[section_key] = missing_commands
            
    return missing_commands_by_section

def validate_interfaces(switchport_info, interface_info, gint_file):
    missing_interface_configs = {}
    try:
        golden_standard_config = gint_file['interface_config']['standard_access_port']
        golden_unused_config = gint_file['interface_config']['unused_access_port']
        golden_trunk_config = gint_file['interface_config']['trunk_port']
    except KeyError as e:
        return {"error": f"Golden interface file is missing required key: {e}"}

    all_configured_interfaces = interface_info.get('interfaces', {})

    for interface_name, actual_config_dict in all_configured_interfaces.items():
        if not interface_name.startswith(('GigabitEthernet', 'FastEthernet', 'TenGigabitEthernet')):
            continue
        
        switchport_details = switchport_info.get(interface_name, {})
        if not switchport_details:
            continue
            
        golden_template_to_use = None
        state_description = ""
        
        mode = switchport_details.get('switchport_mode')

        # Logic Block 1: Handle Access Ports
        if mode == 'static access':
            op_status = switchport_details.get('operational_mode')
            
            if op_status == 'down':
                golden_template_to_use = golden_unused_config
                state_description = "Unused/Down Interface"
            else:
                golden_template_to_use = golden_standard_config
                state_description = "Active Access Interface"
                if 'description' in actual_config_dict:
                    actual_config_dict['description'] = "DOT1X HOST PORT - lan"

        # Logic Block 2: Handle Trunk Ports (at the same level as the access check)
        elif mode == 'trunk':
            golden_template_to_use = golden_trunk_config
            state_description = "Trunk Interface"
        
        # If it's not a trunk or access port, or no template was assigned, skip it
        if not golden_template_to_use:
            continue

        missing_keys = sorted(set(golden_template_to_use.keys()) - set(actual_config_dict.keys()))
        mismatch_values = {
            key: {
                "expected": golden_template_to_use[key],
                "actual": actual_config_dict.get(key, 'Not Present')
            }
            for key in golden_template_to_use.keys() & actual_config_dict.keys()
                if golden_template_to_use[key] != actual_config_dict.get(key)
        }

        if missing_keys or mismatch_values:
            missing_interface_configs[interface_name] = {
                "state": state_description,
                "missing_keys": missing_keys,
                "mismatched_values": mismatch_values,
            }
            
    return missing_interface_configs

def validate_rtr(running_config, gcr_file): # Validate nipr router configs
    """Validates the running configuration against the STIG rules in the golden config file."""
    sections_to_compare = list(gcr_file.get('sections', {}).keys())
    running_config_set = set(line.strip() for line in running_config.splitlines() if line.strip())
    missing_commands_by_section = {}
    
    special_patterns = {
        'ip domain': r'ip domain(-| )name example',
        'no ip domain': r'no ip domain(-| )lookup',
        'ip ssh server algorithm encryption': r'ip ssh server algorithm encryption aes256.*',
        'ip ssh server algorithm mac': r'ip ssh server algorithm mac hmac-sha2-512.*',
        'ip ssh server algorithm kex': r'ip ssh server algorithm kex ecdh-sha2-nistp384.*',
        'ip ssh dh min size': r'ip ssh dh min size (4096|2048)',
        'aaa common-criteria policy': r'aaa common-criteria policy PW_POLICY.*',
        'username networks privilege': r'username networks privilege 0.*',
        'ntp authentication-key': r'ntp authentication-key 32 sha2.*',
        'path': r'path (flash|bootflash):.*',
        'logging source-interface': r'logging source-interface.*',
        'enable secret': r'enable secret.*',
        'snmp-server contact': r'snmp-server contact.*',
        'service-policy input system': r'service-policy input system-c( |o)pp-policy'
    }

    for section_key in sections_to_compare:
        missing_commands = []
        for command in gcr_file.get('sections', {}).get(section_key, []):
            command = command.strip()
            command_found = False
            
            # Check for special patterns first
            for prefix, pattern in special_patterns.items():
                if command.startswith(prefix):
                    if any(re.match(pattern, running_cmd) for running_cmd in running_config_set):
                        command_found = True
                    break
            
            # If not a special pattern, check for a direct match
            if not command_found and command in running_config_set:
                command_found = True
            
            if not command_found:
                missing_commands.append(command)
        
        if missing_commands:
            missing_commands_by_section[section_key] = missing_commands
            
    return missing_commands_by_section

def validate_acls(running_acls, golden_acls): # Validates device ACLs
    """Validates running ACLs against the golden ACL files."""
    missing_acls = {}

    def validate_single_acl(running_output, golden_rules, acl_name, is_extended=False):
        """Helper to validate one ACL."""
        missing = []
        if not running_output: return missing
        
        clean_running_output = running_output.replace(", wildcard bits", "")
        
        for rule_info in golden_rules:
            rule = rule_info[0]
            # Skip header lines that are expected to be different
            list_type = "extended" if is_extended else "standard"
            if rule.lower() in (f"ip access-list {list_type} {acl_name}".lower(), f"{list_type} ip access list {acl_name}".lower()):
                continue
            
            if rule not in clean_running_output:
                missing.append(rule)
        return missing

    for acl_name, golden_rules in golden_acls.items():
        is_extended = acl_name == "REDIRECT"
        missing = validate_single_acl(running_acls.get(acl_name), golden_rules, acl_name, is_extended)
        if missing:
            missing_acls[f"ACL {acl_name}"] = missing
            
    return missing_acls

def format_combined_output(results_per_device): # Old structure method pre-interface checks
    """Formats the validation results into a single string for display."""
    final_output_str = ""
    for device, results in results_per_device.items():
        final_output_str += f"--- Results for {device} ---\n"
        if "error" in results:
            final_output_str += f"  Error: {results['error']}\n\n"
            continue

        is_compliant = not results["missing_commands"] and not results["missing_acls"] and not results["missing_interface_configs"]

        if is_compliant:
            final_output_str += "  Device is STIG compliant.\n\n"
        else:
            final_output_str += "  Device is not STIG compliant. Missing commands:\n\n"
            if results["missing_commands"]:
                for section, commands in results["missing_commands"].items():
                    final_output_str += f"  Section {section}:\n"
                    for cmd in commands:
                        final_output_str += f"    - {cmd}\n"
            
            if results["missing_acls"]:
                final_output_str += "\n  Missing ACL entries:\n"
                for acl_name, commands in results["missing_acls"].items():
                    final_output_str += f"  {acl_name}:\n"
                    for cmd in commands:
                        final_output_str += f"    - {cmd}\n"

            if results.get("missing_interface_configs"):
                final_output_str += "\n Missing interface entries:\n"
                for interface, findings in results["missing_interface_configs"].items():
                    final_output_str += f"  {interface}:\n"
                    if findings.get("missing_keys"):
                        for key in findings["missing_keys"]:
                            final_output_str += f"      - Missing Config: '{key}'\n"
                
                    # Check for and format any mismatched values
                    if findings.get("mismatched_values"):
                        for key, values in findings["mismatched_values"].items():
                            final_output_str += f"      - Mismatch on '{key}': Expected '{values['expected']}', Found '{values['actual']}'\n"
        final_output_str += "\n"
        
    return final_output_str.strip()

def restructure_for_accordion(results_per_device):
    """
    Transforms ALL validation results into a per-finding structure,
    including device connection errors, for a unified accordion view.
    """
    findings_by_command = {}
    for device_ip, results in results_per_device.items():
        
        # First, check if this device had a connection error.
        if "error" in results:
            finding_description = "Device Connection Errors"
            
            # If this is the first error, initialize the finding category.
            findings_by_command.setdefault(finding_description, [])
            
            # Add the specific error message to the list for this category.
            findings_by_command[finding_description].append(f"{device_ip}: {results['error']}")
            
            # Stop processing this failed device
            continue

        # Part 1: Process Interface Findings
        interface_findings = results.get("missing_interface_configs", {})
        for interface_name, findings in interface_findings.items():
            state = findings.get('state', 'Unknown State')
            # Process missing keys
            for missing_key in findings.get("missing_keys", []):
                finding_description = f"Missing Config ({state}): '{missing_key}'"
                findings_by_command.setdefault(finding_description, [])
                findings_by_command[finding_description].append(f"{device_ip} - {interface_name}")

            # Process mismatched values
            for key, values in findings.get("mismatched_values", {}).items():
                finding_description = f"Mismatch on Config ({state}): '{key}'"
                detail = (
                    f"{device_ip} - {interface_name} "
                    f"(Expected: '{values['expected']}', Found: '{values['actual']}')"
                )
                findings_by_command.setdefault(finding_description, [])
                findings_by_command[finding_description].append(detail)

        # Part 2: Process STIG Findings
        stig_findings = results.get("missing_commands", {})
        for section, commands in stig_findings.items():
            finding_description = f"Missing STIG Commands in Section: {section}"
            
            findings_by_command.setdefault(finding_description, {
                "total_missing_count": 0,
                "devices": {}
            })
            
            if commands:
                findings_by_command[finding_description]["devices"][device_ip] = commands
                findings_by_command[finding_description]["total_missing_count"] += len(commands)

    return findings_by_command



# --- Main Execution ---

if __name__ == '__main__': # Runs the flask app
    app.run(debug=True)
