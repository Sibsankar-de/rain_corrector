/** Date range selector with explicit start/end dates and quick presets. */

import { useId } from "react";

import { toIsoDate } from "@/lib/format";

export interface DateRangeSelectorProps {
  start: string;
  end: string;
  min?: string;
  max?: string;
  onChange: (range: { start: string; end: string }) => void;
  presets?: { label: string; days: number }[];
  disabled?: boolean;
}

const DEFAULT_PRESETS = [
  { label: "7d", days: 7 },
  { label: "14d", days: 14 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 }
];

function daysAgo(days: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return toIsoDate(date);
}

export function DateRangeSelector({
  start,
  end,
  min,
  max,
  onChange,
  presets = DEFAULT_PRESETS,
  disabled = false
}: DateRangeSelectorProps) {
  const startId = useId();
  const endId = useId();
  const today = toIsoDate(new Date());

  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="flex flex-col gap-1">
        <label htmlFor={startId} className="data-label">
          From
        </label>
        <input
          id={startId}
          type="date"
          value={start}
          min={min}
          max={max ?? today}
          disabled={disabled}
          onChange={(event) => onChange({ start: event.target.value, end })}
          className="rounded border border-edge bg-surface-raised px-2 py-1.5 text-xs disabled:opacity-50"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor={endId} className="data-label">
          To
        </label>
        <input
          id={endId}
          type="date"
          value={end}
          min={min ?? start}
          max={max ?? today}
          disabled={disabled}
          onChange={(event) => onChange({ start, end: event.target.value })}
          className="rounded border border-edge bg-surface-raised px-2 py-1.5 text-xs disabled:opacity-50"
        />
      </div>

      <div className="flex items-center gap-1" role="group" aria-label="Date range presets">
        {presets.map((preset) => {
          const presetStart = daysAgo(preset.days);
          const active = start === presetStart;
          return (
            <button
              key={preset.label}
              type="button"
              disabled={disabled}
              onClick={() => onChange({ start: presetStart, end: today })}
              aria-pressed={active}
              className={`rounded border px-2 py-1.5 text-xs font-medium disabled:opacity-50 ${
                active
                  ? "border-brand-600 bg-brand-50 text-brand-800"
                  : "border-edge bg-surface-raised text-ink-muted hover:bg-surface-sunken"
              }`}
            >
              {preset.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
