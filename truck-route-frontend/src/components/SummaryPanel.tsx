import type { RouteResult } from "../types/routing";
import { checkpointNearestHour, forecastAtHour } from "../utils/forecast";
import {
  formatDateTime,
  formatDuration,
  RISK_TEXT_CLASSES,
  ROUTE_COLORS,
} from "../utils/format";
import { AlertIcon, CheckIcon, ChevronIcon, ClockIcon } from "./icons";

interface SummaryPanelProps {
  routes: RouteResult[];
  recommendedRouteId: string | null;
  selectedRouteId: string | null;
  recommendationSummary: string;
  departureTime: string | null;
  forecastHour: number;
  onSelectRoute: (routeId: string) => void;
}

export function SummaryPanel({
  routes,
  recommendedRouteId,
  selectedRouteId,
  recommendationSummary,
  departureTime,
  forecastHour,
  onSelectRoute,
}: SummaryPanelProps) {
  if (routes.length === 0) {
    return <PlanningGuide />;
  }

  return (
    <section className="panel-shell overflow-hidden" aria-labelledby="recommendation-title">
      <div className="border-b border-white/8 px-5 py-4">
        <p className="eyebrow">Dispatch recommendation</p>
        <h2 id="recommendation-title" className="mt-1 text-lg font-semibold text-white">
          {recommendedRouteId ? "Safest route identified" : "No safe route available"}
        </h2>
        <p className="mt-2 text-xs leading-5 text-slate-400">{recommendationSummary}</p>
      </div>

      <div className="space-y-3 p-3">
        {routes.map((route, index) => {
          const recommended = route.id === recommendedRouteId;
          const selected = route.id === selectedRouteId;
          const rejected = route.decision.status === "rejected";
          const activeCheckpoint = checkpointNearestHour(
            route.checkpoints,
            departureTime,
            forecastHour,
          );
          const activeForecast = activeCheckpoint
            ? forecastAtHour(activeCheckpoint, forecastHour)
            : null;
          return (
            <button
              type="button"
              key={route.id}
              onClick={() => onSelectRoute(route.id)}
              className={`route-card w-full text-left ${
                selected ? "border-white/20 bg-white/[0.065]" : "border-white/8 bg-white/[0.025]"
              }`}
            >
              <div className="flex items-start gap-3">
                <span
                  className="mt-1 h-10 w-1 shrink-0 rounded-full"
                  style={{ backgroundColor: ROUTE_COLORS[index % ROUTE_COLORS.length] }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-bold text-white">{route.name}</h3>
                        {recommended && (
                          <span className="status-badge bg-emerald-400/12 text-emerald-300 ring-emerald-300/20">
                            <CheckIcon className="size-3" /> Recommended
                          </span>
                        )}
                        {rejected && (
                          <span className="status-badge bg-red-400/10 text-red-300 ring-red-300/20">
                            <AlertIcon className="size-3" /> Rejected
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        {route.distance_miles.toFixed(0)} mi · Arrive {formatDateTime(route.arrival_time)}
                      </p>
                    </div>
                    <ChevronIcon className={`size-4 shrink-0 text-slate-500 transition ${selected ? "rotate-90 text-slate-300" : ""}`} />
                  </div>

                  <div className="mt-3 grid grid-cols-3 divide-x divide-white/8 rounded-lg border border-white/6 bg-black/10 py-2">
                    <Metric label="Travel" value={formatDuration(route.duration_seconds)} />
                    <Metric label="Severe" value={`${route.ranking.severe_miles.toFixed(1)} mi`} tone={route.ranking.severe_miles > 0 ? "danger" : undefined} />
                    <Metric label="High" value={`${route.ranking.high_miles.toFixed(1)} mi`} tone={route.ranking.high_miles > 0 ? "warning" : undefined} />
                  </div>

                  {activeForecast && activeCheckpoint && (
                    <div
                      className="mt-2 rounded-lg border border-sky-300/10 bg-sky-400/[0.045] px-3 py-2"
                      data-forecast-hour={forecastHour}
                      aria-live="polite"
                    >
                      <div className="flex items-center justify-between gap-3 text-[10px] font-semibold uppercase tracking-[0.11em] text-sky-200/65">
                        <span>+{forecastHour}h · CP {activeCheckpoint.sequence}</span>
                        <span>{formatDateTime(activeForecast.weather.forecast_time)}</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-300">
                        <span className="capitalize">{activeForecast.weather.description || "No description"}</span>
                        {" · "}{activeForecast.weather.temperature_f == null
                          ? "—"
                          : `${activeForecast.weather.temperature_f.toFixed(0)}°F`}
                        {" · "}{activeForecast.weather.wind_mph.toFixed(0)} mph wind
                        {" · "}{activeForecast.risk.overall} risk
                      </p>
                    </div>
                  )}

                  {selected && (
                    <div className="mt-3 border-t border-white/8 pt-3">
                      <p className="text-xs leading-5 text-slate-300">{route.decision.reason}</p>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {highestRisks(route).map((risk) => (
                          <span key={risk} className={`risk-pill ${RISK_TEXT_CLASSES[risk]}`}>
                            {risk}
                          </span>
                        ))}
                        <span className="risk-pill bg-sky-400/8 text-sky-200 ring-sky-300/15">
                          Avg risk {route.ranking.average_risk.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "danger" | "warning";
}) {
  const toneClass = tone === "danger" ? "text-red-300" : tone === "warning" ? "text-orange-200" : "text-white";
  return (
    <div className="px-2 text-center">
      <p className="text-[9px] font-semibold uppercase tracking-[0.13em] text-slate-600">{label}</p>
      <p className={`mt-1 text-xs font-bold ${toneClass}`}>{value}</p>
    </div>
  );
}

function highestRisks(route: RouteResult) {
  return Array.from(new Set(route.checkpoints.map((checkpoint) => checkpoint.risk.overall)));
}

function PlanningGuide() {
  return (
    <section className="panel-shell p-5">
      <p className="eyebrow">How ranking works</p>
      <h2 className="mt-1 text-lg font-semibold text-white">Safety before speed</h2>
      <ol className="mt-4 space-y-3">
        {[
          ["01", "Fewest Severe miles", "Avoid the most dangerous exposure first."],
          ["02", "Fewest High miles", "Reduce sustained elevated-risk travel."],
          ["03", "Lowest average risk", "Compare conditions across the full route."],
          ["04", "Shortest travel time", "Use ETA only after safety ties."],
        ].map(([number, title, description]) => (
          <li key={number} className="flex gap-3">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-white/5 text-[10px] font-bold text-emerald-300 ring-1 ring-white/8">
              {number}
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-200">{title}</p>
              <p className="mt-0.5 text-xs leading-5 text-slate-500">{description}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-5 flex items-start gap-2 rounded-xl border border-sky-300/10 bg-sky-400/[0.045] p-3 text-xs leading-5 text-sky-100/70">
        <ClockIcon className="mt-0.5 size-4 shrink-0 text-sky-300" />
        Weather is evaluated at each checkpoint’s projected arrival time, not at departure.
      </div>
    </section>
  );
}
