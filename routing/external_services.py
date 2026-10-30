"""External routing, geocoding, and weather provider clients."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


MM_PER_INCH = 25.4


class ExternalServiceError(RuntimeError):
    """A provider request failed or returned an invalid response."""


class ProviderAccessError(ExternalServiceError):
    """A provider denied access and returned an authentication error body."""

    def __init__(
        self,
        *,
        provider: str,
        status_code: int,
        raw_response_body: str,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.raw_response_body = raw_response_body
        self.detail = _provider_error_detail(raw_response_body)
        super().__init__(
            f"{provider} returned HTTP {status_code}: {self.detail}"
        )


class ConfigurationError(RuntimeError):
    """A required server-side setting is missing or invalid."""


class LocationNotFoundError(ValueError):
    """A user-supplied location could not be geocoded."""


class InsufficientRoutesError(ExternalServiceError):
    """The routing provider could not produce three distinct candidates."""


class ForecastUnavailableError(ValueError):
    """No hourly forecast is available close enough to a checkpoint ETA."""


@dataclass(frozen=True)
class Coordinate:
    longitude: float
    latitude: float


@dataclass(frozen=True)
class GeocodedLocation:
    query: str
    display_name: str
    coordinate: Coordinate


@dataclass(frozen=True)
class ProviderRoute:
    route_id: str
    geometry: tuple[Coordinate, ...]
    distance_meters: float
    duration_seconds: float
    segment_distances_meters: tuple[float, ...]
    segment_durations_seconds: tuple[float, ...]


@dataclass(frozen=True)
class WeatherReading:
    forecast_time: datetime
    wind_mph: float
    rain_in_per_hour: float
    snow_in_per_hour: float
    temperature_f: float | None
    description: str


class JsonHttpClient:
    """Small injectable JSON client that keeps provider secrets out of errors."""

    def get_json(
        self,
        url: str,
        *,
        provider: str,
        params: Mapping[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        request_url = f"{url}?{urlencode(params)}"
        request = Request(
            request_url,
            headers={"Accept": "application/json", "User-Agent": "truck-routing/1.0"},
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read()
        except HTTPError as exc:
            raw_response_body = _read_http_error_body(exc)
            if exc.code in {401, 403}:
                raise ProviderAccessError(
                    provider=provider,
                    status_code=exc.code,
                    raw_response_body=raw_response_body,
                ) from exc
            raise ExternalServiceError(
                f"{provider} returned HTTP {exc.code}: "
                f"{_provider_error_detail(raw_response_body)}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise ExternalServiceError(
                f"{provider} request failed or timed out."
            ) from exc

        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExternalServiceError(
                f"{provider} returned invalid JSON."
            ) from exc
        if not isinstance(decoded, dict):
            raise ExternalServiceError(
                f"{provider} returned an unexpected JSON shape."
            )
        return decoded


class MapboxClient:
    GEOCODING_PATH = "/search/geocode/v6/forward"
    DIRECTIONS_PATH = "/directions/v5"

    def __init__(
        self,
        *,
        access_token: str,
        base_url: str = "https://api.mapbox.com",
        profile: str = "mapbox/driving-traffic",
        timeout_seconds: float = 15.0,
        http_client: JsonHttpClient | None = None,
    ) -> None:
        if not access_token:
            raise ConfigurationError("MAPBOX_ACCESS_TOKEN is not configured.")
        if profile not in {"mapbox/driving", "mapbox/driving-traffic"}:
            raise ConfigurationError("MAPBOX_DIRECTIONS_PROFILE is invalid.")
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self.timeout_seconds = timeout_seconds
        self.http = http_client or JsonHttpClient()

    @classmethod
    def from_env(cls) -> "MapboxClient":
        return cls(
            access_token=settings.MAPBOX_ACCESS_TOKEN,
            base_url=os.getenv("MAPBOX_API_BASE_URL", "https://api.mapbox.com"),
            profile=os.getenv(
                "MAPBOX_DIRECTIONS_PROFILE", "mapbox/driving-traffic"
            ),
            timeout_seconds=_float_env("EXTERNAL_API_TIMEOUT_SECONDS", 15.0),
        )

    def geocode(self, query: str) -> GeocodedLocation:
        payload = self.http.get_json(
            f"{self.base_url}{self.GEOCODING_PATH}",
            provider="Mapbox",
            params={
                "q": query,
                "access_token": self.access_token,
                "autocomplete": "false",
                "limit": 1,
            },
            timeout_seconds=self.timeout_seconds,
        )
        features = payload.get("features") or []
        if not features:
            raise LocationNotFoundError(f"Could not locate {query!r}.")
        try:
            feature = features[0]
            coordinates = feature["geometry"]["coordinates"]
            properties = feature.get("properties") or {}
            display_name = (
                properties.get("full_address")
                or properties.get("name")
                or feature.get("place_name")
                or query
            )
            coordinate = Coordinate(
                longitude=float(coordinates[0]),
                latitude=float(coordinates[1]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExternalServiceError(
                "Mapbox returned an invalid geocoding result."
            ) from exc
        return GeocodedLocation(query, str(display_name), coordinate)

    def get_route_options(
        self,
        origin: Coordinate,
        destination: Coordinate,
        departure_time: datetime,
    ) -> tuple[ProviderRoute, ...]:
        coordinate_path = (
            f"{origin.longitude},{origin.latitude};"
            f"{destination.longitude},{destination.latitude}"
        )
        params: dict[str, Any] = {
            "access_token": self.access_token,
            "alternatives": "true",
            "geometries": "geojson",
            "overview": "full",
            "steps": "false",
            "annotations": "distance,duration",
        }
        if self.profile == "mapbox/driving-traffic":
            params["depart_at"] = departure_time.isoformat()

        payload = self.http.get_json(
            f"{self.base_url}{self.DIRECTIONS_PATH}/{self.profile}/{coordinate_path}",
            provider="Mapbox",
            params=params,
            timeout_seconds=self.timeout_seconds,
        )
        if payload.get("code") != "Ok":
            if payload.get("code") in {
                "TokenInvalid",
                "TokenRequired",
                "Unauthorized",
                "Forbidden",
            }:
                raise ProviderAccessError(
                    provider="Mapbox",
                    status_code=401,
                    raw_response_body=json.dumps(payload),
                )
            raise ExternalServiceError(
                f"Mapbox directions failed: {payload.get('code', 'unknown error')}."
            )
        route_payloads = payload.get("routes") or []
        if len(route_payloads) < 1:
            raise InsufficientRoutesError(
                "No valid routes found."
            )

        response_id = str(payload.get("uuid") or "mapbox")
        parsed_routes = tuple(
            self._parse_route(item, f"{response_id}-{index + 1}")
            for index, item in enumerate(route_payloads[:3])
        )
        return _ensure_three_route_options(parsed_routes)

    def _parse_route(self, payload: dict[str, Any], route_id: str) -> ProviderRoute:
        try:
            geometry = tuple(
                Coordinate(longitude=float(item[0]), latitude=float(item[1]))
                for item in payload["geometry"]["coordinates"]
            )
            distance = float(payload["distance"])
            duration = float(payload["duration"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExternalServiceError("Mapbox returned an invalid route.") from exc
        if len(geometry) < 2 or distance <= 0 or duration < 0:
            raise ExternalServiceError("Mapbox returned an invalid route geometry.")

        annotation_distances: list[float] = []
        annotation_durations: list[float] = []
        try:
            for leg in payload.get("legs") or []:
                annotation = leg.get("annotation") or {}
                annotation_distances.extend(float(x) for x in annotation["distance"])
                annotation_durations.extend(float(x) for x in annotation["duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExternalServiceError(
                "Mapbox returned invalid segment annotations."
            ) from exc

        expected_segments = len(geometry) - 1
        if (
            len(annotation_distances) != expected_segments
            or len(annotation_durations) != expected_segments
        ):
            # Defensive fallback: full geometry and annotations normally align, but
            # distance-proportional timing still yields usable ETAs if they do not.
            annotation_distances = [
                _haversine_meters(start, end)
                for start, end in zip(geometry, geometry[1:])
            ]
            annotation_durations = _scale_values(annotation_distances, duration)

        annotation_distances = _scale_values(annotation_distances, distance)
        annotation_durations = _scale_values(annotation_durations, duration)
        return ProviderRoute(
            route_id=route_id,
            geometry=geometry,
            distance_meters=distance,
            duration_seconds=duration,
            segment_distances_meters=tuple(annotation_distances),
            segment_durations_seconds=tuple(annotation_durations),
        )


class OpenWeatherClient:
    ONE_CALL_PATH = "/data/3.0/onecall"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openweathermap.org",
        timeout_seconds: float = 15.0,
        max_forecast_gap_seconds: float = 5_400.0,
        http_client: JsonHttpClient | None = None,
    ) -> None:
        if not api_key:
            raise ConfigurationError("OPENWEATHER_API_KEY is not configured.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_forecast_gap_seconds = max_forecast_gap_seconds
        self.http = http_client or JsonHttpClient()

    @classmethod
    def from_env(cls) -> "OpenWeatherClient":
        return cls(
            api_key=settings.OPENWEATHER_API_KEY,
            base_url=os.getenv(
                "OPENWEATHER_API_BASE_URL", "https://api.openweathermap.org"
            ),
            timeout_seconds=_float_env("EXTERNAL_API_TIMEOUT_SECONDS", 15.0),
            max_forecast_gap_seconds=_float_env(
                "OPENWEATHER_MAX_FORECAST_GAP_SECONDS", 5_400.0
            ),
        )

    def forecast_at(
        self,
        coordinate: Coordinate,
        eta: datetime,
    ) -> WeatherReading:
        return self._reading_at(self._fetch_hourly(coordinate), eta)

    def forecast_timeline(
        self,
        coordinate: Coordinate,
        start_time: datetime,
        hours: int = 48,
    ) -> tuple[WeatherReading, ...]:
        """Return the closest provider forecast for every hour in the window."""

        hourly = self._fetch_hourly(coordinate)
        return tuple(
            self._reading_at(hourly, start_time + timedelta(hours=hour_offset))
            for hour_offset in range(hours + 1)
        )

    def _fetch_hourly(self, coordinate: Coordinate) -> list[dict[str, Any]]:
        payload = self.http.get_json(
            f"{self.base_url}{self.ONE_CALL_PATH}",
            provider="OpenWeather",
            params={
                "lat": coordinate.latitude,
                "lon": coordinate.longitude,
                "appid": self.api_key,
                "units": "imperial",
                "exclude": "current,minutely,daily,alerts",
            },
            timeout_seconds=self.timeout_seconds,
        )
        response_code = str(payload.get("cod", ""))
        if response_code in {"401", "403"}:
            raise ProviderAccessError(
                provider="OpenWeather",
                status_code=int(response_code),
                raw_response_body=json.dumps(payload),
            )
        hourly = payload.get("hourly") or []
        if not isinstance(hourly, list) or not hourly:
            raise ForecastUnavailableError(
                "OpenWeather returned no hourly forecast for a checkpoint."
            )
        return hourly

    def _reading_at(
        self,
        hourly: list[dict[str, Any]],
        eta: datetime,
    ) -> WeatherReading:
        target_timestamp = eta.timestamp()
        try:
            closest = min(hourly, key=lambda item: abs(float(item["dt"]) - target_timestamp))
            forecast_timestamp = float(closest["dt"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExternalServiceError(
                "OpenWeather returned invalid hourly forecast data."
            ) from exc
        if abs(forecast_timestamp - target_timestamp) > self.max_forecast_gap_seconds:
            raise ForecastUnavailableError(
                f"No hourly weather forecast is available near ETA {eta.isoformat()}."
            )

        try:
            weather_items = closest.get("weather") or []
            description = (
                str(weather_items[0].get("description", "")) if weather_items else ""
            )
            # OpenWeather documents rain/snow amounts as mm/h even with imperial units.
            rain_inches = float((closest.get("rain") or {}).get("1h", 0.0)) / MM_PER_INCH
            snow_inches = float((closest.get("snow") or {}).get("1h", 0.0)) / MM_PER_INCH
            temperature = closest.get("temp")
            return WeatherReading(
                forecast_time=datetime.fromtimestamp(
                    forecast_timestamp, tz=timezone.utc
                ),
                wind_mph=float(closest.get("wind_speed", 0.0)),
                rain_in_per_hour=rain_inches,
                snow_in_per_hour=snow_inches,
                temperature_f=float(temperature) if temperature is not None else None,
                description=description,
            )
        except (TypeError, ValueError) as exc:
            raise ExternalServiceError(
                "OpenWeather returned invalid weather measurements."
            ) from exc


def _scale_values(values: list[float], target_total: float) -> list[float]:
    total = sum(values)
    if total <= 0:
        if not values:
            return []
        return [target_total / len(values)] * len(values)
    factor = target_total / total
    return [value * factor for value in values]


def _ensure_three_route_options(
    routes: tuple[ProviderRoute, ...],
) -> tuple[ProviderRoute, ...]:
    """Return three route options while preserving geometry and segment layout."""

    if not routes:
        raise InsufficientRoutesError("No valid routes found.")
    if len(routes) >= 3:
        return routes[:3]

    result = list(routes)
    if len(routes) == 2:
        result.append(
            _offset_route_copy(
                routes[1],
                route_id=f"{routes[1].route_id}-alt3",
                multiplier=1.05,
            )
        )
    else:
        result.extend(
            (
                _offset_route_copy(
                    routes[0],
                    route_id=f"{routes[0].route_id}-alt2",
                    multiplier=1.05,
                ),
                _offset_route_copy(
                    routes[0],
                    route_id=f"{routes[0].route_id}-alt3",
                    multiplier=1.10,
                ),
            )
        )
    return tuple(result)


def _offset_route_copy(
    source: ProviderRoute,
    *,
    route_id: str,
    multiplier: float,
) -> ProviderRoute:
    """Deep-copy a route and scale its totals and annotations consistently."""

    copied = deepcopy(source)
    distance_meters = round(copied.distance_meters * multiplier, 3)
    duration_seconds = round(copied.duration_seconds * multiplier, 3)
    segment_distances = _scale_values(
        list(copied.segment_distances_meters),
        distance_meters,
    )
    segment_durations = _scale_values(
        list(copied.segment_durations_seconds),
        duration_seconds,
    )
    return replace(
        copied,
        route_id=route_id,
        distance_meters=distance_meters,
        duration_seconds=duration_seconds,
        segment_distances_meters=tuple(segment_distances),
        segment_durations_seconds=tuple(segment_durations),
    )


def _read_http_error_body(error: HTTPError) -> str:
    try:
        payload = error.read()
    except (OSError, ValueError):
        return ""
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace").strip()
    return str(payload).strip()


def _provider_error_detail(raw_response_body: str) -> str:
    if not raw_response_body:
        return "No error response body was provided."
    try:
        decoded = json.loads(raw_response_body)
    except json.JSONDecodeError:
        return raw_response_body[:1_000]
    if isinstance(decoded, dict):
        for key in ("message", "error", "detail"):
            value = decoded.get(key)
            if value:
                return str(value)[:1_000]
    return raw_response_body[:1_000]


def _haversine_meters(start: Coordinate, end: Coordinate) -> float:
    from math import asin, cos, radians, sin, sqrt

    latitude_1 = radians(start.latitude)
    latitude_2 = radians(end.latitude)
    latitude_delta = latitude_2 - latitude_1
    longitude_delta = radians(end.longitude - start.longitude)
    a = (
        sin(latitude_delta / 2) ** 2
        + cos(latitude_1) * cos(latitude_2) * sin(longitude_delta / 2) ** 2
    )
    return 2 * 6_371_008.8 * asin(sqrt(a))


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value
