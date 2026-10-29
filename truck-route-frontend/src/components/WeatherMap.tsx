import { useEffect, useMemo } from "react";
import { latLngBounds, type LatLngExpression } from "leaflet";
import {
  Circle,
  CircleMarker,
  MapContainer,
  Pane,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import type { Checkpoint, RiskLevel, RouteResult } from "../types/routing";
import {
  formatDateTime,
  formatDuration,
  RISK_COLORS,
  riskScore,
  ROUTE_COLORS,
} from "../utils/format";
import { RainIcon, TemperatureIcon, WindIcon } from "./icons";

interface WeatherMapProps {
  routes: RouteResult[];
  selectedRouteId: string | null;
  recommendedRouteId: string | null;
  departureTime: string | null;
  forecastHour: number;
  onSelectRoute: (routeId: string) => void;
}

const DEFAULT_CENTER: LatLngExpression = [39.5, -98.35];

export function WeatherMap({
  routes,
  selectedRouteId,
  recommendedRouteId,
  departureTime,
  forecastHour,
  onSelectRoute,
}: WeatherMapProps) {
  const selectedRoute = routes.find((route) => route.id === selectedRouteId) ?? null;

  return (
    <section className="relative min-h-[520px] flex-1 overflow-hidden bg-[#09131f]">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={4}
        minZoom={3}
        className="h-full min-h-[520px] w-full"
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          className="map-tiles"
        />
        <FitRouteBounds routes={routes} />
        <Pane name="weather-heat" style={{ zIndex: 390 }}>
          {routes
            .filter((route) => route.id === selectedRouteId)
            .flatMap((route) =>
              route.checkpoints.map((checkpoint) => {
                const timeDistance = checkpointTimeDistance(
                  checkpoint,
                  departureTime,
                  forecastHour,
                );
                const temporalOpacity = Math.max(0.02, 0.15 - timeDistance * 0.017);
                return (
                  <Circle
                    key={`heat-${route.id}-${checkpoint.sequence}`}
                    center={[
                      checkpoint.coordinate.latitude,
                      checkpoint.coordinate.longitude,
                    ]}
                    radius={5_000 + riskScore(checkpoint.risk.overall) * 2_500}
                    pathOptions={{
                      color: RISK_COLORS[checkpoint.risk.overall],
                      fillColor: RISK_COLORS[checkpoint.risk.overall],
                      fillOpacity: temporalOpacity,
                      opacity: Math.min(0.2, temporalOpacity + 0.04),
                      weight: 1,
                    }}
                    interactive={false}
                  />
                );
              }),
            )}
        </Pane>

        <Pane name="route-lines" style={{ zIndex: 410 }}>
          {routes.map((route, index) => {
            const selected = route.id === selectedRouteId;
            const recommended = route.id === recommendedRouteId;
            const positions = route.geometry.coordinates.map(
              ([longitude, latitude]) => [latitude, longitude] as LatLngExpression,
            );

            return (
              <Polyline
                key={route.id}
                positions={positions}
                pathOptions={{
                  color: ROUTE_COLORS[index % ROUTE_COLORS.length],
                  weight: selected ? 7 : recommended ? 5 : 4,
                  opacity: selected ? 1 : recommended ? 0.9 : 0.55,
                  dashArray: route.eligible ? undefined : "9 9",
                  lineCap: "round",
                }}
                eventHandlers={{ click: () => onSelectRoute(route.id) }}
              >
                <Tooltip sticky direction="top" opacity={0.95}>
                  <div className="map-tooltip">
                    <strong>{route.name}</strong>
                    <span>{formatDuration(route.duration_seconds)} · {route.distance_miles.toFixed(0)} mi</span>
                  </div>
                </Tooltip>
              </Polyline>
            );
          })}
        </Pane>

        <Pane name="checkpoint-markers" style={{ zIndex: 430 }}>
          {routes.flatMap((route, routeIndex) =>
          route.checkpoints.map((checkpoint) => {
            const selected = route.id === selectedRouteId;
            const timeDistance = checkpointTimeDistance(
              checkpoint,
              departureTime,
              forecastHour,
            );
            const nearSelectedHour = timeDistance <= 3;
            return (
              <CircleMarker
                key={`${route.id}-${checkpoint.sequence}`}
                center={[
                  checkpoint.coordinate.latitude,
                  checkpoint.coordinate.longitude,
                ]}
                radius={selected && nearSelectedHour ? 7 : selected ? 5.5 : 4}
                pathOptions={{
                  color: ROUTE_COLORS[routeIndex % ROUTE_COLORS.length],
                  fillColor: RISK_COLORS[checkpoint.risk.overall],
                  fillOpacity: selected ? 1 : 0.72,
                  opacity: selected ? 1 : 0.7,
                  weight: selected && nearSelectedHour ? 3 : 2,
                }}
                eventHandlers={{ click: () => onSelectRoute(route.id) }}
              >
                <Popup maxWidth={300} minWidth={245}>
                  <CheckpointPopup route={route} checkpoint={checkpoint} />
                </Popup>
              </CircleMarker>
            );
          }),
          )}
        </Pane>
      </MapContainer>

      <MapHeader routes={routes} selectedRoute={selectedRoute} />
      <RiskLegend />
      {routes.length === 0 && <EmptyMapState />}
    </section>
  );
}

function FitRouteBounds({ routes }: { routes: RouteResult[] }) {
  const map = useMap();
  const coordinates = useMemo(
    () =>
      routes.flatMap((route) =>
        route.geometry.coordinates.map(
          ([longitude, latitude]) => [latitude, longitude] as [number, number],
        ),
      ),
    [routes],
  );

  useEffect(() => {
    if (coordinates.length < 2) return;
    map.fitBounds(latLngBounds(coordinates), {
      paddingTopLeft: [45, 90],
      paddingBottomRight: [45, 45],
      maxZoom: 9,
      animate: true,
    });
  }, [coordinates, map]);

  return null;
}

function MapHeader({
  routes,
  selectedRoute,
}: {
  routes: RouteResult[];
  selectedRoute: RouteResult | null;
}) {
  return (
    <div className="pointer-events-none absolute left-4 right-4 top-4 z-[500] flex items-start justify-between gap-3">
      <div className="rounded-xl border border-white/10 bg-slate-950/88 px-3.5 py-2.5 shadow-2xl backdrop-blur-xl">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
          Network weather view
        </p>
        <p className="mt-0.5 text-sm font-semibold text-white">
          {selectedRoute ? selectedRoute.name : routes.length ? "Three route comparison" : "Awaiting trip details"}
        </p>
      </div>
      {routes.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-slate-950/88 px-3.5 py-2.5 text-right shadow-2xl backdrop-blur-xl">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Routes</p>
          <p className="mt-0.5 text-sm font-semibold text-white">{routes.length} analyzed</p>
        </div>
      )}
    </div>
  );
}

