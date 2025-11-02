# UniFi Protect v6+ for Home Assistant

A modern Home Assistant integration for **UniFi Protect v6.1.79+** using the new Protect API with token authentication.

## Why This Integration?

UniFi Protect v6 removed the ability to create local admin users, breaking older integrations. This integration uses the new **API token authentication** introduced in Protect v6, making it the successor to previous UniFi Protect integrations.

## Requirements

- **UniFi Protect v6.1.79 or newer**
- Home Assistant 2024.1.0 or newer
- API token generated in UniFi Protect UI

## Features

### Supported Entities

- **Camera Entities**
  - Live camera feed with RTSP streaming
  - Camera snapshots
  - Camera information and status

- **Binary Sensors**
  - Motion detection
  - Doorbell press detection (for doorbell cameras)
  - Online/offline status

- **Sensors**
  - NVR storage used
  - NVR storage available
  - Storage usage percentage

- **Switches**
  - Privacy mode (disable/enable camera)
  - Recording mode (enable/disable recording)

- **Buttons**
  - Reboot camera

### Key Features

- **Real-time updates** via WebSocket connection
- **API token authentication** (no local admin required)
- **Automatic device discovery** from UniFi Protect
- **SSL verification** configurable (useful for self-signed certificates)
- **Rich device information** including firmware versions, models, etc.
- **PTZ camera control** - Control pan-tilt-zoom cameras with presets and patrols

### PTZ Camera Control

For PTZ cameras, the integration provides services to control camera movement:

- **`unifi_protect.ptz_start_patrol`** - Start a patrol on slot 0-4
- **`unifi_protect.ptz_stop_patrol`** - Stop the active patrol
- **`unifi_protect.ptz_goto_preset`** - Move camera to a preset position (-1 for home, 0+ for saved presets)

**Example automation:**
```yaml
automation:
  - alias: "Move PTZ camera to preset 1 on motion"
    trigger:
      platform: state
      entity_id: binary_sensor.front_door_motion
      to: "on"
    action:
      service: unifi_protect.ptz_goto_preset
      target:
        entity_id: camera.front_ptz
      data:
        preset: 1
```

### Alarm Manager Integration

The integration supports triggering UniFi Protect alarms via webhook:

- **`unifi_protect.trigger_alarm`** - Send webhook to trigger configured alarms

Alarms must be configured in UniFi Protect UI with a matching trigger ID. This allows you to trigger Protect's alarm system from Home Assistant automations.

**Example automation:**
```yaml
automation:
  - alias: "Trigger Protect alarm on door sensor"
    trigger:
      platform: state
      entity_id: binary_sensor.back_door
      to: "on"
    action:
      service: unifi_protect.trigger_alarm
      data:
        trigger_id: "home_security"
```

**Setup in UniFi Protect:**
1. Go to Protect UI → Settings → Alarm Manager
2. Create or edit an alarm
3. Set the webhook trigger ID to match your automation (e.g., "home_security")
4. Configure alarm actions (sirens, notifications, recording, etc.)

## Installation

### HACS (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Add this repository as a custom repository in HACS:
   - Go to HACS > Integrations
   - Click the three dots in the top right corner
   - Select "Custom repositories"
   - Add the URL: `https://github.com/yourusername/ha-unifi-protect`
   - Select "Integration" as the category
3. Click "Download" on the UniFi Protect v6+ integration
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/unifi_protect` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

### Step 1: Generate API Token in UniFi Protect

1. Open the UniFi Protect web interface
2. Navigate to **Settings > Users**
3. Select the **API** tab
4. Click **Create API Token**
5. Give it a descriptive name (e.g., "Home Assistant")
6. Copy the generated token (you won't be able to see it again!)

### Step 2: Add Integration in Home Assistant

1. Go to **Settings > Devices & Services**
2. Click **"+ Add Integration"**
3. Search for **"UniFi Protect"**
4. Follow the configuration wizard:
   - **Host**: Enter your UniFi Protect host (IP address or hostname, e.g., `192.168.1.100` or `protect.local`)
   - **API Token**: Paste the token you generated in Step 1
   - **Verify SSL**: Enable if using valid SSL certificate, disable for self-signed certificates

5. Click **Submit**

The integration will automatically discover all cameras and sensors from your UniFi Protect system.

## API Endpoints

The integration uses the UniFi Protect v6 Integration API with the following endpoints:

**Base URL:** `https://{host}/proxy/protect/integration/v1/`

**Authentication:** API token via `X-API-KEY` header

**REST API Endpoints:**
- `/proxy/protect/integration/v1/meta/info` - Application information
- `/proxy/protect/integration/v1/viewers` - Viewer management
- `/proxy/protect/integration/v1/liveviews` - Liveview configuration
- `/proxy/protect/integration/v1/cameras/{id}/ptz/patrol/start/{slot}` - Start PTZ patrol
- `/proxy/protect/integration/v1/cameras/{id}/ptz/patrol/stop` - Stop PTZ patrol
- `/proxy/protect/integration/v1/cameras/{id}/ptz/goto/{slot}` - Move to PTZ preset
- `/proxy/protect/integration/v1/alarm-manager/webhook/{id}` - Trigger alarm
- `/proxy/protect/api/bootstrap` - Bootstrap data (legacy endpoint)
- `/proxy/protect/api/cameras` - Camera management (legacy endpoint)

**WebSocket Endpoints:**
- `/proxy/protect/integration/v1/subscribe/devices` - Real-time device updates
- `/proxy/protect/integration/v1/subscribe/events` - Real-time events (motion, doorbell, etc.)

## Troubleshooting

### Connection Issues

- Verify your UniFi Protect is running v6.1.79 or newer
- Check that the API token is valid and hasn't been deleted
- Ensure Home Assistant can reach your Protect host on the network
- If using HTTPS with self-signed certificate, disable SSL verification

### No Devices Found

- Verify cameras are adopted and online in UniFi Protect
- Check the Home Assistant logs for error messages
- Try reloading the integration

### WebSocket Disconnects

The integration automatically reconnects if the WebSocket connection drops. Check your network stability if reconnections are frequent.

## Development

### Architecture

```
custom_components/unifi_protect/
├── __init__.py          # Integration setup
├── api.py               # REST + WebSocket API client
├── config_flow.py       # Configuration UI
├── coordinator.py       # Data update coordinator
├── models.py            # Data models
├── entity.py            # Base entity class
├── const.py             # Constants
├── camera.py            # Camera platform
├── sensor.py            # Sensor platform
├── binary_sensor.py     # Binary sensor platform
├── switch.py            # Switch platform
├── button.py            # Button platform
├── manifest.json        # Integration metadata
└── strings.json         # UI translations
```

### Key Components

- **API Client** (`api.py`): Handles REST API requests and WebSocket connections
- **Coordinator** (`coordinator.py`): Manages data updates and WebSocket events
- **Models** (`models.py`): Type-safe data models for cameras, NVR, and sensors

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/yourusername/ha-unifi-protect/issues).

## License

MIT License
