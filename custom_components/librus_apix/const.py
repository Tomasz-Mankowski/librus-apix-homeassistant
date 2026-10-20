"""Constants for the Librus APIX integration."""

from zoneinfo import ZoneInfo

DOMAIN = "librus_apix"

# Librus shows Polish local time.
LIBRUS_TZ = ZoneInfo("Europe/Warsaw")

# Config entry data
CONF_SERVER_URL = "server_url"  # developer option: mock server, login skipped
SECTION_DEVELOPER = "developer"

# Options: poll intervals in minutes, schedule months ahead, message count
CONF_INTERVAL_STUDENT = "interval_student"
CONF_INTERVAL_LUCKY_NUMBER = "interval_lucky_number"
CONF_INTERVAL_GRADES = "interval_grades"
CONF_INTERVAL_MESSAGES = "interval_messages"
CONF_INTERVAL_ANNOUNCEMENTS = "interval_announcements"
CONF_INTERVAL_SCHEDULE = "interval_schedule"
CONF_TIMEFRAME = "timeframe"
CONF_MESSAGE_COUNT = "message_count"

INTERVAL_OPTIONS = (
    CONF_INTERVAL_STUDENT,
    CONF_INTERVAL_LUCKY_NUMBER,
    CONF_INTERVAL_GRADES,
    CONF_INTERVAL_MESSAGES,
    CONF_INTERVAL_ANNOUNCEMENTS,
    CONF_INTERVAL_SCHEDULE,
)
DEFAULT_OPTIONS = {
    CONF_INTERVAL_STUDENT: 1440,
    CONF_INTERVAL_LUCKY_NUMBER: 180,
    CONF_INTERVAL_GRADES: 15,
    CONF_INTERVAL_MESSAGES: 15,
    CONF_INTERVAL_ANNOUNCEMENTS: 15,
    CONF_INTERVAL_SCHEDULE: 60,
    CONF_TIMEFRAME: 1,
    CONF_MESSAGE_COUNT: 20,
}
# Student-info interval default of entries made before 1.1.0 (minor version 1)
OLD_DEFAULT_INTERVAL_STUDENT = 360
# Options: rules of the calculated averages (F13)
CONF_AVERAGE_WEIGHTS = "average_weights"
CONF_AVERAGE_ONLY_COUNTED = "average_only_counted"
CONF_AVERAGE_PLUS = "average_plus"
CONF_AVERAGE_MINUS = "average_minus"
DEFAULT_AVERAGE_OPTIONS = {
    CONF_AVERAGE_WEIGHTS: True,
    CONF_AVERAGE_ONLY_COUNTED: True,
    CONF_AVERAGE_PLUS: 0.5,
    CONF_AVERAGE_MINUS: 0.25,
}
MAX_GRADE_MODIFIER = 1.0

MIN_INTERVAL = 10
MAX_INTERVAL = 24 * 60
MAX_TIMEFRAME = 6
MIN_MESSAGE_COUNT = 1
MAX_MESSAGE_COUNT = 100

# Request queue (shared by all entries)
REQUEST_GAP = 1.5  # seconds between two HTTP requests
REQUEST_TIMEOUT = (10, 30)  # connect and read timeout in seconds
BACKOFF_START = 5 * 60  # first backoff delay in seconds; doubles on each failure
BACKOFF_MAX = 2 * 60 * 60  # longest backoff delay in seconds
