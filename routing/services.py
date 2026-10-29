"""Pure-Python weather risk calculation and route recommendation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any, Iterable, Sequence


class RiskLevel(IntEnum):
    """Ordered risk values; the integer is also used for average risk."""

    LOW = 1
    MODERATE = 2
    HIGH = 3
    SEVERE = 4
    NO_TRAVEL = 5

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class CheckpointInput:
    name: str
    eta: datetime
    segment_distance_miles: float
    wind_mph: float
    rain_in_per_hour: float = 0.0
    snow_in_per_hour: float = 0.0


@dataclass(frozen=True)
class RouteInput:
    route_id: str | int
    name: str
    checkpoints: Sequence[CheckpointInput]


@dataclass(frozen=True)
class CheckpointRisk:
    checkpoint: CheckpointInput
    wind_risk: RiskLevel
    rain_risk: RiskLevel
    snow_risk: RiskLevel
    final_risk: RiskLevel


@dataclass(frozen=True)
class RouteEvaluation:
    route_id: str | int
    route_name: str
    checkpoint_risks: tuple[CheckpointRisk, ...]
    miles_by_risk: dict[RiskLevel, float]
    average_risk: float
    travel_seconds: float
    eligible: bool

    @property
    def severe_miles(self) -> float:
        return self.miles_by_risk[RiskLevel.SEVERE]

    @property
    def high_miles(self) -> float:
        return self.miles_by_risk[RiskLevel.HIGH]

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_risk[RiskLevel.NO_TRAVEL]

    @property
    def ranking_key(self) -> tuple[float, float, float, float]:
        """Required hierarchy: severe, high, average risk, travel time."""

        return (
            self.severe_miles,
            self.high_miles,
            self.average_risk,
            self.travel_seconds,
        )


@dataclass(frozen=True)
class RouteRecommendation:
    recommended: RouteEvaluation | None
    evaluations: tuple[RouteEvaluation, ...]

    def require_safe_route(self) -> RouteEvaluation:
        if self.recommended is None:
            raise NoSafeRouteError("Every candidate route contains No Travel risk.")
        return self.recommended


class NoSafeRouteError(RuntimeError):
    pass


def classify_wind(wind_mph: float) -> RiskLevel:
    _require_non_negative("wind_mph", wind_mph)
    if wind_mph < 25:
        return RiskLevel.LOW
    if wind_mph < 35:
        return RiskLevel.MODERATE
    if wind_mph < 45:
        return RiskLevel.HIGH
    if wind_mph < 55:
        return RiskLevel.SEVERE
    return RiskLevel.NO_TRAVEL


def classify_rain(rain_in_per_hour: float) -> RiskLevel:
    _require_non_negative("rain_in_per_hour", rain_in_per_hour)
    if rain_in_per_hour < 0.10:
        return RiskLevel.LOW
    if rain_in_per_hour < 0.25:
        return RiskLevel.MODERATE
    if rain_in_per_hour < 0.50:
        return RiskLevel.HIGH
    if rain_in_per_hour <= 1.00:
        return RiskLevel.SEVERE
    return RiskLevel.NO_TRAVEL


def classify_snow(snow_in_per_hour: float) -> RiskLevel:
    _require_non_negative("snow_in_per_hour", snow_in_per_hour)
    if snow_in_per_hour < 0.5:
        return RiskLevel.LOW
    if snow_in_per_hour < 1.0:
        return RiskLevel.MODERATE
    if snow_in_per_hour < 2.0:
        return RiskLevel.HIGH
    if snow_in_per_hour <= 3.0:
        return RiskLevel.SEVERE
    return RiskLevel.NO_TRAVEL


def calculate_checkpoint_risk(
    checkpoint: CheckpointInput,
    load_weight_lb: int | float,
) -> CheckpointRisk:
    """Evaluate weather and then apply the wind/load override rules."""

    _require_non_negative("load_weight_lb", load_weight_lb)
    wind_risk = classify_wind(checkpoint.wind_mph)
    rain_risk = classify_rain(checkpoint.rain_in_per_hour)
    snow_risk = classify_snow(checkpoint.snow_in_per_hour)
    final_risk = max(wind_risk, rain_risk, snow_risk)

    # Load rules are deliberately ordered from strongest to weakest.
    if checkpoint.wind_mph >= 55:
        final_risk = RiskLevel.NO_TRAVEL
    elif checkpoint.wind_mph >= 45 and load_weight_lb > 30_000:
        # Loads strictly above 30,000 lb cannot travel in 45-54 mph winds.
        final_risk = RiskLevel.NO_TRAVEL
    elif checkpoint.wind_mph >= 35 and load_weight_lb > 40_000:
        final_risk = max(final_risk, RiskLevel.SEVERE)

    return CheckpointRisk(
        checkpoint=checkpoint,
        wind_risk=wind_risk,
        rain_risk=rain_risk,
        snow_risk=snow_risk,
        final_risk=final_risk,
    )


def evaluate_route(route: RouteInput, load_weight_lb: int | float) -> RouteEvaluation:
    """Calculate miles by risk, distance-weighted average risk, and ETA duration."""

    _require_non_negative("load_weight_lb", load_weight_lb)
    checkpoints = tuple(route.checkpoints)
    if not checkpoints:
        raise ValueError(f"Route {route.name!r} must contain at least one checkpoint.")

    previous_eta: datetime | None = None
    risks: list[CheckpointRisk] = []
    for checkpoint in checkpoints:
        _require_non_negative(
            "segment_distance_miles", checkpoint.segment_distance_miles
        )
        if previous_eta is not None and checkpoint.eta < previous_eta:
            raise ValueError(
                f"Checkpoint ETAs for route {route.name!r} must be chronological."
            )
        previous_eta = checkpoint.eta
        risks.append(calculate_checkpoint_risk(checkpoint, load_weight_lb))

    miles_by_risk = {level: 0.0 for level in RiskLevel}
    total_miles = 0.0
    weighted_risk = 0.0
    for result in risks:
        miles = float(result.checkpoint.segment_distance_miles)
        miles_by_risk[result.final_risk] += miles
        total_miles += miles
        weighted_risk += miles * int(result.final_risk)

    # A zero-mile route is still useful in unit tests or a point-in-time check.
    if total_miles > 0:
        average_risk = weighted_risk / total_miles
    else:
        average_risk = sum(int(result.final_risk) for result in risks) / len(risks)

    travel_seconds = max(
        0.0,
        (checkpoints[-1].eta - checkpoints[0].eta).total_seconds(),
    )
    eligible = all(result.final_risk != RiskLevel.NO_TRAVEL for result in risks)

    return RouteEvaluation(
        route_id=route.route_id,
        route_name=route.name,
        checkpoint_risks=tuple(risks),
        miles_by_risk=miles_by_risk,
        average_risk=average_risk,
        travel_seconds=travel_seconds,
        eligible=eligible,
    )


def recommend_best_route(
    routes: Iterable[RouteInput],
    load_weight_lb: int | float,
) -> RouteRecommendation:
    """
    Evaluate all candidates and recommend the best eligible route.

    A route with any No Travel checkpoint is retained in ``evaluations`` for UI
    display, but is excluded from selection. Eligible routes are compared in the
    exact required order: Severe miles, High miles, average risk, travel time.
    Input order is the stable final tie-breaker.
    """

    evaluations = tuple(evaluate_route(route, load_weight_lb) for route in routes)
    eligible = [evaluation for evaluation in evaluations if evaluation.eligible]
    recommended = min(eligible, key=lambda item: item.ranking_key) if eligible else None
    return RouteRecommendation(
        recommended=recommended,
        evaluations=evaluations,
    )


def route_input_from_model(route: Any) -> RouteInput:
    """Adapt a ``Route`` model instance (with checkpoints) to the pure service DTO."""

    checkpoints = route.checkpoints.all().order_by("sequence")
    return RouteInput(
        route_id=route.pk,
        name=route.name,
        checkpoints=tuple(
            CheckpointInput(
                name=checkpoint.name or f"Checkpoint {checkpoint.sequence}",
                eta=checkpoint.eta,
                segment_distance_miles=float(checkpoint.segment_distance_miles),
                wind_mph=float(checkpoint.wind_mph),
                rain_in_per_hour=float(checkpoint.rain_in_per_hour),
                snow_in_per_hour=float(checkpoint.snow_in_per_hour),
            )
            for checkpoint in checkpoints
        ),
    )


def recommend_best_route_models(
    routes: Iterable[Any],
    load_weight_lb: int | float,
) -> RouteRecommendation:
    """Convenience entry point for a Route queryset or iterable of Route models."""

    return recommend_best_route(
        (route_input_from_model(route) for route in routes),
        load_weight_lb,
    )


def _require_non_negative(name: str, value: int | float) -> None:
    if value < 0:
        raise ValueError(f"{name} cannot be negative.")
