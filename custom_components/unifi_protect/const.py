"""Constants for the UniFi Protect integration."""

DOMAIN = "unifi_protect"

# Configuration
CONF_API_TOKEN = "api_token"
CONF_VERIFY_SSL = "verify_ssl"
DEFAULT_POLLING_INTERVAL = 30
DEFAULT_VERIFY_SSL = False

# Defaults
DEFAULT_NAME = "UniFi Protect"

# Attributes
ATTR_CAMERA_ID = "camera_id"
ATTR_EVENT_TYPE = "event_type"
ATTR_EVENT_SCORE = "event_score"

# Services
SERVICE_SET_RECORDING_MODE = "set_recording_mode"
SERVICE_SET_PRIVACY_MODE = "set_privacy_mode"
SERVICE_PTZ_START_PATROL = "ptz_start_patrol"
SERVICE_PTZ_STOP_PATROL = "ptz_stop_patrol"
SERVICE_PTZ_GOTO_PRESET = "ptz_goto_preset"
SERVICE_TRIGGER_ALARM = "trigger_alarm"

# PTZ
ATTR_PTZ_SLOT = "slot"
ATTR_PTZ_PRESET = "preset"

# Alarm
ATTR_TRIGGER_ID = "trigger_id"

# Recording modes
RECORDING_MODE_ALWAYS = "always"
RECORDING_MODE_NEVER = "never"
RECORDING_MODE_MOTION = "motion"
RECORDING_MODE_DETECTIONS = "detections"

RECORDING_MODES = [
    RECORDING_MODE_ALWAYS,
    RECORDING_MODE_NEVER,
    RECORDING_MODE_MOTION,
    RECORDING_MODE_DETECTIONS,
]
