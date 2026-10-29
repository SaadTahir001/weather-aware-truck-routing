"""Select live or deterministic mock route planning from environment settings."""

from __future__ import annotations

import os
from typing import Any, Protocol

from .external_services import ConfigurationError, ProviderAuthenticationError
from .mock_services import MockRoutePlanningService
from .route_planning import RoutePlanningService


class RouteCalculator(Protocol):
    def calculate(self, **kwargs: Any) -> dict[str, Any]: ...


class CredentialFallbackRoutePlanningService:
    """Retry only credential-authentication failures with deterministic mock data."""

    def __init__(
        self,
        live_service: RoutePlanningService,
        mock_service: MockRoutePlanningService,
    ) -> None:
        self.live_service = live_service
        self.mock_service = mock_service

    def calculate(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.live_service.calculate(**kwargs)
        except ProviderAuthenticationError:
            return self.mock_service.calculate(**kwargs)


def build_route_calculation_service() -> RouteCalculator:
    """
    Build the configured service.

    ROUTING_MOCK_MODE values:
      - auto (default): mock only for missing or provider-rejected credentials.
      - always: never call providers; always return deterministic mock data.
      - never: require valid live credentials and propagate provider failures.
    """

    mode = routing_mock_mode()
    if mode == "always":
        return MockRoutePlanningService.from_env(
            reason="Mock mode was forced by ROUTING_MOCK_MODE=always."
        )

    missing = missing_provider_credentials()
    if mode == "auto" and missing:
        return MockRoutePlanningService.from_env(
            reason=(
                "Development mock data is active because these credentials are "
                f"missing: {', '.join(missing)}."
            )
        )

    live_service = RoutePlanningService.from_env()
    if mode == "auto":
        return CredentialFallbackRoutePlanningService(
            live_service,
            MockRoutePlanningService.from_env(
                reason=(
                    "Development mock data is active because a provider rejected "
                    "its API credential."
                )
            ),
        )
    return live_service


def routing_mock_mode() -> str:
    mode = os.getenv("ROUTING_MOCK_MODE", "auto").strip().casefold()
    if mode not in {"auto", "always", "never"}:
        raise ConfigurationError(
            "ROUTING_MOCK_MODE must be one of: auto, always, never."
        )
    return mode


def missing_provider_credentials() -> list[str]:
    missing: list[str] = []
    if not (os.getenv("MAPBOX_ACCESS_TOKEN") or os.getenv("MAPBOX_API_KEY")):
        missing.append("MAPBOX_ACCESS_TOKEN/MAPBOX_API_KEY")
    if not os.getenv("OPENWEATHER_API_KEY"):
        missing.append("OPENWEATHER_API_KEY")
    return missing
