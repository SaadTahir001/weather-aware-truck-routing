from datetime import datetime, timedelta, timezone
from unittest import TestCase

from routing.external_services import (
    Coordinate,
    GeocodedLocation,
    ProviderRoute,
    WeatherReading,
)
from routing.route_planning import (
    METERS_PER_MILE,
    RoutePlanningService,
    normalize_weather_timeline,
)


class FakeRoutingClient:
    def geocode(self, query):
        if query == "Origin":
            coordinate = Coordinate(0, 0)
        else:
            coordinate = Coordinate(2, 0)
        return GeocodedLocation(query, query, coordinate)

    def get_route_options(self, origin, destination, departure_time):
        middle_latitudes = (0.1, 0.2, 0.3)
        return tuple(
            ProviderRoute(
                route_id=f"route-{index + 1}",
                geometry=(
                    origin,
                    Coordinate(1, middle_latitude),
                    destination,
                ),
                distance_meters=100 * METERS_PER_MILE,
                duration_seconds=7_200 + index * 600,
                segment_distances_meters=(
                    50 * METERS_PER_MILE,
                    50 * METERS_PER_MILE,
                ),
                segment_durations_seconds=(
                    (7_200 + index * 600) / 2,
                    (7_200 + index * 600) / 2,
                ),
            )
            for index, middle_latitude in enumerate(middle_latitudes)
        )


class FakeWeatherClient:
    def forecast_at(self, coordinate, eta):
        if coordinate.latitude < 0.15 and coordinate.latitude > 0:
            wind = 45
        elif coordinate.latitude < 0.25 and coordinate.latitude > 0:
            wind = 35
        else:
            wind = 10
        return WeatherReading(
            forecast_time=eta,
            wind_mph=wind,
            rain_in_per_hour=0,
            snow_in_per_hour=0,
            temperature_f=50,
            description="clear",
        )

    def forecast_timeline(self, coordinate, start_time, hours=48):
        return tuple(
            self.forecast_at(coordinate, start_time + timedelta(hours=offset))
            for offset in range(hours + 1)
        )


class RoutePlanningTests(TestCase):
    def test_normalizes_short_out_of_order_live_timeline_to_49_entries(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        later = FakeWeatherClient().forecast_at(
            Coordinate(0, 0),
            start + timedelta(hours=2),
        )
        earlier = FakeWeatherClient().forecast_at(Coordinate(0, 0), start)

        result = normalize_weather_timeline((later, earlier), start)

        self.assertEqual(len(result), 49)
        self.assertEqual(result[0].forecast_time, start)
        self.assertEqual(result[2].forecast_time, start + timedelta(hours=2))
        self.assertEqual(result[-1].forecast_time, start + timedelta(hours=2))

    def test_builds_frontend_payload_and_recommends_lowest_risk_route(self) -> None:
        service = RoutePlanningService(
            routing_client=FakeRoutingClient(),
            weather_client=FakeWeatherClient(),
            checkpoint_interval_miles=50,
        )

        result = service.calculate(
            origin="Origin",
            destination="Destination",
            departure_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            load_weight_lb=10_000,
        )

        self.assertEqual(len(result["routes"]), 3)
        self.assertEqual(
            [route["name"] for route in result["routes"]],
            ["Route 1", "Route 2", "Route 3"],
        )
        self.assertEqual(result["recommended_route_id"], "route-3")
        self.assertEqual(result["routes"][2]["decision"]["status"], "recommended")
        self.assertEqual(result["routes"][0]["decision"]["status"], "not_recommended")
        self.assertEqual(result["routes"][0]["geometry"]["type"], "LineString")
        self.assertEqual(len(result["routes"][0]["checkpoints"]), 3)
        timeline = result["routes"][0]["checkpoints"][0]["forecast_timeline"]
        self.assertEqual(len(timeline), 49)
        self.assertEqual(
            [entry["hour_offset"] for entry in timeline],
            list(range(49)),
        )
        self.assertTrue(
            all(
                set(entry) == {"hour_offset", "weather", "risk"}
                and isinstance(entry["hour_offset"], int)
                for entry in timeline
            )
        )
