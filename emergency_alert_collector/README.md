This is a AI made code, human edited. It is for a research project referring to Natural Disasters and a way to track updated and live data all over the nation. 

# Emergency Alert Collector

A small Python collector for:
- National Weather Service (NWS) active weather alerts
- FEMA IPAWS archived alerts (non-weather and weather messages appearing in the archive)

The collector stores normalized alert information and the original JSON in a SQLite database.

## Why these sources?

NWS provides active alerts through `https://api.weather.gov/alerts/active`.

FEMA's IPAWS archive is an authoritative archive of Common Alerting Protocol (CAP) messages. FEMA publishes it with about a 24-hour delay, so it should be treated as an archive/ground-truth source rather than a live-alert feed.

## Project files

- `collector.py` - continuously collects both sources
- `database.py` - creates and writes the SQLite database
- `config.py` - settings
- `view_alerts.py` - simple readable command-line viewer
- `requirements.txt` - Python dependency
- `data/alerts.db` - created automatically when the collector first runs

## 1. Install

Python 3.10+ is recommended.

```bash
python -m venv .venv
```

Activate it:

macOS/Linux:
```bash
source .venv/bin/activate
```

Windows:
```powershell
.venv\Scripts\Activate.ps1
```

Then:

```bash
pip install -r requirements.txt
```

## 2. Configure the NWS user agent

Open `config.py` and replace:

```python
NWS_USER_AGENT = "EmergencyAlertCollector/1.0 your-email@example.com"
```

with your own contact information.

NWS asks clients to identify themselves with a User-Agent containing contact information.

## 3. Test one collection cycle

Run:

```bash
python collector.py --once
```

You should see how many NWS and FEMA records were collected.

## 4. View saved alerts

```bash
python view_alerts.py
```

Useful examples:

```bash
python view_alerts.py --source NWS --limit 20
python view_alerts.py --source FEMA --limit 20
python view_alerts.py --event "Tornado Warning"
python view_alerts.py --days 1
```

## 5. Run continuously

```bash
python collector.py
```

The default schedule is:
- NWS: every 60 seconds
- FEMA: every 15 minutes

The collector does not create a new copy every time an unchanged alert is seen. It uses the source identifier plus a content hash to save only new alert versions.

## Important storage decision

Keep `data/alerts.db`.

It is the main historical database.

The database stores the normalized fields plus the original source JSON. This means you can change the viewer or analysis code later without losing information.

For a Raspberry Pi, I recommend eventually putting the database on a USB SSD if you expect to keep years of data. For initial development, an SD card is fine.

## Current limitations

This first version is deliberately small.

It does not yet:
- send notifications
- provide a web dashboard
- download every historical FEMA record
- attempt to decide whether an alert is "true" or "important"
- predict disasters

It records what the government sources reported.

## Moving to the Raspberry Pi

Copy this entire folder to the Pi and run the same commands. Later, use a systemd service so the collector starts automatically when the Pi boots.



## Human Test 9/21/26

Testing running it in the Terminal on my computer using: python3 collector.py --once

and it started: 
Collecting NWS alerts...
NWS: 407 new alert version(s)
Collecting FEMA IPAWS archive...
FEMA: 9 new alert version(s)

# Successfully Provided:

======================================================================
Source:       FEMA
Event:        Flash Flood Warning
Headline:     Flash Flood Warning issued September 20 at 1:54AM EDT until September 20 at 5:00AM EDT by NWS Wilmington OH
Severity:     Severe
Urgency:      Immediate
Certainty:    Likely
Area:         Clinton, OH; Warren, OH
Sent:         2026-09-20T05:54:00+00:00
Effective:    2026-09-20T01:54:00+00:00
Expires:      2026-09-20T05:00:00+00:00
Collected:    2026-09-21T20:06:28.361224+00:00
Sender:       NWS Wilmington OH

Description:
FFWILN

The National Weather Service in Wilmington has issued a

* Flash Flood Warning for...
Southwestern Clinton County in southwestern Ohio...
Southern Warren County in southwestern Ohio...

* Until 500 AM EDT.

* At 154 AM EDT, radar indicated thunderstorms producing heavy rain
across the warned area. Between 2 and 3.5 inches of rain have
fallen. Additional rainfall amounts of 0.5 to 1.5 inches are
possible in the warned area. Flash flooding is ongoing or expected
to begin shortly.

