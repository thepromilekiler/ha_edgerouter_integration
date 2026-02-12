# Ubiquiti EdgeRouter for Home Assistant

Custom component to integrate Ubiquiti EdgeRouter devices into Home Assistant.

## Features
- **System Monitoring**: Uptime, Firmware Version.
- **Health Checks**: Detects DHCP conflicts, Kernel warnings, and SSH Auth failures.
- **Traffic Rates**: Real-time Rx/Tx throughput (Mbps) for all interfaces.
- **Hardware Stats**: CPU and RAM usage.

## Installation

### HACS (Recommended)
1. Add this repository to HACS as a Custom Repository.
2. Search for "Ubiquiti EdgeRouter" and install.
3. Restart Home Assistant.

### Manual
1. Copy the `custom_components/edgerouter` folder to your HA `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration
1. Go to **Settings > Devices & Services**.
2. Click **Add Integration**.
3. Search for **Ubiquiti EdgeRouter**.
4. Enter your Router IP, Username, and Password.

## Requirements
- SSH access enabled on the EdgeRouter.
- Python `paramiko` library (automatically installed by HA).
