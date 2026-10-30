"""Application service that joins providers to the risk calculation domain."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .external_services import (
    ConfigurationError,
    Coordinate,
    MapboxClient,
    OpenWeatherClient,
    ProviderRoute,
    WeatherReading,
)
from .services import (
    CheckpointInput,
    CheckpointRisk,
    RiskLevel,
    RouteEvaluation,
    RouteInput,
    calculate_checkpoint_risk,
    recommend_best_route,
)


METERS_PER_MILE = 1_609.344


class RouteSizeLimitError(ValueError):
    """The request would require more weather calls than configured."""


@dataclass(frozen=True)
class SampledCheckpoint:
    coordinate: Coordinate
    eta: datetime
    segment_distance_miles: float


@dataclass(frozen=True)
class EnrichedRoute:
    provider_route: ProviderRoute
    sampled_checkpoints: tuple[SampledCheckpoint, ...]
    weather: tuple[WeatherReading, ...]
    weather_timelines: tuple[tuple[WeatherReading, ...], ...]


class RoutePlanningService:
    def __init__(
        self,
        *,
        routing_client: MapboxClient,
        weather_client: OpenWeatherClient,
        checkpoint_interval_miles: float = 50.0,
        max_checkpoints_per_request: int = 200,
    ) -> None:
        if checkpoint_interval_miles <= 0:
            raise ConfigurationError(
                "ROUTE_CHECKPOINT_INTERVAL_MILES must be greater than zero."
            )
        if max_checkpoints_per_request < 3:
            raise ConfigurationError("ROUTE_MAX_CHECKPOINTS must be at least three.")
        self.routing_client = routing_client
        self.weather_client = weather_client
        self.checkpoint_interval_miles = checkpoint_interval_miles
        self.max_checkpoints_per_request = max_checkpoints_per_request

    @classmethod
    def from_env(cls) -> "RoutePlanningService":
        try:
            max_checkpoints = int(os.getenv("ROUTE_MAX_CHECKPOINTS", "200"))
        except ValueError as exc:
            raise ConfigurationError("ROUTE_MAX_CHECKPOINTS must be an integer.") from exc
        return cls(
            routing_client=MapboxClient.from_env(),
            weather_client=OpenWeatherClient.from_env(),
            checkpoint_interval_miles=_positive_float_env(
                "ROUTE_CHECKPOINT_INTERVAL_MILES", 50.0
            ),
            max_checkpoints_per_request=max_checkpoints,
        )

    def calculate(
        self,
        *,
        origin: str,
        destination: str,
        departure_time: datetime,
        load_weight_lb: int,
    ) -> dict[str, Any]:
        geocoded_origin = self.routing_client.geocode(origin)
        geocoded_destination = self.routing_client.geocode(destination)
        provider_routes = self.routing_client.get_route_options(
            geocoded_origin.coordinate,
            geocoded_destination.coordinate,
            departure_time,
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
                f"This route needs {total_checkpoints} weather checkpoints; "
                f"the configured limit is {self.max_checkpoints_per_request}."
            )

        weather_timeline_cache: dict[
            tuple[float, float, int], tuple[WeatherReading, ...]
        ] = {}
        enriched: list[EnrichedRoute] = []
        risk_inputs: list[RouteInput] = []
        for provider_route, checkpoints in zip(provider_routes, sampled_routes):
            weather_readings: list[WeatherReading] = []
            weather_timelines: list[tuple[WeatherReading, ...]] = []
            risk_checkpoints: list[CheckpointInput] = []
            for sequence, checkpoint in enumerate(checkpoints):
                cache_key = (
                    round(checkpoint.coordinate.longitude, 4),
                    round(checkpoint.coordinate.latitude, 4),
                    int(departure_time.timestamp() // 3_600),
                )
                timeline = weather_timeline_cache.get(cache_key)
                if timeline is None:
                    timeline = self.weather_client.forecast_timeline(
                        checkpoint.coordinate,
                        departure_time,
                        hours=48,
                    )
                    weather_timeline_cache[cache_key] = timeline
                weather = min(
                    timeline,
                    key=lambda reading: abs(
                        (reading.forecast_time - checkpoint.eta).total_seconds()
                    ),
                )
                weather_readings.append(weather)
                weather_timelines.append(timeline)
                risk_checkpoints.append(
                    CheckpointInput(
                        name=f"Checkpoint {sequence + 1}",
                        eta=checkpoint.eta,
                        segment_distance_miles=checkpoint.segment_distance_miles,
                        wind_mph=weather.wind_mph,
                        rain_in_per_hour=weather.rain_in_per_hour,
                        snow_in_per_hour=weather.snow_in_per_hour,
                    )
                )
            enriched.append(
                EnrichedRoute(
                    provider_route=provider_route,
                    sampled_checkpoints=checkpoints,
                    weather=tuple(weather_readings),
                    weather_timelines=tuple(weather_timelines),
                )
            )
            risk_inputs.append(
                RouteInput(
                    route_id=provider_route.route_id,
                    name=f"Route {len(risk_inputs) + 1}",
                    checkpoints=tuple(risk_checkpoints),
                )
            )

        recommendation = recommend_best_route(risk_inputs, load_weight_lb)
        evaluation_by_id = {
            evaluation.route_id: evaluation for evaluation in recommendation.evaluations
        }
        recommended_id = (
            recommendation.recommended.route_id
            if recommendation.recommended is not None
            else None
        )
        routes = [
            self._serialize_route(
                route,
                evaluation_by_id[route.provider_route.route_id],
                recommendation.recommended,
                departure_time,
                load_weight_lb,
            )
            for route in enriched
        ]

        if recommendation.recommended is None:
            summary = "No route is recommended because every option contains No Travel risk."
        else:
            winner = recommendation.recommended
            summary = (
                f"{winner.route_name} is recommended by the ordered comparison of "
                "Severe miles, High miles, average risk, and travel time."
            )

        return {
            "data_source": "live",
            "mock_reason": None,
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

    @staticmethod
    def _serialize_route(
        route: EnrichedRoute,
        evaluation: RouteEvaluation,
        recommended: RouteEvaluation | None,
        departure_time: datetime,
        load_weight_lb: int,
    ) -> dict[str, Any]:
        checkpoint_payloads = []
        for sequence, (sample, weather, risk, timeline) in enumerate(
            zip(
                route.sampled_checkpoints,
                route.weather,
                evaluation.checkpoint_risks,
                route.weather_timelines,
            )
        ):
            timeline_payloads = []
            for hour_offset, timeline_weather in enumerate(timeline):
                timeline_risk = calculate_checkpoint_risk(
                    CheckpointInput(
                        name=f"Checkpoint {sequence + 1}",
                        eta=timeline_weather.forecast_time,
                        segment_distance_miles=sample.segment_distance_miles,
                        wind_mph=timeline_weather.wind_mph,
                        rain_in_per_hour=timeline_weather.rain_in_per_hour,
                        snow_in_per_hour=timeline_weather.snow_in_per_hour,
                    ),
                    load_weight_lb,
                )
                timeline_payloads.append(
                    {
                        "hour_offset": hour_offset,
                        "weather": _weather_dict(timeline_weather),
                        "risk": _risk_dict(timeline_risk),
                    }
                )
            checkpoint_payloads.append(
                {
                    "sequence": sequence + 1,
                    "coordinate": {
                        "longitude": sample.coordinate.longitude,
                        "latitude": sample.coordinate.latitude,
                    },
                    "eta": sample.eta,
                    "segment_distance_miles": round(
                        sample.segment_distance_miles, 2
                    ),
                    "weather": _weather_dict(weather),
                    "risk": _risk_dict(risk),
                    "forecast_timeline": timeline_payloads,
                }
            )

        decision_status, decision_reason = _decision(evaluation, recommended)
        provider_route = route.provider_route
        return {
            "id": provider_route.route_id,
            "name": evaluation.route_name,
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [coordinate.longitude, coordinate.latitude]
                    for coordinate in provider_route.geometry
                ],
            },
            "distance_miles": round(
                provider_route.distance_meters / METERS_PER_MILE, 2
            ),
            "duration_seconds": round(provider_route.duration_seconds),
            "arrival_time": departure_time
            + timedelta(seconds=provider_route.duration_seconds),
            "eligible": evaluation.eligible,
            "ranking": {
                "severe_miles": round(evaluation.severe_miles, 2),
                "high_miles": round(evaluation.high_miles, 2),
                "average_risk": round(evaluation.average_risk, 3),
                "travel_seconds": round(evaluation.travel_seconds),
            },
            "decision": {
                "status": decision_status,
                "reason": decision_reason,
            },
            "checkpoints": checkpoint_payloads,
        }


def sample_route(
    route: ProviderRoute,
    *,
    departure_time: datetime,
    interval_miles: float,
) -> tuple[SampledCheckpoint, ...]:
    """Interpolate coordinates and ETAs at fixed along-route distances."""

    if interval_miles <= 0:
        raise ValueError("interval_miles must be greater than zero.")
    interval_meters = interval_miles * METERS_PER_MILE
    targets: list[float] = [0.0]
    next_target = interval_meters
    while next_target < route.distance_meters:
        targets.append(next_target)
        next_target += interval_meters
    if route.distance_meters > 0:
        targets.append(route.distance_meters)

    cumulative_distances = [0.0]
    cumulative_durations = [0.0]
    for distance, duration in zip(
        route.segment_distances_meters, route.segment_durations_seconds
    ):
        cumulative_distances.append(cumulative_distances[-1] + distance)
        cumulative_durations.append(cumulative_durations[-1] + duration)

    samples: list[SampledCheckpoint] = []
    segment_index = 0
    for target_index, target in enumerate(targets):
        while (
            segment_index < len(route.segment_distances_meters) - 1
            and cumulative_distances[segment_index + 1] < target
        ):
            segment_index += 1
        segment_distance = route.segment_distances_meters[segment_index]
        within_segment = target - cumulative_distances[segment_index]
        fraction = (
            min(1.0, max(0.0, within_segment / segment_distance))
            if segment_distance > 0
            else 0.0
        )
        start = route.geometry[segment_index]
        end = route.geometry[segment_index + 1]
        coordinate = Coordinate(
            longitude=start.longitude + (end.longitude - start.longitude) * fraction,
            latitude=start.latitude + (end.latitude - start.latitude) * fraction,
        )
        elapsed_seconds = cumulative_durations[segment_index] + (
            route.segment_durations_seconds[segment_index] * fraction
        )
        following_target = (
            targets[target_index + 1]
            if target_index + 1 < len(targets)
            else target
        )
        samples.append(
            SampledCheckpoint(
                coordinate=coordinate,
                eta=departure_time + timedelta(seconds=elapsed_seconds),
                segment_distance_miles=(following_target - target) / METERS_PER_MILE,
            )
        )
    return tuple(samples)


def _decision(
    evaluation: RouteEvaluation,
    recommended: RouteEvaluation | None,
) -> tuple[str, str]:
    if not evaluation.eligible:
        blocked = [
            risk.checkpoint.name
            for risk in evaluation.checkpoint_risks
            if risk.final_risk == RiskLevel.NO_TRAVEL
        ]
        return (
            "rejected",
            "Rejected because No Travel risk occurs at " + ", ".join(blocked) + ".",
        )
    if recommended is None:
        return "not_recommended", "No eligible route was selected."
    if evaluation.route_id == recommended.route_id:
        return (
            "recommended",
            "Selected using Severe miles, High miles, average risk, then travel time.",
        )

    criteria = (
        ("Severe miles", evaluation.severe_miles, recommended.severe_miles),
        ("High miles", evaluation.high_miles, recommended.high_miles),
        ("average risk", evaluation.average_risk, recommended.average_risk),
        ("travel time", evaluation.travel_seconds, recommended.travel_seconds),
    )
    for label, value, winner_value in criteria:
        if abs(value - winner_value) > 1e-9:
            return (
                "not_recommended",
                f"Ranked behind {recommended.route_name} at the first differing "
                f"criterion, {label}: {value:.3f} versus {winner_value:.3f}.",
            )
    return (
        "not_recommended",
        f"All ranking criteria tied with {recommended.route_name}; provider order broke the tie.",
    )


def _weather_dict(weather: WeatherReading) -> dict[str, Any]:
    return {
        "forecast_time": weather.forecast_time,
        "wind_mph": round(weather.wind_mph, 2),
        "rain_in_per_hour": round(weather.rain_in_per_hour, 3),
        "snow_in_per_hour": round(weather.snow_in_per_hour, 3),
        "temperature_f": weather.temperature_f,
        "description": weather.description,
    }


def _risk_dict(risk: CheckpointRisk) -> dict[str, str]:
    return {
        "wind": risk.wind_risk.label,
        "rain": risk.rain_risk.label,
        "snow": risk.snow_risk.label,
        "overall": risk.final_risk.label,
    }


def _location_dict(location: Any) -> dict[str, Any]:
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