HAZARD...Life threatening flash flooding. Thunderstorms producing
flash flooding.

SOURCE...Radar indicated.

IMPACT...Life threatening flash flooding of creeks and streams,
urban areas, highways, streets and underpasses.

* Some locations that may experience flash flooding include...
Mason, Lebanon, Monroe, Loveland, Blanchester, Morrow, Kings
Island, Highpoint, South Lebanon, Maineville, Clarksville, Midland,
Butlerville, Pleasant Plain, State Route 123 at State Route 132,
Middleboro, Fort Ancient, Dallasburg, State Route 350 at US Route
22 and Murdock.


Instructions:
Turn around, don't drown when encountering flooded roads. Most flood
deaths occur in vehicles.

Be especially cautious at night when it is harder to recognize the
dangers of flooding.

To report flash flooding, go to our website at weather.gov/iln and
submit your report via social media, when you can do so safely.

Source URL:   http://www.weather.gov
======================================================================
Source:       FEMA
Event:        Flash Flood Warning
Headline:     Flash Flood Warning issued September 19 at 11:57PM EDT until September 20 at 3:00AM EDT by NWS Wilmington OH
Severity:     Severe
Urgency:      Immediate
Certainty:    Likely
Area:         Hocking, OH; Pickaway, OH; Ross, OH
Sent:         2026-09-20T03:57:00+00:00
Effective:    2026-09-19T23:57:00+00:00
Expires:      2026-09-20T03:00:00+00:00
Collected:    2026-09-21T20:06:28.358901+00:00
Sender:       NWS Wilmington OH

Description:
FFWILN

The National Weather Service in Wilmington has issued a

* Flash Flood Warning for...
Hocking County in central Ohio...
Southeastern Pickaway County in central Ohio...
Northeastern Ross County in south central Ohio...

* Until 300 AM EDT.

* At 1157 PM EDT, radar indicated thunderstorms producing heavy rain
across the warned area. Between 1.5 and 3 inches of rain have
fallen. Additional rainfall amounts of 1 to 2 inches are possible
in the warned area. Flash flooding is ongoing or expected to begin
shortly.

HAZARD...Life threatening flash flooding. Thunderstorms producing
flash flooding.

SOURCE...Radar indicated.

IMPACT...Life threatening flash flooding of creeks and streams,
urban areas, highways, streets and underpasses.

* Some locations that may experience flash flooding include...
Logan, Hocking Hills State Park, Starr, Laurelville, Murray City,
Adelphi, Tarlton, Gibisonville, Lake Logan State Park, Ilesboro,
Enterprise, Rockbridge, South Bloomingville, Union Furnace, Buena
Vista in Hocking County, Haydenville, Oreville, Carbon Hill and
Whisler.


Instructions:
Turn around, don't drown when encountering flooded roads. Most flood
deaths occur in vehicles.

To report flash flooding, go to our website at weather.gov/iln and
submit your report via social media, when you can do so safely.

Source URL:   http://www.weather.gov
======================================================================
Source:       FEMA
Event:        Flash Flood Warning
Headline:     Flash Flood Warning issued September 19 at 8:03PM CDT until September 19 at 10:00PM CDT by NWS Midland/Odessa TX
Severity:     Severe
Urgency:      Immediate
Certainty:    Likely
Area:         Gaines, TX
Sent:         2026-09-20T01:03:00+00:00
Effective:    2026-09-19T20:03:00+00:00
Expires:      2026-09-19T22:00:00+00:00
Collected:    2026-09-21T20:06:28.357233+00:00
Sender:       NWS Midland/Odessa TX

Description:
FFWMAF

The National Weather Service in Midland/Odessa has issued a

* Flash Flood Warning for...
Central Gaines County in western Texas...

* Until 1000 PM CDT.

* At 803 PM CDT, Doppler radar indicated thunderstorms producing
heavy rain across the warned area. Between 1.5 and 2.5 inches of
rain have fallen. The expected rainfall rate is 2 to 3 inches in 1
hour. Flash flooding is ongoing or expected to begin shortly.

HAZARD...Life threatening flash flooding. Thunderstorms producing
flash flooding.

