import os
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from routing.external_services import ProviderAuthenticationError
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
                raise ProviderAuthenticationError("rejected")

        class StubMockService:
            def calculate(self, **kwargs):
                return {"data_source": "mock"}

        service = CredentialFallbackRoutePlanningService(
            RejectedLiveService(),
            StubMockService(),
        )

        result = service.calculate(origin="A")

        self.assertEqual(result["data_source"], "mock")

    def test_auto_mode_uses_mock_when_credentials_are_missing(self) -> None:
        with patch.dict(
            os.environ,
            {"ROUTING_MOCK_MODE": "auto"},
            clear=True,
        ):
            service = build_route_calculation_service()

        self.assertIsInstance(service, MockRoutePlanningService)

    def test_always_mode_uses_mock_even_when_credentials_exist(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ROUTING_MOCK_MODE": "always",
                "MAPBOX_API_KEY": "mapbox-key",
                "OPENWEATHER_API_KEY": "weather-key",
            },
            clear=True,
        ):
            service = build_route_calculation_service()

        self.assertIsInstance(service, MockRoutePlanningService)

    def test_auto_mode_wraps_live_service_for_rejected_credentials(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ROUTING_MOCK_MODE": "auto",
                "MAPBOX_API_KEY": "mapbox-key",
                "OPENWEATHER_API_KEY": "weather-key",
            },
            clear=True,
        ):
            service = build_route_calculation_service()

        self.assertIsInstance(service, CredentialFallbackRoutePlanningService)

    def test_mapbox_api_key_alias_counts_as_configured(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MAPBOX_API_KEY": "mapbox-key",
                "OPENWEATHER_API_KEY": "weather-key",
            },
            clear=True,
        ):
            missing = missing_provider_credentials()

        self.assertEqual(missing, [])
