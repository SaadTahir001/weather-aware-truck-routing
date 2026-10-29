import axios from "axios";
import type {
  ApiErrorEnvelope,
  RouteCalculationRequest,
  RouteCalculationResponse,
} from "../types/routing";

const parsedTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 120_000);

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || undefined,
  timeout: Number.isFinite(parsedTimeout) ? parsedTimeout : 120_000,
  headers: {
    "Content-Type": "application/json",
  },
});

export async function calculateRoutes(
  request: RouteCalculationRequest,
  signal?: AbortSignal,
): Promise<RouteCalculationResponse> {
  const response = await api.post<RouteCalculationResponse>(
    "/api/routes/calculate/",
    request,
    { signal },
  );
  return response.data;
}

export function getApiErrorMessage(error: unknown): string {
  if (!axios.isAxiosError<ApiErrorEnvelope>(error)) {
    return "Something unexpected happened. Please try again.";
  }
  if (error.code === "ERR_CANCELED") {
    return "Route calculation was canceled.";
  }
  const detail = error.response?.data?.error?.detail;
  if (detail) return detail;

  const validationPayload = error.response?.data;
  if (validationPayload && typeof validationPayload === "object") {
    const firstValidationError = Object.values(validationPayload).find(
      (value) => Array.isArray(value) && typeof value[0] === "string",
    );
    if (Array.isArray(firstValidationError)) return firstValidationError[0];
  }

  if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT") {
    return "The calculation timed out while waiting for route or weather data.";
  }
  if (!error.response) {
    return "Could not reach the routing service. Check the backend and network connection.";
  }
  return `Route calculation failed with status ${error.response.status}.`;
}