SOURCE...Radar indicated.

IMPACT...Life threatening flash flooding of creeks and streams,
urban areas, highways, streets and underpasses.

* Some locations that will experience flash flooding include...
Seminole, Seagraves, Gaines County Airport, Gaines County Park,
Paynes Corner and Loop.

This includes the following streams and drainages...
Seminole Draw, Wardswell Draw and McKenzie Draw.


Instructions:
Turn around, don't drown when encountering flooded roads. Most flood
deaths occur in vehicles.

Please report observed flooding to local emergency services or law
enforcement and request they pass this information to the National
Weather Service when you can do so safely.

Source URL:   http://www.weather.gov
======================================================================
Source:       FEMA
Event:        Tornado Warning
Headline:     Tornado Warning issued September 19 at 6:36PM MDT until September 19 at 6:45PM MDT by NWS Goodland KS
Severity:     Extreme
Urgency:      Immediate
Certainty:    Observed
Area:         Cheyenne, CO; Wallace, KS
Sent:         2026-09-20T00:36:00+00:00
Effective:    2026-09-19T18:36:00+00:00
Expires:      2026-09-19T18:45:00+00:00
Collected:    2026-09-21T20:06:28.356109+00:00
Sender:       NWS Goodland KS

Description:
TORGLD

The National Weather Service in Goodland has issued a

* Tornado Warning for...
East central Cheyenne County in east central Colorado...
Southwestern Wallace County in west central Kansas...

* Until 645 PM MDT.

* At 635 PM MDT, a severe thunderstorm capable of producing a tornado
was located 4 miles southwest of Weskan, or 15 miles west of Sharon
Springs, moving east at 25 mph.

HAZARD...Tornado and quarter size hail.

SOURCE...Radar indicated rotation.

IMPACT...Flying debris will be dangerous to those caught without
shelter. Mobile homes will be damaged or destroyed.
Damage to roofs, windows, and vehicles will occur.  Tree
damage is likely.

* This dangerous storm will be near...
Weskan around 640 PM MDT.


Instructions:
TAKE COVER NOW! Move to a basement or an interior room on the lowest
floor of a sturdy building. Avoid windows. If you are outdoors, in a
mobile home, or in a vehicle, move to the closest substantial shelter
and protect yourself from flying debris.

Source URL:   http://www.weather.gov
======================================================================
Source:       FEMA
Event:        Flash Flood Warning
Headline:     Flash Flood Warning issued September 19 at 6:19PM MDT until September 19 at 9:15PM MDT by NWS Grand Junction CO
Severity:     Severe
Urgency:      Immediate
Certainty:    Likely
Area:         Garfield, CO
Sent:         2026-09-20T00:19:00+00:00
Effective:    2026-09-19T18:19:00+00:00
Expires:      2026-09-19T21:15:00+00:00
Collected:    2026-09-21T20:06:28.354976+00:00
Sender:       NWS Grand Junction CO

Description:
FFWGJT

The National Weather Service in Grand Junction has issued a

* Flash Flood Warning for...
Western Garfield County in west central Colorado...

* Until 915 PM MDT.

* At 619 PM MDT, Doppler radar indicated thunderstorms producing
heavy rain across the warned area along Highway 139 near and south
of Douglas Pass. Between 0.6 and 0.8 inches of rain have fallen.
The expected rainfall rate is 1 to 3 inches in 1 hour. Flash
flooding is ongoing or expected to begin shortly.

HAZARD...Life threatening flash flooding. Thunderstorms producing
flash flooding.

SOURCE...Radar indicated.

IMPACT...Life threatening flash flooding of creeks and streams,
urban areas, highways, streets and underpasses.

* Some locations that will experience flash flooding include...
Mainly rural areas of Western Garfield County.


Instructions:
Turn around, don't drown when encountering flooded roads. Most flood
deaths occur in vehicles.

Highway 139 near Douglas Pass is prone to rockslides and mudslides in
heavy rain. Stay alert for rocks and debris on roads, and avoid
driving on flooded roads. Find an alternate route.

