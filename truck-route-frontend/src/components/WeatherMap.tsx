import { Fragment, useEffect, useMemo } from "react";
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
import type {
  Checkpoint,
  ForecastTimelineEntry,
  RiskLevel,
  RouteResult,
} from "../types/routing";
import {
  checkpointNearestHour,
  forecastAtHour,
  logLiveRoutePayload,
} from "../utils/forecast";
import {
  formatDateTime,
  formatDuration,
  PALETTE,
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

  useEffect(() => {
    routes.forEach(logLiveRoutePayload);
  }, [routes]);

  return (
    <section className="relative min-h-[520px] flex-1 overflow-hidden bg-[#0B1218]">
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
                const forecast = forecastAtHour(checkpoint, forecastHour);
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
                    radius={5_000 + riskScore(forecast.risk.overall) * 2_500}
                    pathOptions={{
                      color: RISK_COLORS[forecast.risk.overall],
                      fillColor: RISK_COLORS[forecast.risk.overall],
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
            const routeColor = recommended
              ? PALETTE.blue
              : ROUTE_COLORS[index % ROUTE_COLORS.length];
            const positions = route.geometry.coordinates.map(
              ([longitude, latitude]) => [latitude, longitude] as LatLngExpression,
            );

            return (
              <Fragment key={route.id}>
              <Polyline
                positions={positions}
                pathOptions={{
                  color: routeColor,
                  weight: selected ? 7 : recommended ? 6 : 5,
                  opacity: selected ? 1 : recommended ? 0.96 : 0.62,
                  dashArray: route.eligible ? undefined : "10 8",
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
              {!recommended && (
                <Polyline
                  positions={positions}
                  pathOptions={{
                    color: PALETTE.white,
                    weight: selected ? 2.5 : 1.75,
                    opacity: selected ? 0.9 : 0.58,
                    dashArray: "2 11",
                    lineCap: "round",
                  }}
                  eventHandlers={{ click: () => onSelectRoute(route.id) }}
                />
              )}
              </Fragment>
            );
          })}
        </Pane>

        <Pane name="checkpoint-markers" style={{ zIndex: 430 }}>
          {routes.flatMap((route, routeIndex) =>
          route.checkpoints.map((checkpoint) => {
            const selected = route.id === selectedRouteId;
            const recommended = route.id === recommendedRouteId;
            const forecast = forecastAtHour(checkpoint, forecastHour);
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
                  className: selected && nearSelectedHour ? "active-checkpoint-marker" : undefined,
                  color: recommended
                    ? PALETTE.blue
                    : selected
                      ? PALETTE.cantaloupe
                      : ROUTE_COLORS[routeIndex % ROUTE_COLORS.length],
                  fillColor: RISK_COLORS[forecast.risk.overall],
                  fillOpacity: selected ? 1 : 0.72,
                  opacity: selected ? 1 : 0.7,
                  weight: selected && nearSelectedHour ? 3 : 2,
                }}
                eventHandlers={{ click: () => onSelectRoute(route.id) }}
              >
                <Popup maxWidth={300} minWidth={245}>
                  <CheckpointPopup
                    route={route}
                    checkpoint={checkpoint}
                    forecast={forecast}
                    forecastHour={forecastHour}
                  />
                </Popup>
              </CircleMarker>
            );
          }),
          )}
        </Pane>
      </MapContainer>

      <MapHeader
        routes={routes}
        selectedRoute={selectedRoute}
        departureTime={departureTime}
        forecastHour={forecastHour}
      />
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
  departureTime,
  forecastHour,
}: {
  routes: RouteResult[];
  selectedRoute: RouteResult | null;
  departureTime: string | null;
  forecastHour: number;
}) {
  const activeCheckpoint = selectedRoute
    ? checkpointNearestHour(selectedRoute.checkpoints, departureTime, forecastHour)
    : null;
  const activeForecast = activeCheckpoint
    ? forecastAtHour(activeCheckpoint, forecastHour)
    : null;

  return (
    <div className="pointer-events-none absolute left-4 right-4 top-4 z-[500] flex items-start justify-between gap-3">
      <div className="map-glass-card rounded-xl px-3.5 py-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#0297DE]">
          Network weather view
        </p>
        <p className="mt-0.5 text-sm font-semibold text-slate-50">
          {selectedRoute ? selectedRoute.name : routes.length ? "Three route comparison" : "Awaiting trip details"}
        </p>
        {activeForecast && activeCheckpoint && (
          <p className="mt-1 text-[11px] text-slate-400">
            +{forecastHour}h · CP {activeCheckpoint.sequence} · {activeForecast.weather.temperature_f == null
              ? "—"
              : `${activeForecast.weather.temperature_f.toFixed(0)}°F`} · {activeForecast.weather.description || "No description"}
          </p>
        )}
      </div>
      {routes.length > 0 && (
        <div className="map-glass-card rounded-xl border-[#FC734D]/35 px-3.5 py-2.5 text-right">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#FC734D]">Routes</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-50">{routes.length} analyzed</p>
        </div>
      )}
    </div>
  );
}

