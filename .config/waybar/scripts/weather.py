#!/usr/bin/env python

import json
import os
import sys
import requests
from datetime import datetime

# Last good reading, so a wifi blip does not blank the pill.
#
# waybar hides a custom module whose text is empty, and this script had no
# error handling at all: any network failure raised, the script died before
# printing, and the pill VANISHED until the next run -- up to restart-interval
# (300s) later. waybar's stderr goes to /dev/null, so the traceback was
# invisible too. That is now also more likely to be hit, because closing a
# media player reloads the bar and re-runs this.
CACHE = os.path.join(
    os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache')),
    'waybar-weather.json')


def emit_cached_and_exit():
    """Print the last good reading, marked stale. Exit silently if there is
    none yet, which hides the module exactly as before."""
    try:
        with open(CACHE, encoding='utf-8') as f:
            cached = json.load(f)
    except Exception:
        sys.exit(0)
    cached['tooltip'] = ("<b>⚠ offline — last known reading</b>\n"
                         + cached.get('tooltip', ''))
    print(json.dumps(cached))
    sys.exit(0)

WEATHER_CODES = {
    '113': '🌈',
    '116': '⛅️',
    '119': '☁️',
    '122': '☁️',
    '143': '🌫',
    '176': '🌦',
    '179': '🌧',
    '182': '🌧',
    '185': '🌧',
    '200': '⛈',
    '227': '🌨',
    '230': '❄️',
    '248': '🌫',
    '260': '🌫',
    '263': '🌦',
    '266': '🌦',
    '281': '🌧',
    '284': '🌧',
    '293': '🌦',
    '296': '🌦',
    '299': '🌧',
    '302': '🌧',
    '305': '🌧',
    '308': '🌧',
    '311': '🌧',
    '314': '🌧',
    '317': '🌧',
    '320': '🌨',
    '323': '🌨',
    '326': '🌨',
    '329': '❄️',
    '332': '❄️',
    '335': '❄️',
    '338': '❄️',
    '350': '🌧',
    '353': '🌦',
    '356': '🌧',
    '359': '🌧',
    '362': '🌧',
    '365': '🌧',
    '368': '🌨',
    '371': '❄️',
    '374': '🌧',
    '377': '🌧',
    '386': '⛈',
    '389': '🌩',
    '392': '⛈',
    '395': '❄️'
}

data = {}


# timeout is essential, not defensive: without one, requests.get can hang on
# a half-open connection indefinitely and this script never returns at all.
try:
    weather = requests.get("https://wttr.in/?format=j1", timeout=10).json()
except Exception:
    emit_cached_and_exit()


def format_time(time):
    return time.replace("00", "").zfill(2)


def format_temp(temp):
    return (hour['FeelsLikeC']+"°").ljust(3)


def format_chances(hour):
    chances = {
        "chanceoffog": "Fog",
        "chanceoffrost": "Frost",
        "chanceofovercast": "Overcast",
        "chanceofrain": "Rain",
        "chanceofsnow": "Snow",
        "chanceofsunshine": "Sunshine",
        "chanceofthunder": "Thunder",
        "chanceofwindy": "Wind"
    }

    conditions = []
    for event in chances.keys():
        if int(hour[event]) > 0:
            conditions.append(chances[event]+" "+hour[event]+"%")
    return ", ".join(conditions)


# The pill shows the ACTUAL temperature, not FeelsLikeC. Those differ by
# several degrees often enough that the bar read colder than every other
# thermometer -- 18 against a real 22 on the day this was changed. Feels-like
# is still in the tooltip, on the line below the header.
data['text'] = WEATHER_CODES[weather['current_condition'][0]['weatherCode']] + \
    " "+weather['current_condition'][0]['temp_C']+"°"

data['tooltip'] = f"<b>{weather['current_condition'][0]['weatherDesc'][0]['value']} {weather['current_condition'][0]['temp_C']}°C</b>\n"
data['tooltip'] += f"Feels like: {weather['current_condition'][0]['FeelsLikeC']}°C\n"
data['tooltip'] += f"Wind: {weather['current_condition'][0]['windspeedKmph']}Km/h\n"
data['tooltip'] += f"Humidity: {weather['current_condition'][0]['humidity']}%\n"
for i, day in enumerate(weather['weather']):
    data['tooltip'] += f"\n<b>"
    if i == 0:
        data['tooltip'] += "Today, "
    if i == 1:
        data['tooltip'] += "Tomorrow, "
    data['tooltip'] += f"{day['date']}</b>\n"
    data['tooltip'] += f"⬆️ {day['maxtempC']}° ⬇️ {day['mintempC']}° "
    data['tooltip'] += f"🌅 {day['astronomy'][0]['sunrise']} 🌇 {day['astronomy'][0]['sunset']}\n"
    for hour in day['hourly']:
        if i == 0:
            if int(format_time(hour['time'])) < datetime.now().hour-2:
                continue
        data['tooltip'] += f"{format_time(hour['time'])} {WEATHER_CODES[hour['weatherCode']]} {format_temp(hour['FeelsLikeC'])} {hour['weatherDesc'][0]['value']}, {format_chances(hour)}\n"


# Save before printing, so the next failure has something to fall back on.
try:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(data, f)
except Exception:
    pass          # a cache we cannot write is not worth failing the pill over

print(json.dumps(data))