Source URL:   http://www.weather.gov
======================================================================
Source:       FEMA
Event:        Flash Flood Warning
Headline:     Flash Flood Warning issued September 19 at 6:01PM MDT until September 19 at 9:00PM MDT by NWS Grand Junction CO
Severity:     Severe
Urgency:      Immediate
Certainty:    Likely
Area:         Rio Blanco, CO
Sent:         2026-09-20T00:01:00+00:00
Effective:    2026-09-19T18:01:00+00:00
Expires:      2026-09-19T21:00:00+00:00
Collected:    2026-09-21T20:06:28.353184+00:00
Sender:       NWS Grand Junction CO

Description:
FFWGJT

The National Weather Service in Grand Junction has issued a

* Flash Flood Warning for...
The Lee burn scar in...
Central Rio Blanco County in northwestern Colorado...

* Until 900 PM MDT.

* At 601 PM MDT, Doppler radar indicated thunderstorms producing
heavy rain over the Lee Burn Scar. Between 0.3 and 0.5 inches of
rain have fallen. The expected rainfall rate is 1 to 3 inches in 1
hour. Flash flooding is ongoing or expected to begin shortly.
Excessive rainfall over the burn scar will result in debris flow.
The debris flow can consist of rock, mud, vegetation and other
loose materials.

HAZARD...Life threatening flash flooding. Thunderstorms producing
flash flooding in and around the Lee Burn Scar.

SOURCE...Radar indicated.

IMPACT...Life threatening flash flooding of areas in and around the
Lee Burn Scar.

* Some locations that will experience flash flooding include...
Mainly rural areas of Central Rio Blanco County.


