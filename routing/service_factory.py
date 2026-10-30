"""Select live or deterministic mock route planning from environment settings."""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from django.conf import settings

from .external_services import ConfigurationError, ProviderAccessError
from .mock_services import MockRoutePlanningService
from .route_planning import RoutePlanningService


logger = logging.getLogger(__name__)


class RouteCalculator(Protocol):
    def calculate(self, **kwargs: Any) -> dict[str, Any]: ...


class CredentialFallbackRoutePlanningService:
    """Retry only credential-authentication failures with deterministic mock data."""

    def __init__(
        self,
        live_service: RoutePlanningService,
        mock_service_factory: Callable[[str], RouteCalculator] | None = None,
    ) -> None:
        self.live_service = live_service
        self.mock_service_factory = mock_service_factory or (
            lambda reason: MockRoutePlanningService.from_env(reason=reason)
        )

    def calculate(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.live_service.calculate(**kwargs)
        except ProviderAccessError as exc:
            logger.warning(
                "Provider access denied: provider=%s status=%s detail=%s",
                exc.provider,
                exc.status_code,
                exc.detail,
            )
            reason = (
                "Development mock data is active because "
                f"{exc.provider} denied API access with HTTP "
                f"{exc.status_code}: {exc.detail}"
            )
            return self.mock_service_factory(reason).calculate(**kwargs)


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
        return CredentialFallbackRoutePlanningService(live_service)
    return live_service


def routing_mock_mode() -> str:
    mode = str(settings.ROUTING_MOCK_MODE).strip().casefold()
    if mode not in {"auto", "always", "never"}:
        raise ConfigurationError(
            "ROUTING_MOCK_MODE must be one of: auto, always, never."
        )
    return mode


def missing_provider_credentials() -> list[str]:
    missing: list[str] = []
    if not settings.MAPBOX_ACCESS_TOKEN:
        missing.append("MAPBOX_ACCESS_TOKEN/MAPBOX_API_KEY/MAPBOX_TOKEN")
    if not settings.OPENWEATHER_API_KEY:
        missing.append("OPENWEATHER_API_KEY/OPENWEATHERMAP_API_KEY")
    return missing
