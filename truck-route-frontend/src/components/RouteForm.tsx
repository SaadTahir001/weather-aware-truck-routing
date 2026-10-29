import { useEffect, useState, type FormEvent } from "react";
import type { RouteCalculationRequest } from "../types/routing";
import { toDateTimeLocalValue } from "../utils/format";
import {
  AlertIcon,
  ArrowRightIcon,
  CalendarIcon,
  PinIcon,
  SwapIcon,
  WeightIcon,
} from "./icons";

interface RouteFormProps {
  loading: boolean;
  error: string | null;
  onSubmit: (request: RouteCalculationRequest) => void;
  onCancel: () => void;
}

interface FormState {
  origin: string;
  destination: string;
  departureTime: string;
  loadWeight: string;
}

function initialFormState(): FormState {
  const departure = new Date(Date.now() + 2 * 60 * 60 * 1000);
  departure.setMinutes(Math.ceil(departure.getMinutes() / 15) * 15, 0, 0);
  return {
    origin: "",
    destination: "",
    departureTime: toDateTimeLocalValue(departure),
    loadWeight: "36000",
  };
}

export function RouteForm({ loading, error, onSubmit, onCancel }: RouteFormProps) {
  const [form, setForm] = useState<FormState>(initialFormState);

  useEffect(() => onCancel, [onCancel]);

  function update<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit({
      origin: form.origin.trim(),
      destination: form.destination.trim(),
      departure_time: new Date(form.departureTime).toISOString(),
      load_weight_lb: Number(form.loadWeight),
    });
  }

  function swapLocations() {
    setForm((current) => ({
      ...current,
      origin: current.destination,
      destination: current.origin,
    }));
  }

  return (
    <section className="panel-shell overflow-hidden" aria-labelledby="trip-form-title">
      <div className="border-b border-white/8 px-5 py-4">
        <p className="eyebrow">New dispatch analysis</p>
        <h2 id="trip-form-title" className="mt-1 text-lg font-semibold text-white">
          Plan a weather-safe route
        </h2>
      </div>

      <form className="space-y-4 p-5" onSubmit={handleSubmit}>
        <div className="relative space-y-3">
          <FormField
            icon={<PinIcon className="size-4" />}
            id="origin"
            label="Origin"
            placeholder="City, terminal, or address"
            value={form.origin}
            onChange={(value) => update("origin", value)}
            required
          />
          <button
            type="button"
            onClick={swapLocations}
            className="absolute right-3 top-[66px] z-10 grid size-8 place-items-center rounded-full border border-white/10 bg-slate-900 text-slate-400 transition hover:border-emerald-300/30 hover:text-emerald-300 focus:outline-none focus:ring-2 focus:ring-emerald-300/50"
            aria-label="Swap origin and destination"
          >
            <SwapIcon className="size-4 rotate-90" />
          </button>
          <FormField
            icon={<PinIcon className="size-4" />}
            id="destination"
            label="Destination"
            placeholder="City, terminal, or address"
            value={form.destination}
            onChange={(value) => update("destination", value)}
            required
          />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <FormField
            icon={<CalendarIcon className="size-4" />}
            id="departure-time"
            label="Departure"
            type="datetime-local"
            value={form.departureTime}
            onChange={(value) => update("departureTime", value)}
            required
          />
          <FormField
            icon={<WeightIcon className="size-4" />}
            id="load-weight"
            label="Load weight"
            type="number"
            inputMode="numeric"
            min="0"
            step="500"
            suffix="lb"
            value={form.loadWeight}
            onChange={(value) => update("loadWeight", value)}
            required
          />
        </div>

        {error && (
          <div
            role="alert"
            className="flex gap-3 rounded-xl border border-red-300/15 bg-red-400/8 p-3 text-sm text-red-100"
          >
            <AlertIcon className="mt-0.5 size-4 shrink-0 text-red-300" />
            <p>{error}</p>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="group flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-400 px-4 py-3 text-sm font-bold text-slate-950 shadow-[0_10px_30px_rgba(49,214,163,0.15)] transition hover:bg-emerald-300 focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:ring-offset-2 focus:ring-offset-slate-950 disabled:cursor-wait disabled:opacity-65"
        >
          {loading ? (
            <>
              <span className="size-4 animate-spin rounded-full border-2 border-slate-900/30 border-t-slate-900" />
              Sampling routes & weather
            </>
          ) : (
            <>
              Calculate safest route
              <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
            </>
          )}
        </button>

        <p className="text-center text-[11px] leading-4 text-slate-500">
          Compares severe miles, high miles, average risk, then travel time.
        </p>
      </form>
    </section>
  );
}

interface FormFieldProps {
  icon: React.ReactNode;
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  suffix?: string;
  inputMode?: "numeric";
  min?: string;
  step?: string;
  required?: boolean;
}

function FormField({ icon, label, suffix, ...inputProps }: FormFieldProps) {
  return (
    <label htmlFor={inputProps.id} className="block">
      <span className="mb-1.5 block text-xs font-medium text-slate-400">{label}</span>
      <span className="relative block">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-500">
          {icon}
        </span>
        <input
          {...inputProps}
          onChange={(event) => inputProps.onChange(event.target.value)}
          className="field-input"
        />
        {suffix && (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs font-semibold text-slate-500">
            {suffix}
          </span>
        )}
      </span>
    </label>
  );
}
