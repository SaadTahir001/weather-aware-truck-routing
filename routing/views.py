import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .external_services import (
    ConfigurationError,
    ExternalServiceError,
    ForecastUnavailableError,
    InsufficientRoutesError,
    LocationNotFoundError,
)
from .route_planning import RouteSizeLimitError
from .service_factory import RouteCalculator, build_route_calculation_service
from .serializers import (
    RouteCalculationRequestSerializer,
    RouteCalculationResponseSerializer,
)


logger = logging.getLogger(__name__)


class RouteCalculationView(APIView):
    """Generate, weather-enrich, score, and rank three route candidates."""

    service_factory = staticmethod(build_route_calculation_service)

    def get_service(self) -> RouteCalculator:
        return self.service_factory()

    def post(self, request):
        request_serializer = RouteCalculationRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        try:
            result = self.get_service().calculate(**request_serializer.validated_data)
        except LocationNotFoundError as exc:
            return _error_response("location_not_found", str(exc), status.HTTP_400_BAD_REQUEST)
        except ForecastUnavailableError as exc:
            return _error_response(
                "forecast_unavailable", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        except RouteSizeLimitError as exc:
            return _error_response(
                "route_too_large", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        except InsufficientRoutesError as exc:
            return _error_response(
                "insufficient_routes", str(exc), status.HTTP_502_BAD_GATEWAY
            )
        except ConfigurationError:
            logger.exception("Route API server configuration is invalid")
            return _error_response(
                "service_not_configured",
                "The route calculation service is not configured.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ExternalServiceError:
            logger.exception("A route calculation provider failed")
            return _error_response(
                "provider_error",
                "A routing or weather provider failed. Please retry later.",
                status.HTTP_502_BAD_GATEWAY,
            )

        response_serializer = RouteCalculationResponseSerializer(result)
        response = Response(response_serializer.data, status=status.HTTP_200_OK)
        response["X-Routing-Data-Source"] = result["data_source"]
        return response


def _error_response(code: str, detail: str, http_status: int) -> Response:
    return Response(
        {"error": {"code": code, "detail": detail}},
        status=http_status,
    )
