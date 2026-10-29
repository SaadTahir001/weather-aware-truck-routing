"""Deterministic provider-free route data for local frontend development."""

from __future__ import annotations

import hashlib
import math
import os
from datetime import datetime, timedelta
from typing import Any

from .external_services import (
    ConfigurationError,
    Coordinate,
    GeocodedLocation,
    ProviderRoute,
    WeatherReading,
)
from .route_planning import (
    METERS_PER_MILE,
    EnrichedRoute,
    RoutePlanningService,
    RouteSizeLimitError,
    sample_route,
)
from .services import CheckpointInput, RiskLevel, RouteInput, recommend_best_route


_CITY_COORDINATES: dict[str, Coordinate] = {
    "atlanta": Coordinate(-84.3880, 33.7490),
    "boston": Coordinate(-71.0589, 42.3601),
    "chicago": Coordinate(-87.6298, 41.8781),
    "dallas": Coordinate(-96.7970, 32.7767),
    "denver": Coordinate(-104.9903, 39.7392),
    "detroit": Coordinate(-83.0458, 42.3314),
    "houston": Coordinate(-95.3698, 29.7604),
    "kansas city": Coordinate(-94.5786, 39.0997),
    "las vegas": Coordinate(-115.1398, 36.1699),
    "los angeles": Coordinate(-118.2437, 34.0522),
    "miami": Coordinate(-80.1918, 25.7617),
    "new york": Coordinate(-74.0060, 40.7128),
    "phoenix": Coordinate(-112.0740, 33.4484),
    "portland": Coordinate(-122.6765, 45.5231),
    "seattle": Coordinate(-122.3321, 47.6062),
}

_RISK_PATTERNS: tuple[tuple[RiskLevel, ...], ...] = (
    (
        RiskLevel.LOW,
        RiskLevel.LOW,
        RiskLevel.MODERATE,
        RiskLevel.HIGH,
        RiskLevel.MODERATE,
        RiskLevel.LOW,
    ),
    (
        RiskLevel.LOW,
        RiskLevel.MODERATE,
        RiskLevel.HIGH,
        RiskLevel.SEVERE,
        RiskLevel.HIGH,
        RiskLevel.MODERATE,
    ),
    (
        RiskLevel.LOW,
        RiskLevel.HIGH,
        RiskLevel.SEVERE,
        RiskLevel.NO_TRAVEL,
        RiskLevel.SEVERE,
        RiskLevel.MODERATE,
    ),
)


