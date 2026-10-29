import type { RiskLevel } from "../types/routing";

export const RISK_COLORS: Record<RiskLevel, string> = {
  Low: "#24c78e",
  Moderate: "#e8c94a",
  High: "#f59e42",
  Severe: "#ef5b5b",
  "No Travel": "#a855f7",
};

export const RISK_TEXT_CLASSES: Record<RiskLevel, string> = {
  Low: "text-emerald-300 bg-emerald-400/10 ring-emerald-300/20",
  Moderate: "text-yellow-200 bg-yellow-400/10 ring-yellow-300/20",
  High: "text-orange-200 bg-orange-400/10 ring-orange-300/20",
  Severe: "text-red-200 bg-red-400/10 ring-red-300/20",
  "No Travel": "text-purple-200 bg-purple-400/10 ring-purple-300/20",
};

export const ROUTE_COLORS = ["#31d6a3", "#4fb8ff", "#ffb454"] as const;

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
}

export function formatDateTime(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

export function formatLoad(pounds: number): string {
  return `${new Intl.NumberFormat().format(pounds)} lb`;
}

export function riskScore(level: RiskLevel): number {
  return ["Low", "Moderate", "High", "Severe", "No Travel"].indexOf(level) + 1;
}

export function toDateTimeLocalValue(date: Date): string {
  const timezoneOffset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - timezoneOffset).toISOString().slice(0, 16);
}