function RiskLegend() {
  return (
    <div className="map-glass-card absolute bottom-4 left-4 z-[500] rounded-xl p-3">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#0297DE]">
        Checkpoint risk
      </p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-5">
        {(Object.keys(RISK_COLORS) as RiskLevel[]).map((level) => (
          <div key={level} className="flex items-center gap-1.5 text-[10px] text-slate-300">
            <span
              className="size-2 rounded-full ring-2 ring-slate-50/15"
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
      <div className="map-glass-card max-w-sm rounded-2xl p-6 text-center">
        <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-[#0297DE]/12 ring-1 ring-[#0297DE]/35">
          <span className="size-3 rounded-full bg-[#0297DE] shadow-[0_0_0_8px_rgba(252,115,77,0.11)]" />
        </div>
        <h3 className="mt-4 text-base font-semibold text-slate-50">Your route intelligence map</h3>
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
  forecast,
  forecastHour,
}: {
  route: RouteResult;
  checkpoint: Checkpoint;
  forecast: ForecastTimelineEntry;
  forecastHour: number;
}) {
  const weatherDescription = forecast.weather.description || "No description";
  return (
    <div
      className="checkpoint-popup"
      data-forecast-hour={forecastHour}
      aria-live="polite"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#0297DE]">
            {route.name} · CP {checkpoint.sequence}
          </p>
          <p className="mt-1 text-sm font-bold text-white">
            {formatDateTime(forecast.weather.forecast_time)}
          </p>
          <p className="mt-1 inline-flex rounded-full bg-[#FC734D]/16 px-2 py-0.5 text-[10px] font-bold text-[#FC9A7E] ring-1 ring-[#FC734D]/35">
            Selected +{forecastHour}h forecast
          </p>
        </div>
        <span
          className="rounded-full px-2 py-1 text-[10px] font-bold text-slate-50 shadow-[0_4px_14px_rgba(252,121,77,0.18)]"
          style={{
            backgroundColor: RISK_COLORS[forecast.risk.overall],
            color:
              forecast.risk.overall === "Moderate"
                ? PALETTE.midnight
                : PALETTE.white,
          }}
        >
          {forecast.risk.overall}
        </span>
      </div>
      <p className="mt-2 capitalize text-xs font-medium text-slate-300">{weatherDescription}</p>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <PopupMetric icon={<WindIcon />} label="Wind" value={`${forecast.weather.wind_mph.toFixed(0)} mph`} />
        <PopupMetric icon={<RainIcon />} label="Rain" value={`${forecast.weather.rain_in_per_hour.toFixed(2)} in/h`} />
        <PopupMetric
          icon={<TemperatureIcon />}
          label="Temp"
          value={forecast.weather.temperature_f == null ? "—" : `${forecast.weather.temperature_f.toFixed(0)}°F`}
        />
      </div>
      <div className="mt-3 border-t border-slate-700/60 pt-2 text-[11px] text-slate-400">
        <span className="block font-semibold text-slate-100">
          Weather forecast valid {formatDateTime(forecast.weather.forecast_time)}
        </span>
        <span className="mt-0.5 block">
          Projected checkpoint ETA {formatDateTime(checkpoint.eta)}
        </span>
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
    <div className="rounded-lg border border-[#0297DE]/45 bg-[#0297DE]/14 p-2 shadow-[inset_0_1px_rgba(255,255,255,0.04)]">
      <div className="flex items-center gap-1 font-semibold text-[#55C7FA] [&>svg]:size-3">{icon}{label}</div>
      <p className="mt-1 text-[11px] font-bold text-white">{value}</p>
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
