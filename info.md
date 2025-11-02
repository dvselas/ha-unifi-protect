# UniFi Protect v6+ Integration

Modern integration for **UniFi Protect v6.1.79+** using API token authentication.

## Why This Integration?

UniFi Protect v6 removed local admin accounts. This integration uses the new **API token authentication**, making it compatible with Protect v6+.

## Features

- **Real-time updates** via WebSocket
- **Camera entities** with live streaming and snapshots
- **Motion detection** binary sensors
- **Doorbell** detection for doorbell cameras
- **Storage monitoring** sensors for NVR
- **Privacy mode** and **recording** switches
- **Reboot** buttons for cameras

## Requirements

- **UniFi Protect v6.1.79 or newer**
- API token from Protect UI (Settings > Users > API)
- Home Assistant 2024.1.0 or newer

## Quick Setup

1. Generate API token in UniFi Protect UI (Settings > Users > API)
2. Add integration in Home Assistant
3. Enter your Protect host and API token
4. Done! All cameras and devices are auto-discovered
