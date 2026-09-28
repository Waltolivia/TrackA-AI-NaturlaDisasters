# NWS contains many useful alerts that are not natural disasters. Keep this allow-list explicit and auditable.
NATURAL_TERMS={
 'tornado','flash flood','flood','hurricane','tropical storm','storm surge','severe thunderstorm',
 'extreme wind','high wind','dust storm','blizzard','winter storm','ice storm','snow squall',
 'avalanche','tsunami','earthquake','volcano','wildfire','fire weather','red flag','landslide',
 'severe storms','wildfires','volcanoes','earthquakes','floods','landslides','drought','dust and haze',
 'sea and lake ice','snow'
}

def is_natural_disaster(alert):
    text=f'{alert.event_type} {alert.headline}'.lower()
    return any(term in text for term in NATURAL_TERMS)
