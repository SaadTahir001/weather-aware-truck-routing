import type {
  Checkpoint,
  ForecastTimelineEntry,
  RiskBreakdown,
  WeatherReading,
} from "../types/routing";

export function forecastAtHour(
  checkpoint: Checkpoint,
  forecastHour: number,
): ForecastTimelineEntry {
  const timeline = checkpoint.forecast_timeline ?? [];
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
