"use client";

export interface FilterState {
  type: string;
  sector: string;
  min_confidence: string;
  exclude_earnings_week: boolean;
  exclude_macro_risk: boolean;
  min_price: string;
  max_price: string;
}

export const EMPTY_FILTERS: FilterState = {
  type: "",
  sector: "",
  min_confidence: "",
  exclude_earnings_week: false,
  exclude_macro_risk: false,
  min_price: "",
  max_price: "",
};

const SECTORS = [
  "Technology",
  "Financials",
  "Healthcare",
  "Energy",
  "Consumer Discretionary",
  "Consumer Staples",
  "Industrials",
  "Materials",
  "Utilities",
  "Real Estate",
  "Communication Services",
];

const inputCls =
  "min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 text-sm text-slate-100";

export function Filters({
  filters,
  onChange,
  onReset,
}: {
  filters: FilterState;
  onChange: (patch: Partial<FilterState>) => void;
  onReset: () => void;
}) {
  const hasActive =
    filters.type ||
    filters.sector ||
    filters.min_confidence ||
    filters.min_price ||
    filters.max_price ||
    filters.exclude_earnings_week ||
    filters.exclude_macro_risk;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Filters</h3>
        {hasActive && (
          <button onClick={onReset} className="text-xs text-slate-400 underline hover:text-white">
            Reset
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Type</span>
          <select
            className={inputCls}
            value={filters.type}
            onChange={(e) => onChange({ type: e.target.value })}
          >
            <option value="">All</option>
            <option value="BUY_STANDARD">Buy (Standard)</option>
            <option value="BUY_DOJI_REVERSAL">Doji Reversal</option>
            <option value="SELL">Sell</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Sector</span>
          <select
            className={inputCls}
            value={filters.sector}
            onChange={(e) => onChange({ sector: e.target.value })}
          >
            <option value="">All</option>
            {SECTORS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Min confidence</span>
          <input
            className={inputCls}
            type="number"
            min={0}
            max={100}
            placeholder="0"
            value={filters.min_confidence}
            onChange={(e) => onChange({ min_confidence: e.target.value })}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Min price</span>
          <input
            className={inputCls}
            type="number"
            min={0}
            placeholder="$"
            value={filters.min_price}
            onChange={(e) => onChange({ min_price: e.target.value })}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Max price</span>
          <input
            className={inputCls}
            type="number"
            min={0}
            placeholder="$"
            value={filters.max_price}
            onChange={(e) => onChange({ max_price: e.target.value })}
          />
        </label>
        <label className="col-span-1 flex min-h-[44px] items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3">
          <input
            type="checkbox"
            checked={filters.exclude_earnings_week}
            onChange={(e) => onChange({ exclude_earnings_week: e.target.checked })}
            className="h-5 w-5"
          />
          <span className="text-xs text-slate-300">No earnings week</span>
        </label>
        <label className="col-span-1 flex min-h-[44px] items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3">
          <input
            type="checkbox"
            checked={filters.exclude_macro_risk}
            onChange={(e) => onChange({ exclude_macro_risk: e.target.checked })}
            className="h-5 w-5"
          />
          <span className="text-xs text-slate-300">No macro risk</span>
        </label>
      </div>
    </div>
  );
}
