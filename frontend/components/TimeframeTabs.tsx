"use client";

import {
  TIMEFRAMES,
  TIMEFRAME_DESCRIPTIONS,
  TIMEFRAME_LABELS,
  type Timeframe,
} from "@/lib/types";

/**
 * Candle-interval selector. The same setup rules are read on daily, weekly and
 * monthly candles, so this switches which list you are looking at rather than
 * changing the rules.
 */
export function TimeframeTabs({
  value,
  onChange,
}: {
  value: Timeframe;
  onChange: (timeframe: Timeframe) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs uppercase tracking-wide text-slate-500">Interval</span>
      <div className="flex flex-wrap gap-1">
        {TIMEFRAMES.map((timeframe) => (
          <button
            key={timeframe}
            type="button"
            onClick={() => onChange(timeframe)}
            aria-pressed={value === timeframe}
            title={TIMEFRAME_DESCRIPTIONS[timeframe]}
            className={`min-h-[40px] rounded-lg px-4 text-sm font-medium transition ${
              value === timeframe
                ? "bg-sky-600 text-white"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            {TIMEFRAME_LABELS[timeframe]}
          </button>
        ))}
      </div>
    </div>
  );
}
