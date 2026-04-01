# STIG Compliance (SPECTER)

## Overview

**SPECTER** (**S**ecurity **P**olicy **E**valuation and **C**ompliance **T**ool for **E**nforcement and **R**eview) is a Python/Flask web application for automating STIG (Security Technical Implementation Guide) compliance assessments on Cisco IOS network devices. It connects to devices over SSH, compares their running configurations and ACLs against golden baselines, and presents a structured compliance report.

## Features

- **Web Interface:** Bootstrap-styled browser UI for entering device credentials and viewing results.
- **Multi-Enclave Support:** Separate compliance checks for NIPR (routers, switches, imaging switches) and Transport enclaves.
- **Automated STIG Compliance Checks:** Validates running device configs against section-based JSON golden templates.
- **ACL Validation:** Compares device ACLs (1, 2, 5, 55, and REDIRECT) against golden ACL text files.
- **Interface Validation:** Checks switchport and interface configurations against a golden interface JSON template (switch only).
- **TACACS & Local Auth:** Supports both TACACS and local device credentials from the web form.
- **Comprehensive Error Handling:** Gracefully handles SSH timeouts, authentication failures, and missing golden files.
- **Accordion Results View:** Per-device compliance results displayed in collapsible accordion sections.

## Directory Structure

```
stig_compliance/
│
├── stig_checker/
│   ├── stig_check_flask.py               # Flask web app — main application logic
│   ├── templates/
│   │   ├── index.html                    # Web UI: input form (device IPs, credentials, enclave/device type)
│   │   └── specter_post.html             # Web UI: compliance results output page
│   ├── static/
│   │   ├── specter.png                   # SPECTER logo used in the navigation bar
│   │   ├── bootstrap.css                 # Bootstrap CSS for styling
│   │   └── bootstrap.bundle.js           # Bootstrap JS bundle
│   └── golden/
│       ├── bulk_config_file.txt          # "show" commands sent to devices before config retrieval
│       ├── golden_config_rtr.json        # Section-based golden STIG config for NIPR routers
│       ├── golden_config_sw.json         # Section-based golden STIG config for NIPR switches
│       ├── golden_interfaces.json        # Golden interface/switchport config template (switches)
│       ├── golden_acl1_file.txt          # Golden ACL 1 template
│       ├── golden_acl2_file.txt          # Golden ACL 2 template
│       ├── golden_acl5_file.txt          # Golden ACL 5 template
│       ├── golden_acl55_file.txt         # Golden ACL 55 template
│       └── golden_redirect_acl_file.txt  # Golden REDIRECT ACL template (switches only)
├── requirements.txt                      # Python dependencies
└── README.md                             # This file
```

## How It Works

### 1. Web Form (`index.html` → `/submit`)
The home page presents a form where users provide:
- One or more device IP addresses
- Authentication method: **TACACS** (username + password) or **Local** (username, password, enable secret)
- **Enclave** selection: NIPR or Transport
- **Device type**: Router, Switch, or Imaging Switch (NIPR); Router or Switch (Transport)

### 2. Compliance Check (`stig_check_flask.py`)
On form submission the Flask app:
1. Connects to each device via SSH using **Netmiko**.
2. Sends the commands listed in `bulk_config_file.txt` to retrieve running config, ACL output, and (for switches) interface/switchport info.
3. Validates the running config against the relevant JSON golden file:
   - **Routers** → `golden_config_rtr.json` (sections 2.1, 2.2, 3.1–3.10, 4.1.3, 4.1.4, 7)
   - **Switches** → `golden_config_sw.json`
4. Validates each ACL against its corresponding golden text file.
5. For switches, additionally validates interface configurations against `golden_interfaces.json`.
6. Aggregates per-device results and renders `specter_post.html` with an accordion-style report.

### 3. Golden Configuration Files (`golden/`)
| File | Purpose |
|------|---------|
| `bulk_config_file.txt` | List of `show` commands sent to the device |
| `golden_config_rtr.json` | STIG config sections for NIPR routers |
| `golden_config_sw.json` | STIG config sections for NIPR switches |
| `golden_interfaces.json` | Expected interface/switchport settings |
| `golden_acl{N}_file.txt` | Expected lines for standard ACLs 1, 2, 5, 55 |
| `golden_redirect_acl_file.txt` | Expected lines for the REDIRECT ACL (switches) |

## Dependencies

Install Python dependencies with:

```bash
pip install -r requirements.txt
```

Key packages: `Flask`, `Netmiko`, `Paramiko`, `ntc_templates`, `textfsm`

## Running the Application

```bash
cd stig_checker
python stig_check_flask.py
```

Then open a browser to `http://localhost:5000`.

## Error Handling

The application handles:
- SSH connection timeouts and authentication failures (per device, without stopping the batch)
- Missing golden configuration files (logs a warning and continues)
- Device communication errors (e.g., SSH not enabled on device)

All errors are captured per device and surfaced in the results page.

## Extending the Project

- Add new STIG sections by updating `golden_config_rtr.json` or `golden_config_sw.json`.
- Add new ACL checks by adding a golden ACL text file and referencing it in `open_golden_files()`.
- Support additional device types or enclaves by extending `get_form_input()` and adding corresponding validation functions.

## License

*No license specified. For reuse or contribution, contact the repository owner.*

---
