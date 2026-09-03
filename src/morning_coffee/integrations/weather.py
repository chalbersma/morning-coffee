"""Weather integration: a 7-day forecast for a postal code.

No API keys required. Postal code -> lat/lon via zippopotam.us, then a daily
forecast from Open-Meteo. WMO weather codes are mapped to a description + emoji.
Each day becomes one ``FeedItem``.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx

from ..models import FeedItem
from .base import Integration

GEOCODE_URL = "https://api.zippopotam.us/{country}/{postal_code}"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO 4677 weather codes -> (description, emoji). Missing codes fall back below.
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Moderate drizzle", "🌦️"),
    55: ("Dense drizzle", "🌦️"),
    56: ("Freezing drizzle", "🌧️"),
    57: ("Dense freezing drizzle", "🌧️"),
    61: ("Slight rain", "🌧️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"),
    67: ("Heavy freezing rain", "🌧️"),
    71: ("Slight snow", "🌨️"),
    73: ("Moderate snow", "🌨️"),
    75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "🌨️"),
    80: ("Slight rain showers", "🌦️"),
    81: ("Moderate rain showers", "🌦️"),
    82: ("Violent rain showers", "⛈️"),
    85: ("Slight snow showers", "🌨️"),
    86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with slight hail", "⛈️"),
    99: ("Thunderstorm with heavy hail", "⛈️"),
}


def describe_weather(code: int | None) -> tuple[str, str]:
    """Map a WMO weather code to (description, emoji), with a default."""
    if code is None:
        return ("Unknown", "❓")
    return WMO_CODES.get(int(code), ("Unknown", "❓"))


class WeatherIntegration(Integration):
    name = "Weather"
    config_key = "weather"

    def _location(self) -> dict:
        # Location may be nested (merged by Config) or flattened into settings.
        loc = self.settings.get("location") or {}
        return {
            "postal_code": self.settings.get("postal_code") or loc.get("postal_code"),
            "country": (self.settings.get("country") or loc.get("country") or "us"),
            "units": (self.settings.get("units") or loc.get("units") or "fahrenheit"),
        }

    def _geocode(self, client: httpx.Client, country: str, postal_code: str) -> tuple[float, float, str]:
        url = GEOCODE_URL.format(country=country.lower(), postal_code=postal_code)
        resp = client.get(url)
        if resp.status_code == 404:
            raise RuntimeError(f"Unknown postal code {postal_code!r} for country {country!r}")
        resp.raise_for_status()
        data = resp.json()
        places = data.get("places") or []
        if not places:
            raise RuntimeError(f"No location found for {postal_code!r}")
        place = places[0]
        name = place.get("place name") or ""
        return float(place["latitude"]), float(place["longitude"]), name

    def _forecast(self, client: httpx.Client, lat: float, lon: float, units: str, days: int) -> dict:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": days,
            "temperature_unit": "fahrenheit" if units == "fahrenheit" else "celsius",
        }
        resp = client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    def fetch(self) -> list[FeedItem]:
        self._error = None
        loc = self._location()
        if not loc["postal_code"]:
            self._error = "location.postal_code is not configured"
            return []

        days = int(self.settings.get("forecast_days", 7))
        unit_symbol = "°F" if loc["units"] == "fahrenheit" else "°C"
        try:
            with httpx.Client(timeout=15.0) as client:
                lat, lon, place = self._geocode(client, loc["country"], str(loc["postal_code"]))
                data = self._forecast(client, lat, lon, loc["units"], days)
        except Exception as exc:  # noqa: BLE001 - surface any failure in the panel
            self._error = str(exc)
            return []

        daily = data.get("daily") or {}
        times = daily.get("time") or []
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        codes = daily.get("weather_code") or []
        pops = daily.get("precipitation_probability_max") or []

        items: list[FeedItem] = []
        for i, iso in enumerate(times):
            try:
                day = date.fromisoformat(iso)
                day_label = day.strftime("%a %b %-d")
                ts = datetime.combine(day, datetime.min.time())
            except ValueError:
                day_label, ts = iso, None

            hi = highs[i] if i < len(highs) else None
            lo = lows[i] if i < len(lows) else None
            desc, emoji = describe_weather(codes[i] if i < len(codes) else None)
            pop = pops[i] if i < len(pops) else None

            temp = f"{round(hi)}{unit_symbol} / {round(lo)}{unit_symbol}" if hi is not None and lo is not None else ""
            title = f"{emoji} {day_label}  {temp}".strip()
            subtitle = desc
            if pop is not None:
                subtitle += f" · {pop}% precip"

            items.append(
                FeedItem(
                    title=title,
                    subtitle=subtitle,
                    timestamp=ts,
                    source=f"{self.name} ({place})" if i == 0 and place else self.name,
                    meta={"weather_code": codes[i] if i < len(codes) else None},
                )
            )
        return items
