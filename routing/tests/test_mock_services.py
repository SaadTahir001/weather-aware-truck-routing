import os
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from django.test import override_settings

from config.settings import env_secret
from routing.external_services import ProviderAccessError
from routing.mock_services import MockRoutePlanningService
from routing.service_factory import (
    CredentialFallbackRoutePlanningService,
    build_route_calculation_service,
    missing_provider_credentials,
)


class MockRoutePlanningTests(TestCase):
    def test_returns_three_distinct_routes_and_frontend_ready_data(self) -> None:
        service = MockRoutePlanningService(
            reason="test",
            checkpoint_interval_miles=50,
        )

        result = service.calculate(
            origin="Chicago, IL",
            destination="Detroit, MI",
            departure_time=datetime(2026, 11, 2, 14, tzinfo=timezone.utc),
            load_weight_lb=36_000,
        )

        self.assertEqual(result["data_source"], "mock")
        self.assertEqual(len(result["routes"]), 3)
        self.assertEqual(len({route["id"] for route in result["routes"]}), 3)
        self.assertEqual(
            len(
                {
                    tuple(tuple(point) for point in route["geometry"]["coordinates"])
                    for route in result["routes"]
                }
            ),
            3,
        )
        self.assertTrue(all(route["checkpoints"] for route in result["routes"]))
        self.assertIsNotNone(result["recommended_route_id"])
        self.assertIn(
            "rejected",
            {route["decision"]["status"] for route in result["routes"]},
        )

    def test_unknown_places_get_repeatable_mock_coordinates(self) -> None:
        service = MockRoutePlanningService(reason="test")
        request = {
            "origin": "Warehouse Alpha",
            "destination": "Warehouse Omega",
            "departure_time": datetime(2026, 6, 1, tzinfo=timezone.utc),
            "load_weight_lb": 20_000,
        }

        first = service.calculate(**request)
        second = service.calculate(**request)

        self.assertEqual(first["resolved_locations"], second["resolved_locations"])


class ServiceFactoryTests(TestCase):
    def test_rejected_live_credential_uses_mock_service(self) -> None:
        class RejectedLiveService:
            def calculate(self, **kwargs):
                raise ProviderAccessError(
                    provider="OpenWeather",
                    status_code=401,
                    raw_response_body='{"message":"subscription required"}',
                )

        class StubMockService:
            def __init__(self, reason):
                self.reason = reason

            def calculate(self, **kwargs):
                return {"data_source": "mock", "mock_reason": self.reason}

        service = CredentialFallbackRoutePlanningService(
            RejectedLiveService(),
            lambda reason: StubMockService(reason),
        )

        with self.assertLogs("routing.service_factory", level="WARNING") as logs:
            result = service.calculate(origin="A")

        self.assertEqual(result["data_source"], "mock")
        self.assertIn("OpenWeather", result["mock_reason"])
        self.assertIn("subscription required", result["mock_reason"])
        self.assertIn("provider=OpenWeather", logs.output[0])

    @override_settings(
        ROUTING_MOCK_MODE="auto",
        MAPBOX_ACCESS_TOKEN="",
        OPENWEATHER_API_KEY="",
    )
    def test_auto_mode_uses_mock_when_credentials_are_missing(self) -> None:
        service = build_route_calculation_service()

        self.assertIsInstance(service, MockRoutePlanningService)

    @override_settings(
        ROUTING_MOCK_MODE="always",
        MAPBOX_ACCESS_TOKEN="mapbox-key",
        OPENWEATHER_API_KEY="weather-key",
    )
    def test_always_mode_uses_mock_even_when_credentials_exist(self) -> None:
        service = build_route_calculation_service()

        self.assertIsInstance(service, MockRoutePlanningService)

    @override_settings(
        ROUTING_MOCK_MODE="auto",
        MAPBOX_ACCESS_TOKEN="mapbox-key",
        OPENWEATHER_API_KEY="weather-key",
    )
    def test_auto_mode_wraps_live_service_for_rejected_credentials(self) -> None:
        service = build_route_calculation_service()

        self.assertIsInstance(service, CredentialFallbackRoutePlanningService)

    @override_settings(
        MAPBOX_ACCESS_TOKEN="mapbox-key",
        OPENWEATHER_API_KEY="weather-key",
    )
    def test_configured_provider_credentials_are_not_missing(self) -> None:
        self.assertEqual(missing_provider_credentials(), [])

    def test_env_secret_strips_and_uses_fallback_names(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MAPBOX_ACCESS_TOKEN": "   ",
                "MAPBOX_API_KEY": "  mapbox-key  ",
            },
            clear=True,
        ):
            value = env_secret(
                "MAPBOX_ACCESS_TOKEN",
                "MAPBOX_API_KEY",
                "MAPBOX_TOKEN",
            )

        self.assertEqual(value, "mapbox-key")
