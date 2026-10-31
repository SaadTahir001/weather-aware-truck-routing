import { useEffect } from "react";
import type { RouteResult } from "../types/routing";
import {
  checkpointNearestHour,
  forecastAtHour,
  logLiveRoutePayload,
} from "../utils/forecast";
import {
  formatDateTime,
  formatDuration,
  PALETTE,
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
  useEffect(() => {
    routes.forEach(logLiveRoutePayload);
  }, [routes]);

  if (routes.length === 0) {
    return <PlanningGuide />;
  }

  return (
    <section className="panel-shell overflow-hidden" aria-labelledby="recommendation-title">
      <div className="border-b border-[#0297DE]/20 px-5 py-4">
        <p className="eyebrow">Dispatch recommendation</p>
        <h2 id="recommendation-title" className="mt-1 text-lg font-semibold text-slate-50">
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
                selected
                  ? "border-[#FC794D]/60 bg-[#FC794D]/[0.07] shadow-[0_0_0_1px_rgba(252,121,77,0.18),0_0_24px_rgba(252,121,77,0.12)]"
                  : "border-[#0297DE]/20 bg-[#0B1218]/70"
              }`}
            >
              <div className="flex items-start gap-3">
                <span
                  className="mt-1 h-10 w-1 shrink-0 rounded-full"
                  style={{
                    backgroundColor: recommended
                      ? PALETTE.priority
                      : selected
                        ? PALETTE.blue
                        : ROUTE_COLORS[index % ROUTE_COLORS.length],
                  }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-bold text-slate-50">{route.name}</h3>
                        {recommended && (
                          <span className="status-badge bg-emerald-500/14 text-emerald-200 ring-emerald-400/35 shadow-[0_0_18px_rgba(16,185,129,0.16)]">
                            <CheckIcon className="size-3" /> Recommended
                          </span>
                        )}
                        {rejected && (
                          <span className="status-badge bg-[#02070A] text-red-300 ring-red-500/45">
                            <AlertIcon className="size-3" /> Rejected
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        {route.distance_miles.toFixed(0)} mi · Arrive {formatDateTime(route.arrival_time)}
                      </p>
                    </div>
                    <ChevronIcon className={`size-4 shrink-0 text-slate-600 transition ${selected ? "rotate-90 text-[#0297DE]" : ""}`} />
                  </div>

                  <div className="mt-3 grid grid-cols-3 divide-x divide-slate-700/60 rounded-lg border border-slate-700/60 bg-[#131C26]/85 py-2 shadow-[inset_0_1px_rgba(255,255,255,0.025)]">
                    <Metric label="Travel" value={formatDuration(route.duration_seconds)} />
                    <Metric label="Severe" value={`${route.ranking.severe_miles.toFixed(1)} mi`} tone={route.ranking.severe_miles > 0 ? "danger" : undefined} />
                    <Metric label="High" value={`${route.ranking.high_miles.toFixed(1)} mi`} tone={route.ranking.high_miles > 0 ? "warning" : undefined} />
                  </div>

                  {activeForecast && activeCheckpoint && (
                    <div
                      className="mt-2 rounded-lg border border-[#0297DE]/35 bg-[#131C26]/90 px-3 py-2 shadow-[0_0_16px_rgba(2,151,222,0.07)]"
                      data-forecast-hour={forecastHour}
                      aria-live="polite"
                    >
                      <div className="flex items-center justify-between gap-3 text-[10px] font-semibold uppercase tracking-[0.11em] text-[#0297DE]">
                        <span>+{forecastHour}h · CP {activeCheckpoint.sequence}</span>
                        <span className="text-[#FC734D]">{formatDateTime(activeForecast.weather.forecast_time)}</span>
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
                    <div className="mt-3 border-t border-slate-800 pt-3">
                      <p className="text-xs leading-5 text-slate-300">{route.decision.reason}</p>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {highestRisks(route).map((risk) => (
                          <span key={risk} className={`risk-pill ${RISK_TEXT_CLASSES[risk]}`}>
                            {risk}
                          </span>
                        ))}
                        <span className="risk-pill bg-[#0297DE]/12 text-slate-100 ring-[#0297DE]/40">
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
  const toneClass = tone === "danger"
    ? "text-red-300"
    : tone === "warning"
      ? "text-[#FC794D]"
      : "text-slate-50";
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
      <h2 className="mt-1 text-lg font-semibold text-slate-50">Safety before speed</h2>
      <ol className="mt-4 space-y-3">
        {[
          ["01", "Fewest Severe miles", "Avoid the most dangerous exposure first."],
          ["02", "Fewest High miles", "Reduce sustained elevated-risk travel."],
          ["03", "Lowest average risk", "Compare conditions across the full route."],
          ["04", "Shortest travel time", "Use ETA only after safety ties."],
        ].map(([number, title, description]) => (
          <li key={number} className="flex gap-3">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-[#0297DE]/14 text-[10px] font-bold text-[#0297DE] ring-1 ring-[#0297DE]/35">
              {number}
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-200">{title}</p>
              <p className="mt-0.5 text-xs leading-5 text-slate-500">{description}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-5 flex items-start gap-2 rounded-xl border border-[#0297DE]/30 bg-[#0297DE]/8 p-3 text-xs leading-5 text-slate-300">
        <ClockIcon className="mt-0.5 size-4 shrink-0 text-[#0297DE]" />
        Weather is evaluated at each checkpoint’s projected arrival time, not at departure.
      </div>
    </section>
  );
}
