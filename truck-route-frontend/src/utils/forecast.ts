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

  return timeline.reduce((closest, candidate) =>
    Math.abs(candidate.hour_offset - forecastHour) <
    Math.abs(closest.hour_offset - forecastHour)
      ? candidate
      : closest,
  );
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
