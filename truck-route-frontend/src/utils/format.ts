import type { RiskLevel } from "../types/routing";

export const PALETTE = {
  blue: "#0297DE",
  cantaloupe: "#FC734D",
  priority: "#FC794D",
  midnight: "#02070A",
  panel: "#0B1218",
  white: "#F8FAFC",
} as const;

export const RISK_COLORS: Record<RiskLevel, string> = {
  Low: "#10B981",
  Moderate: "#F59E0B",
  High: "#FC794D",
  Severe: "#DC2626",
  "No Travel": "#8B5CF6",
};

export const RISK_TEXT_CLASSES: Record<RiskLevel, string> = {
  Low: "text-emerald-200 bg-emerald-500/14 ring-emerald-400/35",
  Moderate: "text-amber-200 bg-amber-500/14 ring-amber-400/35",
  High: "text-[#FFE8E0] bg-[#FC794D]/16 ring-[#FC794D]/45",
  Severe: "text-red-200 bg-red-600/18 ring-red-500/45",
  "No Travel": "text-violet-200 bg-violet-500/16 ring-violet-400/45",
};

export const ROUTE_COLORS = [PALETTE.blue, "#64748B", "#334155"] as const;

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
