from io import BytesIO
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

from routing.external_services import (
    Coordinate,
    JsonHttpClient,
    MapboxClient,
    OpenWeatherClient,
    ProviderAccessError,
    ProviderRoute,
)
from routing.route_planning import METERS_PER_MILE, sample_route


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, provider, params, timeout_seconds):
        self.calls.append((url, provider, params, timeout_seconds))
        return self.payload


class ProviderParsingTests(TestCase):
    @staticmethod
    def route_payload(distance=1_000, duration=100):
        return {
            "geometry": {"coordinates": [[0, 0], [1, 1]]},
            "distance": distance,
            "duration": duration,
            "legs": [
                {
                    "annotation": {
                        "distance": [distance],
                        "duration": [duration],
                    }
                }
            ],
        }

    def test_mapbox_requests_and_parses_three_routes(self) -> None:
        route = self.route_payload()
        http = FakeHttpClient({"code": "Ok", "uuid": "abc", "routes": [route] * 3})
        client = MapboxClient(access_token="secret", http_client=http)

        result = client.get_route_options(
            Coordinate(0, 0),
            Coordinate(1, 1),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].route_id, "abc-1")
        self.assertEqual(http.calls[0][1], "Mapbox")
        self.assertEqual(http.calls[0][2]["alternatives"], "true")
        self.assertEqual(http.calls[0][2]["geometries"], "geojson")

    def test_mapbox_synthesizes_third_route_from_second_route(self) -> None:
        http = FakeHttpClient(
            {
                "code": "Ok",
                "uuid": "abc",
                "routes": [
                    self.route_payload(distance=1_000, duration=100),
                    self.route_payload(distance=1_200, duration=120),
                ],
            }
        )
        client = MapboxClient(access_token="secret", http_client=http)

        result = client.get_route_options(
            Coordinate(0, 0),
            Coordinate(1, 1),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(len(result), 3)
        self.assertEqual(result[2].route_id, "abc-2-alt3")
        self.assertEqual(result[2].geometry, result[1].geometry)
        self.assertAlmostEqual(result[2].distance_meters, 1_260)
        self.assertAlmostEqual(result[2].duration_seconds, 126)
        self.assertAlmostEqual(
            sum(result[2].segment_distances_meters),
            result[2].distance_meters,
        )
        self.assertAlmostEqual(
            sum(result[2].segment_durations_seconds),
            result[2].duration_seconds,
        )

    def test_mapbox_synthesizes_two_routes_from_single_route(self) -> None:
        route = self.route_payload(distance=1_000, duration=100)
        http = FakeHttpClient({"code": "Ok", "uuid": "abc", "routes": [route]})
        client = MapboxClient(access_token="secret", http_client=http)

        result = client.get_route_options(
            Coordinate(0, 0),
            Coordinate(1, 1),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(len(result), 3)
        self.assertEqual(
            [item.route_id for item in result],
            ["abc-1", "abc-1-alt2", "abc-1-alt3"],
        )
        self.assertEqual(result[1].geometry, result[0].geometry)
        self.assertEqual(result[2].geometry, result[0].geometry)
        self.assertAlmostEqual(result[1].distance_meters, 1_050)
        self.assertAlmostEqual(result[1].duration_seconds, 105)
        self.assertAlmostEqual(result[2].distance_meters, 1_100)
        self.assertAlmostEqual(result[2].duration_seconds, 110)

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
        self.assertEqual(http.calls[0][1], "OpenWeather")
        self.assertEqual(http.calls[0][2]["units"], "imperial")


class ProviderAccessErrorTests(TestCase):
    def test_http_authentication_error_preserves_provider_and_body(self) -> None:
        error = HTTPError(
            "https://api.example.test/resource",
            401,
            "Unauthorized",
            {},
            BytesIO(b'{"message":"API key has no access to this product"}'),
        )

        with patch("routing.external_services.urlopen", side_effect=error):
            with self.assertRaises(ProviderAccessError) as context:
                JsonHttpClient().get_json(
                    "https://api.example.test/resource",
                    provider="OpenWeather",
                    params={"appid": "secret"},
                    timeout_seconds=5,
                )

        self.assertEqual(context.exception.provider, "OpenWeather")
        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(
            context.exception.raw_response_body,
            '{"message":"API key has no access to this product"}',
        )
        self.assertEqual(
            context.exception.detail,
            "API key has no access to this product",
        )


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
