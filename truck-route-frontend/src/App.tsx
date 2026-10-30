import { useCallback, useRef, useState } from "react";
import { calculateRoutes, getApiErrorMessage } from "./api/routes";
import { ForecastSlider } from "./components/ForecastSlider";
import { RouteForm } from "./components/RouteForm";
import { RouteIcon } from "./components/icons";
import { SummaryPanel } from "./components/SummaryPanel";
import { WeatherMap } from "./components/WeatherMap";
import type {
  RouteCalculationRequest,
  RouteCalculationResponse,
} from "./types/routing";

export default function App() {
  const [result, setResult] = useState<RouteCalculationResponse | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [forecastHour, setForecastHour] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestController = useRef<AbortController | null>(null);

  const cancelActiveRequest = useCallback(() => {
    requestController.current?.abort();
    requestController.current = null;
  }, []);

  async function handleCalculate(request: RouteCalculationRequest) {
    cancelActiveRequest();
    const controller = new AbortController();
    requestController.current = controller;
    setLoading(true);
    setError(null);

    try {
      const response = await calculateRoutes(request, controller.signal);
      setResult(response);
      setSelectedRouteId(response.recommended_route_id ?? response.routes[0]?.id ?? null);
      setForecastHour(0);
    } catch (requestError) {
      if (controller.signal.aborted) return;
      setError(getApiErrorMessage(requestError));
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
        setLoading(false);
      }
    }
  }

  return (
    <div className="min-h-screen bg-[#07111f] text-slate-100">
      <header className="border-b border-white/8 bg-slate-950/75 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-emerald-400 text-slate-950 shadow-[0_0_30px_rgba(49,214,163,0.16)]">
              <RouteIcon className="size-5" />
            </div>
            <div>
              <h1 className="text-base font-extrabold tracking-tight text-white">HaulCast</h1>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                Weather-aware routing
              </p>
            </div>
          </div>
          <div
            className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold ${
              result?.data_source === "mock"
                ? "border-amber-300/15 bg-amber-400/[0.06] text-amber-200"
                : "border-white/8 bg-white/[0.035] text-slate-400"
            }`}
            title={result?.mock_reason ?? undefined}
          >
            <span className="relative flex size-2">
              <span
                className={`absolute inline-flex size-full animate-ping rounded-full opacity-50 ${
                  result?.data_source === "mock" ? "bg-amber-400" : "bg-emerald-400"
                }`}
              />
              <span
                className={`relative inline-flex size-2 rounded-full ${
                  result?.data_source === "mock" ? "bg-amber-400" : "bg-emerald-400"
                }`}
              />
            </span>
            {result?.data_source === "mock" ? "Development mock active" : "Risk engine online"}
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1800px] grid-cols-1 gap-4 p-4 sm:p-5 xl:grid-cols-[390px_minmax(0,1fr)]">
        <aside className="flex min-w-0 flex-col gap-4">
          <RouteForm
            loading={loading}
            error={error}
            onSubmit={handleCalculate}
            onCancel={cancelActiveRequest}
          />
          <SummaryPanel
            routes={result?.routes ?? []}
            recommendedRouteId={result?.recommended_route_id ?? null}
            selectedRouteId={selectedRouteId}
            recommendationSummary={result?.recommendation_summary ?? ""}
            departureTime={result?.request.departure_time ?? null}
            forecastHour={forecastHour}
            onSelectRoute={setSelectedRouteId}
          />
        </aside>

        <div className="map-frame flex min-h-[690px] min-w-0 flex-col overflow-hidden">
          <WeatherMap
            routes={result?.routes ?? []}
            selectedRouteId={selectedRouteId}
            recommendedRouteId={result?.recommended_route_id ?? null}
            departureTime={result?.request.departure_time ?? null}
            forecastHour={forecastHour}
            onSelectRoute={setSelectedRouteId}
          />
          <ForecastSlider
            departureTime={result?.request.departure_time ?? null}
            value={forecastHour}
            onChange={setForecastHour}
          />
        </div>
      </main>

      <footer className="mx-auto flex max-w-[1800px] flex-col gap-2 px-5 pb-5 text-[10px] text-slate-600 sm:flex-row sm:items-center sm:justify-between">
        <p>Decision support only. Drivers and dispatchers remain responsible for safe operation.</p>
        <p>Map data © OpenStreetMap contributors</p>
      </footer>
    </div>
  );
}
