import type {
  Checkpoint,
  ForecastTimelineEntry,
  RiskBreakdown,
  RiskLevel,
  WeatherReading,
} from "../types/routing";

const RISK_LEVELS = new Set<RiskLevel>([
  "Low",
  "Moderate",
  "High",
  "Severe",
  "No Travel",
]);
const TIMELINE_CACHE = new WeakMap<Checkpoint, ForecastTimelineEntry[]>();

export function forecastAtHour(
  checkpoint: Checkpoint,
  forecastHour: number,
): ForecastTimelineEntry {
  const timeline = normalizedTimeline(checkpoint);
  if (timeline.length === 0) {
    return fallbackForecast(checkpoint.weather, checkpoint.risk);
  }

  const selectedHour = normalizeForecastHour(forecastHour);
  const exactMatch = timeline.find(
    (entry) => Number(entry.hour_offset) === selectedHour,
  );
  if (exactMatch) return exactMatch;

  // A 49-entry response is ordered 0h...48h, so indexing is the most
  // reliable fallback when an older API response omits hour_offset.
  if (timeline.length >= 49) {
    const indexedEntry = timeline[selectedHour];
    if (indexedEntry) return indexedEntry;
  }

  return timeline.reduce((closest, candidate) => {
    const candidateOffset = Number(candidate.hour_offset);
    const closestOffset = Number(closest.hour_offset);
    if (!Number.isFinite(candidateOffset)) return closest;
    if (!Number.isFinite(closestOffset)) return candidate;
    return Math.abs(candidateOffset - selectedHour) <
      Math.abs(closestOffset - selectedHour)
      ? candidate
      : closest;
  });
}

export function normalizeForecastHour(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(48, Math.max(0, Math.round(value)));
}

export function checkpointNearestHour(
  checkpoints: Checkpoint[],
  departureTime: string | null,
  forecastHour: number,
): Checkpoint | null {
  if (checkpoints.length === 0) return null;
  if (!departureTime) return checkpoints[0];

  const departureTimestamp = new Date(departureTime).getTime();
  return checkpoints.reduce((closest, candidate) =>
    checkpointHourDistance(candidate, departureTimestamp, forecastHour) <
    checkpointHourDistance(closest, departureTimestamp, forecastHour)
      ? candidate
      : closest,
  );
}

function checkpointHourDistance(
  checkpoint: Checkpoint,
  departureTimestamp: number,
  forecastHour: number,
): number {
  const checkpointHour =
    (new Date(checkpoint.eta).getTime() - departureTimestamp) / 3_600_000;
  return Math.abs(checkpointHour - forecastHour);
}

function fallbackForecast(
  weather: WeatherReading,
  risk: RiskBreakdown,
): ForecastTimelineEntry {
  return { hour_offset: 0, weather, risk };
}

function normalizedTimeline(checkpoint: Checkpoint): ForecastTimelineEntry[] {
  const cached = TIMELINE_CACHE.get(checkpoint);
  if (cached) return cached;

  const source = checkpoint as unknown as Record<string, unknown>;
  const rawTimeline = [
    source.forecast_timeline,
    source.forecastTimeline,
    source.weather_timeline,
    source.timeline,
  ].find(Array.isArray);

  if (!Array.isArray(rawTimeline)) return [];
  const normalized = rawTimeline
    .map((entry, index) => normalizeTimelineEntry(entry, index, checkpoint))
    .filter((entry): entry is ForecastTimelineEntry => entry !== null)
    .sort((left, right) => left.hour_offset - right.hour_offset);
  TIMELINE_CACHE.set(checkpoint, normalized);
  return normalized;
}

function normalizeTimelineEntry(
  value: unknown,
  index: number,
  checkpoint: Checkpoint,
): ForecastTimelineEntry | null {
  const entry = asRecord(value);
  if (!entry) return null;

  const rawOffset =
    entry.hour_offset ?? entry.hourOffset ?? entry.offset ?? index;
  const weatherSource =
    asRecord(entry.weather) ??
    asRecord(entry.forecast) ??
    asRecord(entry.weather_data) ??
    entry;
  const riskSource =
    asRecord(entry.risk) ??
    asRecord(entry.risk_breakdown) ??
    asRecord(entry.riskBreakdown);

  return {
    hour_offset: normalizeForecastHour(Number(rawOffset)),
    weather: normalizeWeather(weatherSource, checkpoint.weather),
    risk: normalizeRisk(riskSource, checkpoint.risk),
  };
}

function normalizeWeather(
  source: Record<string, unknown>,
  fallback: WeatherReading,
): WeatherReading {
  return {
    forecast_time: stringValue(
      source,
      ["forecast_time", "forecastTime", "timestamp", "time"],
      fallback.forecast_time,
    ),
    wind_mph: numberValue(
      source,
      ["wind_mph", "windMph", "wind_speed", "windSpeed"],
      fallback.wind_mph,
    ),
    rain_in_per_hour: numberValue(
      source,
      ["rain_in_per_hour", "rainInPerHour", "rain"],
      fallback.rain_in_per_hour,
    ),
    snow_in_per_hour: numberValue(
      source,
      ["snow_in_per_hour", "snowInPerHour", "snow"],
      fallback.snow_in_per_hour,
    ),
    temperature_f: nullableNumberValue(
      source,
      ["temperature_f", "temperatureF", "temp"],
      fallback.temperature_f,
    ),
    description: stringValue(
      source,
      ["description", "condition", "summary"],
      fallback.description,
    ),
  };
}

function normalizeRisk(
  source: Record<string, unknown> | null,
  fallback: RiskBreakdown,
): RiskBreakdown {
  if (!source) return fallback;
  return {
    wind: riskValue(source.wind, fallback.wind),
    rain: riskValue(source.rain, fallback.rain),
    snow: riskValue(source.snow, fallback.snow),
    overall: riskValue(
      source.overall ?? source.overall_risk ?? source.overallRisk,
      fallback.overall,
    ),
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function firstValue(
  source: Record<string, unknown>,
  keys: string[],
): unknown {
  for (const key of keys) {
    if (source[key] !== undefined) return source[key];
  }
  return undefined;
}

function stringValue(
  source: Record<string, unknown>,
  keys: string[],
  fallback: string,
): string {
  const value = firstValue(source, keys);
  return typeof value === "string" && value ? value : fallback;
}

function numberValue(
  source: Record<string, unknown>,
  keys: string[],
  fallback: number,
): number {
  const value = Number(firstValue(source, keys));
  return Number.isFinite(value) ? value : fallback;
}

function nullableNumberValue(
  source: Record<string, unknown>,
  keys: string[],
  fallback: number | null,
): number | null {
  const rawValue = firstValue(source, keys);
  if (rawValue === null) return null;
  const value = Number(rawValue);
  return Number.isFinite(value) ? value : fallback;
}

function riskValue(value: unknown, fallback: RiskLevel): RiskLevel {
  return typeof value === "string" && RISK_LEVELS.has(value as RiskLevel)
    ? (value as RiskLevel)
    : fallback;
}
