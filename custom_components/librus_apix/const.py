"""Constants for the Librus APIX integration."""

DOMAIN = "librus_apix"

# Request queue (shared by all entries)
REQUEST_GAP = 1.5  # seconds between two HTTP requests
REQUEST_TIMEOUT = (10, 30)  # connect and read timeout in seconds
BACKOFF_START = 5 * 60  # first backoff delay in seconds; doubles on each failure
BACKOFF_MAX = 2 * 60 * 60  # longest backoff delay in seconds
