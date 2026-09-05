"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SignalListResponse } from "@/lib/types";
import { SignalTable } from "@/components/SignalTable";
import { SignalCard } from "@/components/SignalCard";
import { EMPTY_FILTERS, Filters, type FilterState } from "@/components/Filters";

const PAGE_SIZE = 50;

export default function HistoryPage() {
  const [data, setData] = useState<SignalListResponse | null>(null);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      const params: Record<string, string | number | boolean | undefined> = {
        limit: PAGE_SIZE,
        offset,
        type: filters.type,
        sector: filters.sector,
        min_confidence: filters.min_confidence ? Number(filters.min_confidence) : undefined,
        min_price: filters.min_price ? Number(filters.min_price) : undefined,
        max_price: filters.max_price ? Number(filters.max_price) : undefined,
        exclude_earnings_week: filters.exclude_earnings_week,
        exclude_macro_risk: filters.exclude_macro_risk,
      };
      api
        .signals(params)
        .then(setData)
        .catch((e) => setError(e instanceof Error ? e.message : "Failed to load history"))
        .finally(() => setLoading(false));
    }, 350);
    return () => clearTimeout(t);
  }, [filters, offset]);

  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold sm:text-2xl">Signal History</h1>
        <p className="text-sm text-slate-400">{total} signals across all dates.</p>
      </div>

      <Filters
        filters={filters}
        onChange={(patch) => {
          setFilters((f) => ({ ...f, ...patch }));
          setOffset(0);
        }}
        onReset={() => {
          setFilters(EMPTY_FILTERS);
          setOffset(0);
        }}
      />

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-sm text-slate-400">Loading…</p>}
      {!loading && data && data.signals.length === 0 && (
        <p className="text-sm text-slate-400">No signals found.</p>
      )}

      {data && data.signals.length > 0 && (
        <>
          <SignalTable signals={data.signals} />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:hidden">
            {data.signals.map((s) => (
              <SignalCard key={s.id} signal={s} />
            ))}
          </div>

          <div className="flex items-center justify-between">
            <button
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              className="min-h-[44px] rounded-lg border border-slate-700 px-4 text-sm disabled:opacity-40"
            >
              ← Previous
            </button>
            <span className="text-xs text-slate-400">
              {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <button
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              className="min-h-[44px] rounded-lg border border-slate-700 px-4 text-sm disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
