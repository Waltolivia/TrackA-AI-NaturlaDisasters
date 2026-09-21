# Collection settings

# NWS asks API clients to identify themselves with a User-Agent.
# Replace the example email with your contact information.
NWS_USER_AGENT = "EmergencyAlertCollector/1.0 your-email@example.com"

NWS_URL = "https://api.weather.gov/alerts/active"

FEMA_URL = (
    "https://gis.fema.gov/arcgis/rest/services/"
    "FEMA/IPAWS_Archive/FeatureServer/1/query"
)

# NWS is checked every minute.
NWS_INTERVAL_SECONDS = 60

# FEMA's archive is delayed, so it does not need to be checked as often.
FEMA_INTERVAL_SECONDS = 15 * 60

DATABASE_PATH = "data/alerts.db"

# FEMA requests use a small overlap so a temporary request problem is less
# likely to make us miss a record. Duplicates are removed by identifier.
FEMA_LOOKBACK_HOURS = 48

# Maximum number of FEMA records requested in one page.
FEMA_PAGE_SIZE = 1000
