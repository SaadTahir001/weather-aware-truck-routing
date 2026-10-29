from datetime import datetime, timedelta, timezone
from unittest import TestCase

from routing.services import (
    CheckpointInput,
    RiskLevel,
    RouteInput,
    calculate_checkpoint_risk,
    classify_rain,
    classify_snow,
    classify_wind,
    recommend_best_route,
)


START = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)


def checkpoint(
    name: str,
    *,
    hour: int,
    miles: float,
    wind: float = 0,
    rain: float = 0,
    snow: float = 0,
) -> CheckpointInput:
    return CheckpointInput(
        name=name,
        eta=START + timedelta(hours=hour),
        segment_distance_miles=miles,
        wind_mph=wind,
        rain_in_per_hour=rain,
        snow_in_per_hour=snow,
    )


class ThresholdTests(TestCase):
    def test_wind_thresholds(self) -> None:
        self.assertEqual(classify_wind(24.99), RiskLevel.LOW)
        self.assertEqual(classify_wind(25), RiskLevel.MODERATE)
        self.assertEqual(classify_wind(35), RiskLevel.HIGH)
        self.assertEqual(classify_wind(45), RiskLevel.SEVERE)
        self.assertEqual(classify_wind(55), RiskLevel.NO_TRAVEL)

    def test_rain_thresholds(self) -> None:
        self.assertEqual(classify_rain(0.099), RiskLevel.LOW)
        self.assertEqual(classify_rain(0.10), RiskLevel.MODERATE)
        self.assertEqual(classify_rain(0.25), RiskLevel.HIGH)
        self.assertEqual(classify_rain(0.50), RiskLevel.SEVERE)
        self.assertEqual(classify_rain(1.00), RiskLevel.SEVERE)
        self.assertEqual(classify_rain(1.001), RiskLevel.NO_TRAVEL)

    def test_snow_thresholds(self) -> None:
        self.assertEqual(classify_snow(0.49), RiskLevel.LOW)
        self.assertEqual(classify_snow(0.5), RiskLevel.MODERATE)
        self.assertEqual(classify_snow(1.0), RiskLevel.HIGH)
        self.assertEqual(classify_snow(2.0), RiskLevel.SEVERE)
        self.assertEqual(classify_snow(3.0), RiskLevel.SEVERE)
        self.assertEqual(classify_snow(3.01), RiskLevel.NO_TRAVEL)


class LoadRuleTests(TestCase):
    def test_55_mph_is_no_travel_for_every_load(self) -> None:
        result = calculate_checkpoint_risk(
            checkpoint("wind", hour=0, miles=10, wind=55),
            load_weight_lb=1_000,
        )
        self.assertEqual(result.final_risk, RiskLevel.NO_TRAVEL)

    def test_45_to_54_mph_is_no_travel_only_above_30000_lb(self) -> None:
        at_threshold = calculate_checkpoint_risk(
            checkpoint("wind", hour=0, miles=10, wind=45),
            load_weight_lb=30_000,
        )
        above_threshold = calculate_checkpoint_risk(
            checkpoint("wind", hour=0, miles=10, wind=45),
            load_weight_lb=30_001,
        )

        self.assertEqual(at_threshold.final_risk, RiskLevel.SEVERE)
        self.assertEqual(above_threshold.final_risk, RiskLevel.NO_TRAVEL)

    def test_35_to_44_mph_is_severe_above_40000_lb(self) -> None:
        result = calculate_checkpoint_risk(
            checkpoint("wind", hour=0, miles=10, wind=35),
            load_weight_lb=40_001,
        )
        self.assertEqual(result.final_risk, RiskLevel.SEVERE)


class RecommendationTests(TestCase):
    def test_hierarchy_prioritizes_fewer_severe_then_high_miles(self) -> None:
        faster_but_severe = RouteInput(
            route_id="a",
            name="Faster but severe",
            checkpoints=(
                checkpoint("start", hour=0, miles=5, wind=45),
                checkpoint("end", hour=1, miles=0),
            ),
        )
        slower_without_severe = RouteInput(
            route_id="b",
            name="Slower without severe",
            checkpoints=(
                checkpoint("start", hour=0, miles=20, wind=35),
                checkpoint("end", hour=2, miles=0),
            ),
        )

        recommendation = recommend_best_route(
            [faster_but_severe, slower_without_severe],
            load_weight_lb=10_000,
        )

        self.assertEqual(recommendation.require_safe_route().route_id, "b")

    def test_no_travel_route_is_never_recommended(self) -> None:
        blocked = RouteInput(
            route_id="blocked",
            name="Blocked",
            checkpoints=(checkpoint("start", hour=0, miles=1, wind=55),),
        )
        safe = RouteInput(
            route_id="safe",
            name="Safe",
            checkpoints=(checkpoint("start", hour=0, miles=100, wind=45),),
        )

        recommendation = recommend_best_route([blocked, safe], load_weight_lb=1_000)

        self.assertEqual(recommendation.require_safe_route().route_id, "safe")

    def test_shorter_time_breaks_an_otherwise_exact_tie(self) -> None:
        slow = RouteInput(
            route_id="slow",
            name="Slow",
            checkpoints=(
                checkpoint("start", hour=0, miles=10, wind=20),
                checkpoint("end", hour=3, miles=0, wind=20),
            ),
        )
        fast = RouteInput(
            route_id="fast",
            name="Fast",
            checkpoints=(
                checkpoint("start", hour=0, miles=10, wind=20),
                checkpoint("end", hour=1, miles=0, wind=20),
            ),
        )

        recommendation = recommend_best_route([slow, fast], load_weight_lb=10_000)

        self.assertEqual(recommendation.require_safe_route().route_id, "fast")
