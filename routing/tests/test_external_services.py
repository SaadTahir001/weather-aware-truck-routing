from datetime import datetime, timezone
from unittest import TestCase

from routing.external_services import (
    Coordinate,
    MapboxClient,
    OpenWeatherClient,
    ProviderRoute,
)
from routing.route_planning import METERS_PER_MILE, sample_route


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, params, timeout_seconds):
        self.calls.append((url, params, timeout_seconds))
        return self.payload


class ProviderParsingTests(TestCase):
    def test_mapbox_requests_and_parses_three_routes(self) -> None:
        route = {
            "geometry": {"coordinates": [[0, 0], [1, 1]]},
            "distance": 1_000,
            "duration": 100,
            "legs": [{"annotation": {"distance": [1_000], "duration": [100]}}],
        }
        http = FakeHttpClient({"code": "Ok", "uuid": "abc", "routes": [route] * 3})
        client = MapboxClient(access_token="secret", http_client=http)

        result = client.get_route_options(
            Coordinate(0, 0),
            Coordinate(1, 1),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].route_id, "abc-1")
        self.assertEqual(http.calls[0][1]["alternatives"], "true")
        self.assertEqual(http.calls[0][1]["geometries"], "geojson")

    def test_openweather_converts_mm_per_hour_to_inches(self) -> None:
        eta = datetime(2026, 1, 1, tzinfo=timezone.utc)
        http = FakeHttpClient(
            {
                "hourly": [
                    {
                        "dt": int(eta.timestamp()),
                        "wind_speed": 30,
                        "rain": {"1h": 25.4},
                        "snow": {"1h": 12.7},
                        "temp": 45,
                        "weather": [{"description": "mixed precipitation"}],
                    }
                ]
            }
        )
        client = OpenWeatherClient(api_key="secret", http_client=http)

        result = client.forecast_at(Coordinate(0, 0), eta)

        self.assertAlmostEqual(result.rain_in_per_hour, 1.0)
        self.assertAlmostEqual(result.snow_in_per_hour, 0.5)
        self.assertEqual(result.wind_mph, 30)
        self.assertEqual(http.calls[0][1]["units"], "imperial")


class RouteSamplingTests(TestCase):
    def test_samples_route_and_interpolates_eta(self) -> None:
        route = ProviderRoute(
            route_id="one",
            geometry=(Coordinate(0, 0), Coordinate(1, 0)),
            distance_meters=100 * METERS_PER_MILE,
            duration_seconds=7_200,
            segment_distances_meters=(100 * METERS_PER_MILE,),
            segment_durations_seconds=(7_200,),
        )
        departure = datetime(2026, 1, 1, tzinfo=timezone.utc)

        result = sample_route(route, departure_time=departure, interval_miles=50)

        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[1].coordinate.longitude, 0.5)
        self.assertEqual((result[1].eta - departure).total_seconds(), 3_600)
        self.assertEqual(result[-1].segment_distance_miles, 0)
