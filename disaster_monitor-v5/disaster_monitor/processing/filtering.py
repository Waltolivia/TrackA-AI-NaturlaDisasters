import re


# NWS alerts that are serious enough to retain.
NWS_KEEP_TERMS = {
    "hurricane warning",
    "hurricane watch",
    "tropical storm warning",
    "tropical storm watch",
    "typhoon warning",
    "typhoon watch",
    "storm surge warning",
    "storm surge watch",

    "flash flood warning",
    "flash flood emergency",
    "flood warning",
    "flood emergency",
    "tornado",

    "tsunami warning",
    "tsunami watch",

    "volcano warning",
    "volcano watch",
    "volcanic ash warning",

    "landslide warning",
    "debris flow warning",

    "evacuation immediate",
}


# Alerts to reject even if another keyword happens to match.
NWS_REJECT_TERMS = {
    "severe thunderstorm",
    "severe storm",

    "coastal flood",
    "coastal flooding",
    "flood advisory",
    "flash flood watch",

    "fire weather",
    "red flag",

    "wind advisory",
    "high wind",
    "extreme wind",

    "heat advisory",
    "excessive heat",
    "cold weather",
    "freeze warning",
    "frost advisory",

    "dense fog",
    "smoke",
    "air quality",
    "dust haze",
    "dust and haze",

    "winter weather",
    "winter storm watch",
    "snow",
    "ice",
    "blizzard watch",

    "special weather statement",
    "hazardous weather outlook",

    "small craft",
    "gale warning",
    "rip current",
    "beach hazards",
    "marine weather",
}


# NASA EONET categories worth retaining.
#
# "wildfires" keeps active wildfire events from NASA EONET.
# It does NOT keep NWS Red Flag or Fire Weather alerts.
EONET_KEEP_CATEGORIES = {
    "earthquakes",
    "volcanoes",
    "floods",
    "landslides"
}


def _normalise(value):
    return re.sub(r"[\s_-]+", "", str(value or "").lower())


def is_natural_disaster(alert):
    source = str(getattr(alert, "source", "") or "").upper()

    event_type = str(getattr(alert, "event_type", "") or "").lower()
    headline = str(getattr(alert, "headline", "") or "").lower()
    text = f"{event_type} {headline}"

    # NASA EONET uses category IDs such as:
    # earthquakes, volcanoes, floods, landslides, wildfires
    if source == "NASA_EONET":
        category = _normalise(alert.event_type)
        return category in {
            _normalise(value)
            for value in EONET_KEEP_CATEGORIES
        }

    # NWS alerts require an explicit high-impact phrase.
    if source == "NWS":
        if any(term in text for term in NWS_REJECT_TERMS):
            return False

        return any(term in text for term in NWS_KEEP_TERMS)

    # Do not save unknown sources unless explicitly added above.
    return False
