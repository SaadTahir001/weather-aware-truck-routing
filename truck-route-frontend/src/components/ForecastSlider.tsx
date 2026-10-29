import { useEffect, useState } from "react";
import { formatDateTime } from "../utils/format";
import { ClockIcon } from "./icons";

interface ForecastSliderProps {
  departureTime: string | null;
  value: number;
  onChange: (hours: number) => void;
}

export function ForecastSlider({
  departureTime,
  value,
  onChange,
}: ForecastSliderProps) {
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const interval = window.setInterval(() => {
      onChange(value >= 48 ? 0 : value + 1);
    }, 700);
    return () => window.clearInterval(interval);
  }, [onChange, playing, value]);

  const selectedTime = departureTime
    ? new Date(new Date(departureTime).getTime() + value * 3_600_000)
    : null;
  const fill = `${(value / 48) * 100}%`;

  return (
    <section className="border-t border-white/8 bg-slate-950/88 px-4 py-4 backdrop-blur-xl sm:px-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="flex min-w-0 items-center gap-3 lg:w-72">
          <button
            type="button"
            onClick={() => setPlaying((current) => !current)}
            disabled={!departureTime}
            className="grid size-9 shrink-0 place-items-center rounded-full border border-white/10 bg-white/5 text-emerald-300 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label={playing ? "Pause forecast animation" : "Play forecast animation"}
          >
            {playing ? (
              <span className="flex gap-1" aria-hidden="true">
                <span className="h-3 w-0.5 rounded-full bg-current" />
                <span className="h-3 w-0.5 rounded-full bg-current" />
              </span>
            ) : (
              <span className="ml-0.5 size-0 border-y-[6px] border-l-[9px] border-y-transparent border-l-current" />
            )}
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
              <ClockIcon className="size-3.5" />
              Forecast corridor
            </div>
            <p className="mt-1 truncate text-sm font-medium text-white">
              {selectedTime ? formatDateTime(selectedTime) : "Submit a trip to activate"}
            </p>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <span className="w-8 text-right text-[11px] font-semibold text-slate-500">0h</span>
            <input
              aria-label="Forecast hour from departure"
              type="range"
              min="0"
              max="48"
              step="1"
              value={value}
              disabled={!departureTime}
              onChange={(event) => onChange(Number(event.target.value))}
              className="forecast-range"
              style={{ "--range-fill": fill } as React.CSSProperties}
            />
            <span className="w-9 text-[11px] font-semibold text-slate-500">48h</span>
          </div>
          <div className="ml-11 mr-12 mt-1.5 flex justify-between text-[10px] text-slate-600">
            <span>Departure</span>
            <span>+12h</span>
            <span>+24h</span>
            <span>+36h</span>
            <span>+48h</span>
          </div>
        </div>

        <div className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2 text-xs text-slate-400 lg:max-w-64">
          Showing ETA-aligned forecasts nearest <strong className="text-slate-200">+{value}h</strong>.
        </div>
      </div>
    </section>
  );
}