function RiskLegend() {
  return (
    <div className="absolute bottom-4 left-4 z-[500] rounded-xl border border-white/10 bg-slate-950/88 p-3 shadow-2xl backdrop-blur-xl">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
        Checkpoint risk
      </p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-5">
        {(Object.keys(RISK_COLORS) as RiskLevel[]).map((level) => (
          <div key={level} className="flex items-center gap-1.5 text-[10px] text-slate-300">
            <span
              className="size-2 rounded-full ring-2 ring-white/8"
              style={{ backgroundColor: RISK_COLORS[level] }}
            />
            {level}
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyMapState() {
  return (
    <div className="pointer-events-none absolute inset-0 z-[450] grid place-items-center p-6">
      <div className="max-w-sm rounded-2xl border border-white/10 bg-slate-950/82 p-6 text-center shadow-2xl backdrop-blur-xl">
        <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-emerald-400/10 ring-1 ring-emerald-300/20">
          <span className="size-3 rounded-full bg-emerald-300 shadow-[0_0_0_8px_rgba(52,211,153,0.08)]" />
        </div>
        <h3 className="mt-4 text-base font-semibold text-white">Your route intelligence map</h3>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          Enter a trip to compare three routes, inspect weather at each ETA, and identify No Travel segments before dispatch.
        </p>
      </div>
    </div>
  );
}

function CheckpointPopup({
  route,
  checkpoint,
}: {
  route: RouteResult;
  checkpoint: Checkpoint;
}) {
  const weatherDescription = checkpoint.weather.description || "No description";
  return (
    <div className="checkpoint-popup">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
            {route.name} · CP {checkpoint.sequence}
          </p>
          <p className="mt-1 text-sm font-bold text-slate-900">{formatDateTime(checkpoint.eta)}</p>
        </div>
        <span
          className="rounded-full px-2 py-1 text-[10px] font-bold text-white"
          style={{ backgroundColor: RISK_COLORS[checkpoint.risk.overall] }}
        >
          {checkpoint.risk.overall}
        </span>
      </div>
      <p className="mt-2 capitalize text-xs text-slate-500">{weatherDescription}</p>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <PopupMetric icon={<WindIcon />} label="Wind" value={`${checkpoint.weather.wind_mph.toFixed(0)} mph`} />
        <PopupMetric icon={<RainIcon />} label="Rain" value={`${checkpoint.weather.rain_in_per_hour.toFixed(2)} in/h`} />
        <PopupMetric
          icon={<TemperatureIcon />}
          label="Temp"
          value={checkpoint.weather.temperature_f == null ? "—" : `${checkpoint.weather.temperature_f.toFixed(0)}°F`}
        />
      </div>
      <div className="mt-3 border-t border-slate-200 pt-2 text-[11px] text-slate-500">
        Weather forecast valid {formatDateTime(checkpoint.weather.forecast_time)}
      </div>
    </div>
  );
}

function PopupMetric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg bg-slate-100 p-2">
      <div className="flex items-center gap-1 text-slate-400 [&>svg]:size-3">{icon}{label}</div>
      <p className="mt-1 text-[11px] font-bold text-slate-800">{value}</p>
    </div>
  );
}

function checkpointTimeDistance(
  checkpoint: Checkpoint,
  departureTime: string | null,
  forecastHour: number,
): number {
  if (!departureTime) return 48;
  const checkpointHour =
    (new Date(checkpoint.eta).getTime() - new Date(departureTime).getTime()) / 3_600_000;
  return Math.abs(checkpointHour - forecastHour);
}