class MockRoutePlanningService:
    """Return realistic, repeatable data without making provider requests."""

    def __init__(
        self,
        *,
        reason: str,
        checkpoint_interval_miles: float = 50.0,
        max_checkpoints_per_request: int = 200,
    ) -> None:
        self.reason = reason
        self.checkpoint_interval_miles = checkpoint_interval_miles
        self.max_checkpoints_per_request = max_checkpoints_per_request

    @classmethod
    def from_env(cls, *, reason: str) -> "MockRoutePlanningService":
        return cls(
            reason=reason,
            checkpoint_interval_miles=_positive_float_env(
                "ROUTE_CHECKPOINT_INTERVAL_MILES", 50.0
            ),
            max_checkpoints_per_request=_positive_int_env(
                "ROUTE_MAX_CHECKPOINTS", 200
            ),
        )

    def calculate(
        self,
        *,
        origin: str,
        destination: str,
        departure_time: datetime,
        load_weight_lb: int,
    ) -> dict[str, Any]:
        geocoded_origin = _mock_geocode(origin)
        geocoded_destination = _mock_geocode(destination)
        if _haversine_meters(
            geocoded_origin.coordinate, geocoded_destination.coordinate
        ) < 75 * METERS_PER_MILE:
            geocoded_destination = _move_mock_destination(geocoded_destination)

        provider_routes = _build_mock_routes(
            geocoded_origin.coordinate, geocoded_destination.coordinate
        )
        sampled_routes = tuple(
            sample_route(
                route,
                departure_time=departure_time,
                interval_miles=self.checkpoint_interval_miles,
            )
            for route in provider_routes
        )
        total_checkpoints = sum(len(route) for route in sampled_routes)
        if total_checkpoints > self.max_checkpoints_per_request:
            raise RouteSizeLimitError(
                f"This mock trip needs {total_checkpoints} checkpoints; "
                f"the configured limit is {self.max_checkpoints_per_request}."
            )

        enriched_routes: list[EnrichedRoute] = []
        risk_inputs: list[RouteInput] = []
        for route_index, (provider_route, checkpoints) in enumerate(
            zip(provider_routes, sampled_routes)
        ):
            weather_readings: list[WeatherReading] = []
            risk_checkpoints: list[CheckpointInput] = []
            for checkpoint_index, checkpoint in enumerate(checkpoints):
                progress = (
                    checkpoint_index / (len(checkpoints) - 1)
                    if len(checkpoints) > 1
                    else 0.0
                )
                requested_risk = _pattern_risk(route_index, progress)
                weather = _mock_weather(
                    requested_risk,
                    checkpoint.eta,
                    route_index=route_index,
                    checkpoint_index=checkpoint_index,
                )
                weather_readings.append(weather)
                risk_checkpoints.append(
                    CheckpointInput(
                        name=f"Checkpoint {checkpoint_index + 1}",
                        eta=checkpoint.eta,
                        segment_distance_miles=checkpoint.segment_distance_miles,
                        wind_mph=weather.wind_mph,
                        rain_in_per_hour=weather.rain_in_per_hour,
                        snow_in_per_hour=weather.snow_in_per_hour,
                    )
                )
            enriched_routes.append(
                EnrichedRoute(
                    provider_route=provider_route,
                    sampled_checkpoints=checkpoints,
                    weather=tuple(weather_readings),
                )
            )
            risk_inputs.append(
                RouteInput(
                    route_id=provider_route.route_id,
                    name=f"Route {route_index + 1}",
                    checkpoints=tuple(risk_checkpoints),
                )
            )

        recommendation = recommend_best_route(risk_inputs, load_weight_lb)
        evaluations = {
            evaluation.route_id: evaluation for evaluation in recommendation.evaluations
        }
        routes = [
            RoutePlanningService._serialize_route(
                enriched,
                evaluations[enriched.provider_route.route_id],
                recommendation.recommended,
                departure_time,
            )
            for enriched in enriched_routes
        ]
        recommended_id = (
            recommendation.recommended.route_id
            if recommendation.recommended is not None
            else None
        )
        summary = (
            f"{recommendation.recommended.route_name} is recommended from deterministic "
            "development data using Severe miles, High miles, average risk, and travel time."
            if recommendation.recommended is not None
            else "No mock route is recommended because every option contains No Travel risk."
        )

        return {
            "data_source": "mock",
            "mock_reason": self.reason,
            "request": {
                "origin": origin,
                "destination": destination,
                "departure_time": departure_time,
                "load_weight_lb": load_weight_lb,
            },
            "resolved_locations": {
                "origin": _location_dict(geocoded_origin),
                "destination": _location_dict(geocoded_destination),
            },
            "recommended_route_id": recommended_id,
            "recommendation_summary": summary,
            "ranking_hierarchy": [
                "fewest_severe_miles",
                "fewest_high_miles",
                "lowest_average_risk",
                "shortest_travel_time",
            ],
            "routes": routes,
        }


def _build_mock_routes(
    origin: Coordinate,
    destination: Coordinate,
) -> tuple[ProviderRoute, ...]:
    delta_lon = destination.longitude - origin.longitude
    delta_lat = destination.latitude - origin.latitude
    planar_length = max(math.hypot(delta_lon, delta_lat), 0.1)
    perpendicular_lon = -delta_lat / planar_length
    perpendicular_lat = delta_lon / planar_length
    curve_factors = (0.025, 0.16, -0.14)
    speeds_mph = (57.0, 53.0, 61.0)
    routes: list[ProviderRoute] = []

    for route_index, (curve_factor, speed_mph) in enumerate(
        zip(curve_factors, speeds_mph)
    ):
        geometry: list[Coordinate] = []
        for point_index in range(13):
            progress = point_index / 12
            bulge = math.sin(math.pi * progress) * planar_length * curve_factor
            geometry.append(
                Coordinate(
                    longitude=origin.longitude
                    + delta_lon * progress
                    + perpendicular_lon * bulge,
                    latitude=origin.latitude
                    + delta_lat * progress
                    + perpendicular_lat * bulge,
                )
            )
        distances = [
            _haversine_meters(start, end)
            for start, end in zip(geometry, geometry[1:])
        ]
        total_distance = sum(distances)
        total_duration = total_distance / (speed_mph * METERS_PER_MILE) * 3_600
        durations = [
            total_duration * distance / total_distance for distance in distances
        ]
        routes.append(
            ProviderRoute(
                route_id=f"mock-route-{route_index + 1}",
                geometry=tuple(geometry),
                distance_meters=total_distance,
                duration_seconds=total_duration,
                segment_distances_meters=tuple(distances),
                segment_durations_seconds=tuple(durations),
            )
        )
    return tuple(routes)