Instructions:
This is a life threatening situation. Heavy rainfall will cause
extensive and severe flash flooding of creeks...streams...and ditches
in the Lee Burn Scar. Severe debris flows can also be anticipated
across roads. Roads and driveways may be washed away in places. If
you encounter flood waters...climb to safety.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 2:43AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Gravel Point to Cape Cleare out to 15 NM
Sent:         2026-09-20T02:43:00-08:00
Effective:    2026-09-20T02:43:00-08:00
Expires:      2026-09-20T15:30:00-08:00
Collected:    2026-09-21T20:06:27.297436+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for the Northern Gulf of Alaska Coast
up to 100 nm out including Kodiak Island and Cook Inlet.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...E wind 30 kt becoming N 20 kt by late afternoon. Seas 11
ft. Rain showers. Isolated thunderstorms.
.TONIGHT...W wind 15 kt in the evening becoming SW. Seas 9 ft.
Isolated thunderstorms.
.MON...S wind 20 kt. Seas 8 ft. Rain showers.
.MON NIGHT...SE wind 15 kt. Seas 7 ft.
.TUE...NE wind 20 kt. Seas 7 ft.
.WED...E wind 15 kt. Seas 6 ft.
.THU...SE wind 25 kt. Seas 4 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 2:43AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Cape Suckling to Cape Cleare from 15 to 75 NM
Sent:         2026-09-20T02:43:00-08:00
Effective:    2026-09-20T02:43:00-08:00
Expires:      2026-09-20T15:30:00-08:00
Collected:    2026-09-21T20:06:27.297045+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for the Northern Gulf of Alaska Coast
up to 100 nm out including Kodiak Island and Cook Inlet.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...E wind 30 kt becoming W 30 kt in the afternoon. Seas 14 ft.
Rain showers. Isolated thunderstorms.
.TONIGHT...SW wind 20 kt. Seas 11 ft. Rain showers. Isolated
thunderstorms.
.MON...SW wind 20 kt. Seas 10 ft.
.MON NIGHT...SE wind 15 kt. Seas 8 ft.
.TUE...E wind 30 kt. Seas 10 ft.
.WED...E wind 20 kt. Seas 8 ft.
.THU...SE wind 25 kt. Seas 5 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 2:43AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Cape Suckling to Gravel Point out to 15 NM
Sent:         2026-09-20T02:43:00-08:00
Effective:    2026-09-20T02:43:00-08:00
Expires:      2026-09-20T15:30:00-08:00
Collected:    2026-09-21T20:06:27.296650+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for the Northern Gulf of Alaska Coast
up to 100 nm out including Kodiak Island and Cook Inlet.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...E wind 35 kt becoming S by late this afternoon. Seas 12 ft.
Rain showers. Isolated thunderstorms.
.TONIGHT...S wind 25 kt diminishing to 15 kt after midnight. Seas
10 ft. Rain showers. Isolated thunderstorms.
.MON...S wind 15 kt. Seas 9 ft. Rain showers.
.MON NIGHT...SE wind 15 kt. Seas 7 ft.
.TUE...NE wind 25 kt. Seas 8 ft.
.WED...E wind 20 kt. Seas 6 ft.
.THU...E wind 25 kt. Seas 4 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 2:43AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Cape Cleare to Gore Point from 15 to 75 NM
Sent:         2026-09-20T02:43:00-08:00
Effective:    2026-09-20T02:43:00-08:00
Expires:      2026-09-20T15:30:00-08:00
Collected:    2026-09-21T20:06:27.296262+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for the Northern Gulf of Alaska Coast
up to 100 nm out including Kodiak Island and Cook Inlet.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...NE wind 25 kt becoming NW 20 kt by late afternoon. Seas 11
ft. Rain showers. Isolated thunderstorms.
.TONIGHT...W wind 20 kt. Seas 8 ft.
.MON...SW wind 20 kt. Seas 8 ft.
.MON NIGHT...SE wind 15 kt. Seas 7 ft.
.TUE...NE wind 25 kt. Seas 9 ft.
.WED...NE wind 15 kt. Seas 7 ft.
.THU...SE wind 25 kt. Seas 5 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 3:28AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Port Heiden to Nelson Lagoon from 15 to 60 NM
Sent:         2026-09-20T03:28:00-08:00
Effective:    2026-09-20T03:28:00-08:00
Expires:      2026-09-20T16:00:00-08:00
Collected:    2026-09-21T20:06:27.295862+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for Southwest Alaska+Bristol Bay+The
Alaska Peninsula Waters and the Aleutian Islands up to 100 nm out.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...NW wind 30 kt. Seas 10 ft. Rain showers. Isolated
thunderstorms.
.TONIGHT...NW wind 30 kt. Seas 11 ft. Rain showers.
.MON...NW wind 30 kt. Seas 10 ft.
.MON NIGHT...NW wind 20 kt. Seas 7 ft.
.TUE...NW wind 15 kt. Seas 5 ft.
.WED...SE wind 35 kt. Seas 7 ft.
.THU...S wind 35 kt. Seas 12 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 3:28AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Nelson Lagoon to Cape Sarichef out to 15 NM
Sent:         2026-09-20T03:28:00-08:00
Effective:    2026-09-20T03:28:00-08:00
Expires:      2026-09-20T16:00:00-08:00
Collected:    2026-09-21T20:06:27.295364+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for Southwest Alaska+Bristol Bay+The
Alaska Peninsula Waters and the Aleutian Islands up to 100 nm out.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...NW wind 30 kt. Seas 9 ft. Widespread rain showers. Isolated
thunderstorms.
.TONIGHT...NW wind 30 kt. Seas 10 ft. Rain showers.
.MON...NW wind 25 kt. Seas 9 ft. Rain showers.
.MON NIGHT...NW wind 20 kt. Seas 6 ft.
.TUE...W wind 15 kt. Seas 5 ft.
.WED...SE wind 40 kt. Seas 5 ft.
.THU...S wind 40 kt. Seas 13 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 3:28AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Cape Tolstoi to Cape Sarichef out to 15 NM
Sent:         2026-09-20T03:28:00-08:00
Effective:    2026-09-20T03:28:00-08:00
Expires:      2026-09-20T16:00:00-08:00
Collected:    2026-09-21T20:06:27.294899+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for Southwest Alaska+Bristol Bay+The
Alaska Peninsula Waters and the Aleutian Islands up to 100 nm out.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...NW wind 25 kt. Seas 3 ft. Isolated
thunderstorms.
.TONIGHT...NW wind 25 kt. Seas 3 ft.
.MON...NW wind 25 kt. Seas 3 ft.
.MON NIGHT...NW wind 20 kt. Seas 3 ft.
.TUE...W wind 15 kt. Seas 3 ft.
.WED...S wind 40 kt. Seas 10 ft.
.THU...S wind 40 kt. Seas 14 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 3:28AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Nelson Lagoon to Unalga Pass from 15 to 70 NM
Sent:         2026-09-20T03:28:00-08:00
Effective:    2026-09-20T03:28:00-08:00
Expires:      2026-09-20T16:00:00-08:00
Collected:    2026-09-21T20:06:27.294492+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for Southwest Alaska+Bristol Bay+The
Alaska Peninsula Waters and the Aleutian Islands up to 100 nm out.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...NW wind 30 kt. Seas 10 ft. Rain showers. Isolated
thunderstorms.
.TONIGHT...NW wind 30 kt. Seas 10 ft.
.MON...NW wind 25 kt. Seas 9 ft.
.MON NIGHT...NW wind 20 kt. Seas 6 ft.
.TUE...SW wind 20 kt. Seas 5 ft.
.WED...SE wind 35 kt. Seas 12 ft.
.THU...S wind 35 kt. Seas 20 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 3:28AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Port Heiden to Nelson Lagoon out to 15 NM
Sent:         2026-09-20T03:28:00-08:00
Effective:    2026-09-20T03:28:00-08:00
Expires:      2026-09-20T16:00:00-08:00
Collected:    2026-09-21T20:06:27.294090+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for Southwest Alaska+Bristol Bay+The
Alaska Peninsula Waters and the Aleutian Islands up to 100 nm out.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...NW wind 30 kt. Seas 10 ft. Widespread rain showers. Isolated
thunderstorms.
.TONIGHT...NW wind 30 kt. Seas 11 ft. Widespread rain showers.
.MON...NW wind 25 kt. Seas 10 ft. Rain showers.
.MON NIGHT...NW wind 20 kt. Seas 7 ft.
.TUE...NW wind 15 kt. Seas 5 ft.
.WED...SE wind 30 kt. Seas 3 ft.
.THU...S wind 30 kt. Seas 7 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Gale Warning
Headline:     Gale Warning issued September 20 at 3:28AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Moderate
Urgency:      Expected
Certainty:    Likely
Area:         Castle Cape to Cape Tolstoi from 15 to 100 NM
Sent:         2026-09-20T03:28:00-08:00
Effective:    2026-09-20T03:28:00-08:00
Expires:      2026-09-20T16:00:00-08:00
Collected:    2026-09-21T20:06:27.293737+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for Southwest Alaska+Bristol Bay+The
Alaska Peninsula Waters and the Aleutian Islands up to 100 nm out.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...NW wind 35 kt. Seas 12 ft. Isolated
thunderstorms.
.TONIGHT...NW wind 35 kt. Seas 10 ft. Rain showers.
.MON...NW wind 35 kt. Seas 10 ft.
.MON NIGHT...NW wind 30 kt. Seas 9 ft.
.TUE...NW wind 25 kt. Seas 7 ft.
.WED...S wind 30 kt. Seas 8 ft.
.THU...S wind 30 kt. Seas 14 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Gale Warning
Headline:     Gale Warning issued September 20 at 3:28AM AKDT until September 21 at 5:00PM AKDT by NWS Anchorage AK
Severity:     Moderate
Urgency:      Expected
Certainty:    Likely
Area:         Sitkinak to Castle Cape from 15 to 100 NM
Sent:         2026-09-20T03:28:00-08:00
Effective:    2026-09-20T03:28:00-08:00
Expires:      2026-09-20T16:00:00-08:00
Collected:    2026-09-21T20:06:27.293356+00:00
Sender:       NWS Anchorage AK

