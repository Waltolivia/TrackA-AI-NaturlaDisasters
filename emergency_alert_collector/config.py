NWS_USER_AGENT = "EmergencyAlertCollector/1.0 your-email@example.com"

NWS_URL = "https://api.weather.gov/alerts/active"
FEMA_URL = (
    "https://gis.fema.gov/arcgis/rest/services/"
    "FEMA/IPAWS_Archive/FeatureServer/1/query"
)

NWS_INTERVAL_SECONDS = 60
FEMA_INTERVAL_SECONDS = 15 * 60
DATABASE_PATH = "data/alerts.db"

FEMA_LOOKBACK_HOURS = 48
FEMA_PAGE_SIZE = 1000

# The collector only SAVES alerts matching these natural-hazard terms.
DISASTER_KEYWORDS = [
    "earthquake", "aftershock", "seismic", "tsunami",
    "flood", "flash flood", "coastal flood", "river flood",
    "urban flood", "inundation",
    "thunderstorm", "severe thunderstorm", "tornado", "hail",
    "derecho", "storm", "lightning", "dangerous wind",
    "hurricane", "tropical storm", "tropical depression", "storm surge",
    "wildfire", "wild fire", "forest fire", "brush fire", "grass fire",
    "fire weather", "red flag", "smoke",
    "blizzard", "winter storm", "ice storm", "freezing rain",
    "heavy snow", "snow squall", "avalanche",
    "extreme cold", "extreme heat",
    "volcano", "volcanic", "ash",
    "landslide", "mudslide", "debris flow",
    "dust storm", "dust devil", "sandstorm",
    "rip current", "high surf", "coastal hazard",
]

# These do NOT get saved unless the same alert also clearly describes
# a natural hazard. They help exclude ordinary non-weather emergencies.
NON_DISASTER_KEYWORDS = [
    "amber alert", "silver alert", "missing child", "missing person",
    "local area emergency", "local area alert",
    "boil water", "civil emergency", "law enforcement",
    "police", "crime", "active shooter",
]