def _pattern_risk(route_index: int, progress: float) -> RiskLevel:
    pattern = _RISK_PATTERNS[route_index]
    pattern_index = min(len(pattern) - 1, round(progress * (len(pattern) - 1)))
    return pattern[pattern_index]


def _mock_weather(
    requested_risk: RiskLevel,
    eta: datetime,
    *,
    route_index: int,
    checkpoint_index: int,
) -> WeatherReading:
    values = {
        RiskLevel.LOW: (18.0, 0.02, 0.0, "partly cloudy"),
        RiskLevel.MODERATE: (29.0, 0.08, 0.0, "gusty crosswinds"),
        RiskLevel.HIGH: (22.0, 0.34, 0.0, "heavy rain bands"),
        RiskLevel.SEVERE: (24.0, 0.72, 0.0, "severe rainfall"),
        RiskLevel.NO_TRAVEL: (58.0, 0.18, 0.0, "dangerous winds"),
    }
    wind, rain, snow, description = values[requested_risk]
    if eta.month in {12, 1, 2} and requested_risk in {
        RiskLevel.HIGH,
        RiskLevel.SEVERE,
    }:
        rain = 0.0
        snow = 1.35 if requested_risk == RiskLevel.HIGH else 2.35
        description = "heavy snow" if requested_risk == RiskLevel.HIGH else "severe snow"
    temperature = 61.0 - route_index * 2.5 - checkpoint_index * 0.8
    return WeatherReading(
        forecast_time=eta.replace(minute=0, second=0, microsecond=0),
        wind_mph=wind,
        rain_in_per_hour=rain,
        snow_in_per_hour=snow,
        temperature_f=temperature,
        description=description,
    )


def _mock_geocode(query: str) -> GeocodedLocation:
    normalized = query.casefold().strip()
    coordinate = _parse_coordinate_query(query)
    if coordinate is None:
        for city, city_coordinate in _CITY_COORDINATES.items():
            if city in normalized:
                coordinate = city_coordinate
                break
    if coordinate is None:
        digest = hashlib.sha256(normalized.encode("utf-8")).digest()
        longitude = -123.0 + int.from_bytes(digest[:4], "big") / 2**32 * 48.0
        latitude = 27.0 + int.from_bytes(digest[4:8], "big") / 2**32 * 20.0
        coordinate = Coordinate(longitude, latitude)
    return GeocodedLocation(
        query=query,
        display_name=f"{query} (mock location)",
        coordinate=coordinate,
    )


def _parse_coordinate_query(query: str) -> Coordinate | None:
    parts = [part.strip() for part in query.split(",")]
    if len(parts) != 2:
        return None
    try:
        latitude, longitude = (float(part) for part in parts)
    except ValueError:
        return None
    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return Coordinate(longitude, latitude)
    return None


def _move_mock_destination(location: GeocodedLocation) -> GeocodedLocation:
    longitude = location.coordinate.longitude + 4.0
    if longitude > -67.0:
        longitude = location.coordinate.longitude - 4.0
    latitude = max(25.0, min(49.0, location.coordinate.latitude + 1.25))
    return GeocodedLocation(
        query=location.query,
        display_name=location.display_name,
        coordinate=Coordinate(longitude, latitude),
    )


def _haversine_meters(start: Coordinate, end: Coordinate) -> float:
    latitude_1 = math.radians(start.latitude)
    latitude_2 = math.radians(end.latitude)
    latitude_delta = latitude_2 - latitude_1
    longitude_delta = math.radians(end.longitude - start.longitude)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_1)
        * math.cos(latitude_2)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(value))


def _location_dict(location: GeocodedLocation) -> dict[str, Any]:
    return {
        "query": location.query,
        "display_name": location.display_name,
        "coordinate": {
            "longitude": location.coordinate.longitude,
            "latitude": location.coordinate.latitude,
        },
    }


def _positive_float_env(name: str, default: float) -> float:
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


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value