Description:
Coastal Waters Forecast for Southwest Alaska+Bristol Bay+The
Alaska Peninsula Waters and the Aleutian Islands up to 100 nm out.

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent an average of the highest
one-third of the combined wind wave and swell height.

.TODAY...NW wind 35 kt. Seas 13 ft.
.TONIGHT...W wind 30 kt. Seas 12 ft. Rain showers. Isolated
thunderstorms in the evening.
.MON...NW wind 35 kt. Seas 10 ft.
.MON NIGHT...NW wind 30 kt. Seas 10 ft.
.TUE...NW wind 30 kt. Seas 9 ft.
.WED...SW wind 25 kt. Seas 6 ft.
.THU...S wind 30 kt. Seas 15 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 3:55AM AKDT until September 21 at 5:00PM AKDT by NWS Juneau AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Yakutat Bay
Sent:         2026-09-20T03:55:00-08:00
Effective:    2026-09-20T03:55:00-08:00
Expires:      2026-09-20T22:00:00-08:00
Collected:    2026-09-21T20:06:27.293017+00:00
Sender:       NWS Juneau AK

Description:
Coastal Waters Forecast for Yakutat Bay

Wind forecasts reflect the predominant speed and direction
expected. Sea forecasts represent the average of the highest
one-third of the combined windwave and swell height.

.TODAY...SE wind 25 kt. Seas 10 ft building to 17 ft. Patchy fog.
Slight chance of thunderstorms early in the morning. Showers.
Chance of thunderstorms.
.TONIGHT...SE wind 25 kt. Seas 14 ft. SW swell in the evening.
Patchy fog in the evening. Chance of thunderstorms in the
evening. Showers. Slight chance of thunderstorms late.
.MON...S wind 15 kt. Seas 10 ft. Slight chance of
thunderstorms in the morning. Showers.
.MON NIGHT...E wind 10 kt. Seas 8 ft.
.TUE...NE wind 15 kt. Seas 7 ft.
.WED...NE wind 15 kt. Seas 8 ft.
.THU...NE wind 10 kt. Seas 4 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 3:56AM AKDT until September 21 at 5:00PM AKDT by NWS Juneau AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Cape Decision to Cape Edgecumbe out to 15 NM
Sent:         2026-09-20T03:56:00-08:00
Effective:    2026-09-20T03:56:00-08:00
Expires:      2026-09-20T22:00:00-08:00
Collected:    2026-09-21T20:06:27.292724+00:00
Sender:       NWS Juneau AK

Description:
Southeast Alaska Coastal Waters from Dixon Entrance to
Cape Suckling out 100 NM

Wind forecasts reflect the predominant speed and direction
expected. Seas forecasts represent the average of the highest
one-third of the combined windwave and swell height.

.TODAY...S wind 25 kt. Seas 12 ft building to 18 ft. Slight
chance of thunderstorms. Showers.
.TONIGHT...S wind 20 kt. Seas 15 ft. SW swell in the evening.
Slight chance of thunderstorms. Showers late.
.MON...S wind 10 kt. Seas 10 ft. Showers in the morning.
Slight chance of thunderstorms.
.MON NIGHT...SE wind 20 kt. Seas 8 ft. SW swell. Slight chance
of thunderstorms.
.TUE...SE wind 25 kt. Seas 12 ft.
.WED...SE wind 20 kt. Seas 10 ft.
.THU...E wind 15 kt. Seas 7 ft.

Source URL:   http://www.weather.gov
======================================================================
Source:       NWS
Event:        Small Craft Advisory
Headline:     Small Craft Advisory issued September 20 at 3:56AM AKDT until September 21 at 5:00PM AKDT by NWS Juneau AK
Severity:     Minor
Urgency:      Expected
Certainty:    Likely
Area:         Dixon Entrance to Cape Decision out to 15 NM
Sent:         2026-09-20T03:56:00-08:00
Effective:    2026-09-20T03:56:00-08:00
Expires:      2026-09-20T22:00:00-08:00
Collected:    2026-09-21T20:06:27.292435+00:00
Sender:       NWS Juneau AK

Description:
Southeast Alaska Coastal Waters from Dixon Entrance to
Cape Suckling out 100 NM

Wind forecasts reflect the predominant speed and direction
expected. Seas forecasts represent the average of the highest
one-third of the combined windwave and swell height.

.TODAY...S wind 25 kt. Seas 14 ft. Patchy fog early in the
morning. Slight chance of thunderstorms. Showers in the
afternoon.
.TONIGHT...S wind 20 kt. Seas 14 ft. Slight chance of
thunderstorms. Showers late.
.MON...S wind 10 kt. Seas 10 ft. Showers in the morning.
Slight chance of thunderstorms. Showers in the afternoon.
.MON NIGHT...S wind 20 kt. Seas 9 ft. Showers and slight
chance of thunderstorms.
.TUE...S wind 25 kt. Seas 11 ft.
.WED...SE wind 20 kt. Seas 9 ft.
.THU...SE wind 15 kt. Seas 8 ft.

Source URL:   http://www.weather.gov
======================================================================
